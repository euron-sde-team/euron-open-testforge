"""``testforge-cli``: import, generate, review and run tests from a terminal or CI.

    export TESTFORGE_URL=http://localhost:5630 TESTFORGE_API_KEY=tfk_...
    testforge-cli import-zip ./my-project.zip
    testforge-cli import-github owner/repo [--ref main]
    testforge-cli analysis
    testforge-cli generate [--kinds unit,edge,negative] [--pull 12]
    testforge-cli tests [--status proposed]
    testforge-cli accept --all | ID [ID ...]
    testforge-cli run [--kind generated|project|all] [--json]
    testforge-cli coverage
    testforge-cli report --run RUN_ID --format html > report.html

``run`` exits 0 when every test passed, 1 otherwise (a failure, an error, or a sandbox
limit crossed), so it fits as a CI step. ``generate`` exits 1 when the generation failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from euron_testforge.client import TestForge
from euron_testforge.errors import TestForgeError
from euron_testforge.models import Run


def _print_run(run: Run, as_json: bool) -> int:
    if as_json:
        print(json.dumps(run.raw, indent=2, default=str))
        return 0 if run.ok else 1
    cov = f"{run.coverage_percent:.1f}%" if run.coverage_percent is not None else "not measured"
    print(
        f"run {run.id}: {run.status}  passed {run.passed}  failed {run.failed}  errors {run.errors}  coverage {cov}"
    )
    if run.limit_exceeded:
        print(f"stopped at the sandbox's {run.limit_exceeded} limit: {run.message}")
    elif run.message:
        print(run.message)
    for f in run.failures:
        print(f"\nFAILED {f.test}\n  {f.explanation}")
    return 0 if run.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="testforge-cli", description="Euron Open TestForge")
    parser.add_argument("--url", help="API URL (TESTFORGE_URL)")
    parser.add_argument("--api-key", help="project API key (TESTFORGE_API_KEY)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("import-zip", help="upload a ZIP of the project")
    p.add_argument("path")
    p = sub.add_parser("import-github", help="import a GitHub repository")
    p.add_argument("repo", nargs="?")
    p.add_argument("--ref")
    sub.add_parser("analysis", help="languages, frameworks and untested code")
    p = sub.add_parser("pull", help="import a pull request and list the code it changes")
    p.add_argument("number", type=int)
    p = sub.add_parser(
        "generate", help="generate tests (untested code, or a pull request's changes)"
    )
    p.add_argument("--kinds", default="unit,edge,negative")
    p.add_argument("--pull", type=int, help="scope to this pull request's changes")
    p.add_argument("--instructions", default="")
    p = sub.add_parser("tests", help="list generated tests")
    p.add_argument("--status", choices=["proposed", "accepted", "discarded"])
    p = sub.add_parser("accept", help="accept generated tests")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true", help="every proposed test")
    p = sub.add_parser("run", help="run tests in the sandbox; exit 1 unless every test passed")
    p.add_argument("--kind", default="generated", choices=["generated", "project", "all"])
    p.add_argument("--json", action="store_true")
    sub.add_parser("coverage", help="the latest coverage and the trend")
    p = sub.add_parser("report", help="print a report (HTML or CSV) to stdout")
    p.add_argument("--run")
    p.add_argument("--format", default="html", choices=["html", "csv"])
    args = parser.parse_args(argv)

    try:
        with TestForge(url=args.url, api_key=args.api_key) as tf:
            return _dispatch(tf, args)
    except TestForgeError as exc:
        print(f"error: {exc.message} ({exc.code})", file=sys.stderr)
        return 2


def _dispatch(tf: TestForge, args: argparse.Namespace) -> int:
    if args.command == "import-zip":
        imp = tf.import_zip(args.path)
    elif args.command == "import-github":
        imp = tf.import_github(args.repo, args.ref)
    else:
        imp = None
    if imp is not None:
        print(
            f"import {imp.id}: {imp.status} {', '.join(imp.languages)} {', '.join(imp.frameworks)}, {imp.units} units"
        )
        if imp.error:
            print(imp.error)
        return 0 if imp.ready else 1
    if args.command == "analysis":
        a = tf.analysis()
        print(f"{a.get('units', 0)} units, {a.get('untested', 0)} untested")
        for u in a.get("untested_units", []):
            print(f"  {u['kind']:<8} {u['qualname']}  ({u['file']}:{u['start_line']})")
        return 0
    if args.command == "pull":
        pull: dict[str, Any] = tf.import_pull(args.number)
        print(f"#{pull['number']} {pull['title']}: {len(pull['changed_files'])} files changed")
        for u in pull.get("scoped_units", []):
            print(f"  {u['kind']:<8} {u['qualname']}")
        return 0 if pull["status"] == "ready" else 1
    if args.command == "generate":
        pull_id = None
        if args.pull:
            pull_id = str(tf.import_pull(args.pull)["id"])
        gen = tf.generate(
            [k.strip() for k in args.kinds.split(",") if k.strip()],
            pull_id=pull_id,
            instructions=args.instructions,
        )
        print(
            f"generation {gen.id}: {gen.status}, {gen.accepted_count} tests written, {gen.rejected_count} refused"
        )
        for r in gen.rejections:
            print(f"  refused {r['name']}: {r['reason']}")
        if gen.error:
            print(gen.error)
        return 0 if gen.status == "done" else 1
    if args.command == "tests":
        for t in tf.tests(status=args.status):
            print(f"{t.id}  {t.status:<9} {t.kind:<8} {t.name}  {t.last_outcome or ''}")
        return 0
    if args.command == "accept":
        ids = list(args.ids) or ([t.id for t in tf.tests(status="proposed")] if args.all else [])
        if not ids:
            print("nothing to accept (pass test ids or --all)")
            return 1
        print(f"accepted {tf.accept(ids)} tests")
        return 0
    if args.command == "run":
        return _print_run(tf.run(kind=args.kind), args.json)
    if args.command == "coverage":
        cov = tf.coverage()
        latest = cov.get("latest")
        if not latest:
            print("no coverage yet: run tests first")
            return 1
        print(
            f"line coverage {latest['line_percent']}% ({latest['lines_covered']}/{latest['lines_total']}) by {latest['tool']}"
        )
        for f in latest["files"]:
            print(f"  {f['percent']:>6.1f}%  {f['path']}")
        return 0
    if args.command == "report":
        sys.stdout.write(
            tf.report("run" if args.run else "project", args.format, args.run).decode()
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
