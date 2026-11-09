import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from contextpilot.benchmark import run_benchmark

parser = argparse.ArgumentParser(
    description="Reproduce labelled synthetic retrieval and log benchmarks."
)
parser.add_argument("--output", default="examples/results")
args = parser.parse_args()
data = run_benchmark(args.output)
print(json.dumps(data, indent=2, ensure_ascii=False))
if data["evidenceRecall"] != 1 or not data["log"]["requiredEvidencePreserved"]:
    raise SystemExit("Benchmark evidence check failed")
