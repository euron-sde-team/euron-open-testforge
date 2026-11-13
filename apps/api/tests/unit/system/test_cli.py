"""The testforge command's roles and admin tasks, wired without starting servers."""

from __future__ import annotations

import pytest

from testforge import cli


def test_openapi_prints_the_document(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["openapi"])
    out = capsys.readouterr().out
    assert out.startswith("openapi:") and "Euron Open TestForge" in out


def test_roles_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(cli, "_uvicorn", lambda target, args: seen.append(f"{target}:{args.port}"))
    cli.main(["serve", "--port", "9001"])
    cli.main(["sandbox", "--port", "9002"])
    assert seen == ["testforge.main:create_app:9001", "testforge.sandbox.server:create_app:9002"]


def test_create_admin_refuses_a_weak_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESTFORGE_ADMIN_PASSWORD", "weak")
    with pytest.raises(SystemExit, match="password needs"):
        cli.main(["create-admin", "--email", "a@example.test"])


def test_unknown_command() -> None:
    with pytest.raises(SystemExit):
        cli.main(["nope"])
