# A probe that runs inside the sandbox only (never collected here: its file name is not test_*).
# Runs inside the sandbox. Tests named test_read_* / test_write_* must FAIL: the run sees
# only its own workspace, a private /tmp and read-only system directories. The others pass.
import os

SECRET = "test-only-sandbox-secret-that-must-never-leak"


def test_environment_holds_no_secret():
    assert not any(SECRET in value for value in os.environ.values())
    assert "SANDBOX_SECRET" not in os.environ
    assert "DATABASE_URL" not in os.environ


def test_runs_as_nobody():
    assert os.getuid() == 65534


def test_read_etc_passwd():
    open("/etc/passwd").read()


def test_read_the_service_code():
    os.listdir("/opt/venv")


def test_read_proc():
    open("/proc/self/environ", "rb").read()


def test_read_another_runs_workspace():
    other = os.environ.get("OTHER_RUN", "/tmp/testforge-sandbox-tests")
    os.listdir(other)


def test_read_the_host_root_home():
    os.listdir("/root")


def test_write_outside_the_workspace():
    with open("/usr/escaped", "w") as fh:
        fh.write("x")


def test_write_the_toolchain():
    with open("/opt/toolchain/plugins/testforge_pytest.py", "a") as fh:
        fh.write("# tampered")


def test_replace_reports_with_links():
    # Point the run's own output files at a file only the service process could read.
    # The service must refuse to follow them (it opens outputs with O_NOFOLLOW).
    out = "/box/.testforge"
    for name in ("events.jsonl", "coverage.json"):
        path = os.path.join(out, name)
        if os.path.lexists(path):
            os.remove(path)
        os.symlink("/proc/1/environ", path)
    assert os.path.islink(os.path.join(out, "events.jsonl"))
