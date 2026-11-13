"""The ``testforge`` command: every service and admin task in one entry point. (The SDK's
own command line, for developers and CI, is ``testforge-cli`` in ``sdk/python``.)"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys


def _uvicorn(target: str, args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        target,
        factory=True,
        host=args.host,
        port=args.port,
        workers=1,  # one process per container: metrics and in-process state stay exact
        proxy_headers=True,
        # Only trust X-Forwarded-For from the load balancer's network (the VPC CIDR on AWS).
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        access_log=False,
        log_config=None,
        timeout_graceful_shutdown=30,
    )


def _serve(args: argparse.Namespace) -> None:
    _uvicorn("testforge.main:create_app", args)


def _sandbox(args: argparse.Namespace) -> None:
    _uvicorn("testforge.sandbox.server:create_app", args)


def _worker(_: argparse.Namespace) -> None:
    from testforge.worker import main

    asyncio.run(main())


def _scheduler(_: argparse.Namespace) -> None:
    from testforge.worker import scheduler_main

    asyncio.run(scheduler_main())


def _migrate(_: argparse.Namespace) -> None:
    from testforge.core.config import get_settings
    from testforge.migrations.runner import upgrade

    upgrade(get_settings().database_url)
    print("migrations applied")


def _revision(args: argparse.Namespace) -> None:
    from testforge.core.config import get_settings
    from testforge.migrations.runner import revision

    revision(get_settings().database_url, args.message)


async def _create_admin(email: str, name: str, password: str) -> None:
    from sqlalchemy import func, select

    from testforge.audit.service import Actor
    from testforge.core.config import get_settings
    from testforge.core.db import Database, import_all_models
    from testforge.core.security import hash_password, password_problems
    from testforge.orgs import service as orgs
    from testforge.users.models import User

    if problems := password_problems(password):
        sys.exit("password needs " + ", ".join(problems))
    import_all_models()
    db = Database(get_settings().database_url, pool_size=1, max_overflow=0)
    try:
        async with db.sessionmaker() as session:
            existing = await session.scalar(
                select(User).where(func.lower(User.email) == email.lower())
            )
            if existing:
                existing.role = "admin"
                existing.password_hash = hash_password(password)
                existing.disabled = False
                existing.session_version += 1
                print(f"updated {email} (admin)")
            else:
                user = User(
                    email=email.lower(),
                    name=name,
                    role="admin",
                    password_hash=hash_password(password),
                )
                session.add(user)
                await session.flush()
                # Every account starts with an organization of its own.
                await orgs.create_for(
                    session, user, f"{name}'s organization", Actor(user.id, user.email, "admin")
                )
                print(f"created {email} (admin)")
            await session.commit()
    finally:
        await db.dispose()


def _admin(args: argparse.Namespace) -> None:
    password = os.environ.get("TESTFORGE_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    asyncio.run(_create_admin(args.email, args.name, password))


def _seed(args: argparse.Namespace) -> None:
    from testforge.demo.seed import run

    asyncio.run(run())


def _openapi(_: argparse.Namespace) -> None:
    from testforge.openapi import spec, to_yaml

    sys.stdout.write(to_yaml(spec()))


def _server(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], name: str, fn: object, help_: str
) -> None:
    p = sub.add_parser(name, help=help_)
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 containers listen on all interfaces
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    p.set_defaults(fn=fn)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="testforge", description="Euron Open TestForge")
    sub = parser.add_subparsers(dest="command", required=True)
    _server(sub, "serve", _serve, "the API")
    _server(sub, "sandbox", _sandbox, "the sandbox service: runs tests in nsjail, no network")
    sub.add_parser(
        "worker", help="the worker: imports and analysis, test generation, sandboxed runs"
    ).set_defaults(fn=_worker)
    sub.add_parser(
        "scheduler", help="the periodic tasks: lease reaper, webhook retries, retention"
    ).set_defaults(fn=_scheduler)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(fn=_migrate)
    p = sub.add_parser("revision", help="autogenerate a migration from the models")
    p.add_argument("-m", "--message", required=True)
    p.set_defaults(fn=_revision)
    p = sub.add_parser("create-admin", help="create or reset an admin account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Admin")
    p.set_defaults(fn=_admin)
    sub.add_parser(
        "seed-demo",
        help="demo projects imported and analyzed, generated tests, runs, a pull request",
    ).set_defaults(fn=_seed)
    sub.add_parser("openapi", help="print the OpenAPI document as YAML").set_defaults(fn=_openapi)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
