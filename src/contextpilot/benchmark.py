"""A labelled synthetic retrieval benchmark, not a model-cost experiment."""

import json
import tempfile
import subprocess
from pathlib import Path
from .engine import pack, scan
from .logs import digest_log

CASES = [
    {
        "id": "session-expiry",
        "query": "SessionExpiry expires_at session cookie login",
        "required": {
            "auth/session.py": "def is_session_expired",
            "auth/login.py": "def validate_login_cookie",
        },
    },
    {
        "id": "payment-idempotency",
        "query": "PaymentIdempotency duplicate invoice payment",
        "required": {
            "billing/payment.py": "def claim_payment_key",
            "billing/invoice.py": "def invoice_total",
        },
    },
    {
        "id": "upload-resume",
        "query": "UploadOffset chunk resume upload sha256",
        "required": {
            "media/upload.py": "def validate_upload_offset",
            "media/hash.py": "def verify_sha256",
        },
    },
    {
        "id": "search-pagination",
        "query": "SearchCursor paginate search next_cursor",
        "required": {
            "search/cursor.py": "def decode_search_cursor",
            "search/results.py": "def paginate_search",
        },
    },
    {
        "id": "turkish-symbol-query",
        "query": "Stok rezervasyon InventoryReservation stock release",
        "required": {
            "warehouse/stock.py": "def release_stock",
            "warehouse/reservation.py": "def reserve_inventory",
        },
    },
]


def isolate_fixture(root):
    """Do not inherit an enclosing checkout's ignore rules for temporary benchmark data."""
    try:
        subprocess.run(
            ["git", "init", str(root)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pass


def fixture(root):
    """Valid small Python modules with target functions and deterministic filler."""
    isolate_fixture(root)
    for case in CASES:
        for path, marker in case["required"].items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            prefix = "\n".join(
                "# Background record {:03d}: stable domain metadata.".format(i) for i in range(100)
            )
            function = (
                marker + "(value, expected=0):\n"
                '    """' + case["query"] + '."""\n'
                "    return value == expected\n"
            )
            suffix = "\n".join(
                "# Documentation detail {:03d}: retain audit history.".format(i) for i in range(100)
            )
            p.write_text(prefix + "\n\n" + function + "\n" + suffix, encoding="utf-8")
    for i in range(20):
        p = root / "catalog" / ("item_{:02d}.py".format(i))
        p.parent.mkdir(exist_ok=True)
        p.write_text(
            "\n".join('LABEL_{} = "Product metadata category {}"'.format(j, i) for j in range(200)),
            encoding="utf-8",
        )


def run_benchmark(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="contextpilot-benchmark-") as tmp:
        root = Path(tmp)
        fixture(root)
        for case in CASES:
            output, report = pack(root, case["query"], max_chars=4500, max_files=4)
            paths = {r["path"] for r in report["selected"]}
            hit = sum(p in paths and marker in output for p, marker in case["required"].items())
            results.append(
                {
                    "case": case["id"],
                    "requiredEvidence": len(case["required"]),
                    "foundEvidence": hit,
                    "evidenceRecall": hit / len(case["required"]),
                    "outputChars": report["outputChars"],
                    "selectedFullFileChars": report["selectedFullFileChars"],
                    "eligibleSourceChars": report["eligibleSourceChars"],
                    "reductionVsSelectedFilesPct": report["reductionVsSelectedFilesPct"],
                    "reductionVsEligibleCorpusPct": report["reductionVsEligibleCorpusPct"],
                }
            )
            if case["id"] == "session-expiry":
                (destination / "context-pack.md").write_text(output, encoding="utf-8")
                # Remove machine-local timing; the report is reproducible across platforms.
                report.pop("elapsedMs")
                (destination / "pack-report.json").write_text(
                    json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
        noisy = "\n".join(
            ["INFO service heartbeat healthy"] * 1800
            + [
                "ERROR UploadOffset mismatch: expected 4096, received 8192",
                "  at validate_upload_offset (media/upload.py:104)",
                "AssertionError: retry must preserve previous bytes",
            ]
            + ["INFO service heartbeat healthy"] * 200
        )
        reduced, log_report = digest_log(noisy, max_chars=2500)
        (destination / "log-digest.md").write_text(reduced, encoding="utf-8")
        preserved = all(
            s in reduced
            for s in (
                "UploadOffset mismatch",
                "media/upload.py:104",
                "retry must preserve previous bytes",
            )
        )
    data = {
        "schemaVersion": 1,
        "benchmark": "Synthetic ShopCore / 30 source files / 5 labelled queries",
        "methodology": "Same deterministic source corpus for every run. Baselines: all eligible text, and full text of selected files. Context includes labels and warnings. No model was called.",
        "cases": results,
        "evidenceRecall": sum(r["foundEvidence"] for r in results)
        / sum(r["requiredEvidence"] for r in results),
        "log": {**log_report, "requiredEvidencePreserved": preserved},
        "limitations": [
            "Lexical retrieval on synthetic data; not representative of every codebase.",
            "Does not prove equal bug-fixing quality, actual token savings or reduced subscription usage.",
            "The full-corpus baseline is deliberately broad; compare selected-file baseline too.",
        ],
    }
    (destination / "benchmark.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return data
