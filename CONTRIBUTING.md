# Contributing

Start with an issue describing a concrete retrieval failure, unsafe disclosure or confusing measurement. Small, focused pull requests are welcome.

```sh
python -m pip install -e . coverage
coverage run --source=src/contextpilot -m unittest discover -s tests -v
coverage report --show-missing
python scripts/benchmark.py --output examples/results
python scripts/real_benchmark.py
```

Changes to ranking must include a failing retrieval example and keep budget and evidence tests passing. Update checked-in reports if behavior changes. A benchmark that fails to retain required evidence is a failure even if its output is smaller.

Keep the runtime dependency-free. Do not add telemetry, automatic uploads, billing-token claims or account-limit workarounds. Keep generated private caches out of version control. Never include real credentials in fixtures or issue reports.

Commits should describe the behavior changed. There is no commit-count target. CI verifies Windows / Linux and Python 3.9 / 3.12 / 3.13.
