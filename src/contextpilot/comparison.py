"""Paired offline retrieval evidence. Does not execute an agent or infer coding success."""

from .engine import pack


def compare(
    root, query, max_chars=6000, max_files=5, expected_files=(), evidence=(), encoding=None
):
    results = {}
    for name, dependencies in (("lexical", False), ("dependency-aware", True)):
        output, report = pack(
            root, query, max_chars, max_files, dependencies=dependencies, encoding=encoding
        )
        paths = {r["path"] for r in report["selected"]}
        checks = {path: path in paths for path in expected_files}
        markers = {text: text in output for text in evidence}
        values = list(checks.values()) + list(markers.values())
        results[name] = {
            "outputChars": len(output),
            "selected": [r["path"] for r in report["selected"]],
            "requiredFiles": checks,
            "requiredMarkers": markers,
            "evidenceRecall": sum(values) / len(values) if values else None,
            "tokenization": report.get("tokenization"),
        }
    return {
        "query": query,
        "budgetChars": max_chars,
        "maxFiles": max_files,
        "modes": results,
        "scope": "Paired retrieval with explicit evidence labels only. No agent, hidden coding tests, reasoning tokens, or Codex quota was measured.",
    }
