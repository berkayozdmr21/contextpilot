"""Paired offline context evidence and acknowledged-session traffic, with optional encoding."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from contextpilot.benchmark import isolate_fixture
from contextpilot.comparison import compare
from contextpilot.engine import pack
from contextpilot.sessions import create, acknowledge

CASES = [
    (
        "python-local",
        {
            "app/service.py": "from .policy import allowed_region\n\ndef schedule_dispatch(zone):\n    return allowed_region(zone)\n",
            "app/policy.py": 'def allowed_region(zone):\n    return zone in {"north", "south"}\n',
            "tests/test_dispatch.py": 'from app.service import schedule_dispatch\n\ndef test_delivery():\n    assert schedule_dispatch("north")\n',
        },
        "schedule_dispatch",
        "app/policy.py",
        "return zone in",
        True,
    ),
    (
        "typescript-local",
        {
            "web/service.ts": 'import { allowedRegion } from "./policy";\nexport function scheduleDispatch(zone: string) { return allowedRegion(zone); }\n',
            "web/policy.ts": 'export function allowedRegion(zone: string) { return ["north", "south"].includes(zone); }\n',
            "web/service.test.ts": 'import { scheduleDispatch } from "./service";\nconst outcome = scheduleDispatch("north");\n',
        },
        "scheduleDispatch",
        "web/policy.ts",
        "includes(zone)",
        True,
    ),
    (
        "dart-local",
        {
            "lib/service.dart": "import 'policy.dart';\nbool scheduleDispatch(String zone) => allowedRegion(zone);\n",
            "lib/policy.dart": "bool allowedRegion(String zone) => ['north', 'south'].contains(zone);\n",
            "test/service_test.dart": "import '../lib/service.dart';\nvoid main() { scheduleDispatch('north'); }\n",
        },
        "scheduleDispatch",
        "lib/policy.dart",
        "contains(zone)",
        True,
    ),
    (
        "csharp-local",
        {
            "Api/Controller.cs": "public class Controller { public bool ScheduleDispatch(string zone) => new RegionPolicy().Allow(zone); }\n",
            "Core/RegionPolicy.cs": 'public class RegionPolicy { public bool Allow(string zone) => zone == "north"; }\n',
            "Tests/ControllerTests.cs": 'public class ControllerTests { bool Check() => new Controller().ScheduleDispatch("north"); }\n',
        },
        "ScheduleDispatch",
        "Core/RegionPolicy.cs",
        'zone == "north"',
        True,
    ),
    (
        "known-one-hop-limit",
        {
            "app/service.py": "from .bridge import allowed\n\ndef schedule_dispatch(zone): return allowed(zone)\n",
            "app/bridge.py": "from .policy import region\ndef allowed(zone): return region(zone)\n",
            "app/policy.py": 'def region(zone): return zone == "north"\n',
        },
        "schedule_dispatch",
        "app/policy.py",
        'zone == "north"',
        False,
    ),
]


def run(destination, encoding=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for case_id, files, query, dependency, marker, supported in CASES:
        with tempfile.TemporaryDirectory(prefix="contextpilot-paired-") as directory:
            corpus = Path(directory)
            isolate_fixture(corpus)
            for path, text in files.items():
                target = corpus / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            result = compare(corpus, query, 6000, 4, [dependency], [marker], encoding)
            results.append({"case": case_id, "withinSupportedOneHopScope": supported, **result})
    with tempfile.TemporaryDirectory(prefix="contextpilot-session-") as directory:
        corpus = Path(directory)
        isolate_fixture(corpus)
        prefix = "\n".join(
            "# Context documentation " + ("stable background " * 10) for _ in range(5)
        )
        suffix = "\n".join("# Supporting context " + ("additional detail " * 10) for _ in range(3))
        source = prefix + "\ndef compute_total():\n    return 42\n" + suffix + "\n"
        target = corpus / "logic.py"
        target.write_text(source, encoding="utf-8")
        create(corpus, "benchmark-chat")
        first, r1 = pack(
            corpus, "compute_total", 6000, 1, encoding=encoding, session="benchmark-chat"
        )
        acknowledge(corpus, "benchmark-chat", r1["session"]["receipt"])
        unchanged, r2 = pack(
            corpus, "compute_total", 6000, 1, encoding=encoding, session="benchmark-chat"
        )
        target.write_text(source.replace("return 42", "return 84"), encoding="utf-8")
        changed, r3 = pack(
            corpus, "compute_total", 6000, 1, encoding=encoding, session="benchmark-chat"
        )
        session = {
            "initialChars": len(first),
            "unchangedChars": len(unchanged),
            "changedChars": len(changed),
            "unchangedIsReference": r2["selected"][0].get("deltaKind") == "unchanged",
            "changeEvidencePreserved": "-    return 42" in changed and "+    return 84" in changed,
            "encoding": encoding,
            "initialTextTokens": r1.get("tokenization", {}).get("textTokens"),
            "unchangedTextTokens": r2.get("tokenization", {}).get("textTokens"),
            "changedTextTokens": r3.get("tokenization", {}).get("textTokens"),
            "scope": "Requires a complete, explicitly acknowledged baseline retained in this same chat. New chats send full context.",
        }
    data = {
        "schemaVersion": 1,
        "encoding": encoding,
        "cases": results,
        "session": session,
        "scope": "Small labelled retrieval fixtures, not paired agent runs or bug-fixing success. Larger context can improve evidence recall without saving tokens. One known one-hop limitation is included rather than hidden.",
    }
    (destination / "paired-benchmark.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="examples/results")
    parser.add_argument("--encoding", choices=("o200k_base", "cl100k_base", "p50k_base"))
    args = parser.parse_args()
    data = run(args.output, args.encoding)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if not all(
        r["modes"]["dependency-aware"]["evidenceRecall"] == 1
        for r in data["cases"]
        if r["withinSupportedOneHopScope"]
    ):
        raise SystemExit("Supported one-hop evidence missing")
    if (
        not data["session"]["changeEvidencePreserved"]
        or not data["session"]["unchangedIsReference"]
    ):
        raise SystemExit("Acknowledged session evidence check failed")
