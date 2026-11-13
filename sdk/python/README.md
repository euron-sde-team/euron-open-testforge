# euron-testforge

Python SDK and command line for [Euron Open TestForge](../../README.md): import a project,
generate tests whose assertions come from the real code, run them in the sandbox, and read
coverage and failures explained.

```bash
pip install ./sdk/python          # from a checkout of the repository
export TESTFORGE_URL=http://localhost:5630 TESTFORGE_API_KEY=tfk_...
```

```python
from euron_testforge import TestForge

with TestForge() as tf:  # the API key picks the project
    tf.import_github("owner/repo")  # or tf.import_zip("project.zip")
    gen = tf.generate(["unit", "edge", "negative"])
    print(gen.accepted_count, "written,", gen.rejected_count, "refused (no real assertion)")
    tf.accept([t.id for t in tf.tests(generation_id=gen.id)])
    run = tf.run()  # in the sandbox: no network, CPU/memory/time limits
    print(run.status, run.coverage_percent)
    for f in run.failures:
        print(f.test, f.expected, f.actual, f.explanation)
```

`AsyncTestForge` has the same methods with `await`.

Point `TESTFORGE_URL` at the API itself (port 5630 locally). Through the web app's origin
(`/api` on port 5610) a request is proxied with a 120 second limit, so long `wait` values
end early there; the API waits up to 900 seconds for a run.

## CLI

```bash
testforge-cli import-github owner/repo
testforge-cli generate --pull 12          # only the code pull request #12 changes
testforge-cli accept --all
testforge-cli run                         # exit 1 unless every test passed: a CI step
testforge-cli coverage
testforge-cli report --run RUN_ID --format html > report.html
```

API keys carry scopes: `read`, `generate`, `execute`, `manage`. A CI job that only runs
accepted tests needs `read` and `execute`.

MIT licence.
