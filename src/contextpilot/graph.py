"""Bounded local import graph. No module execution, language server, or network."""

import ast
import posixpath
import re
from pathlib import PurePosixPath


def is_test(path):
    p = PurePosixPath(path)
    name = p.name.lower()
    return any(s.lower() in {"test", "tests", "__tests__"} for s in p.parts) or bool(
        re.search(r"(?:^test_|_test\.|\.test\.|\.spec\.|tests?\.cs$)", name)
    )


def build_graph(index):
    files = index["files"]
    modules = {}
    for path in files:
        if path.endswith(".py"):
            parts = list(PurePosixPath(path).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            names = [".".join(parts)]
            if parts and parts[0] in {"src", "lib"}:
                names.append(".".join(parts[1:]))
            for name in names:
                modules.setdefault(name, set()).add(path)
    types = {}
    for path, entry in files.items():
        if path.endswith(".cs"):
            for name in re.findall(
                r"\b(?:class|interface|record|struct|enum)\s+(\w+)", entry["text"]
            ):
                types.setdefault(name, set()).add(path)
    edges = []
    edge_keys = set()
    diagnostics = []

    def add(source, target, kind, line, symbol):
        if target != source:
            edge = {
                "source": source,
                "target": target,
                "kind": kind,
                "line": line,
                "symbol": symbol,
            }
            key = (source, target, kind, symbol)
            if key not in edge_keys:
                edges.append(edge)
                edge_keys.add(key)

    def python_module(source, name, line):
        matches = modules.get(name, set())
        if len(matches) == 1:
            add(source, next(iter(matches)), "python-import", line, name)
        elif len(matches) > 1:
            diagnostics.append(
                {"path": source, "line": line, "reason": "ambiguous module", "symbol": name}
            )

    for path, entry in sorted(files.items()):
        text = entry["text"]
        if path.endswith(".py"):
            try:
                tree = ast.parse(text)
            except (SyntaxError, ValueError, RecursionError):
                diagnostics.append(
                    {"path": path, "reason": "Python parse failed; no import edges inferred"}
                )
                continue
            for node in list(ast.walk(tree)):
                if isinstance(node, ast.Import):
                    for item in node.names[:50]:
                        python_module(path, item.name, node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    prefix = list(PurePosixPath(path).parent.parts)
                    if node.level:
                        if node.level > len(prefix):
                            continue
                        prefix = prefix[: len(prefix) - node.level + 1]
                        if prefix and prefix[0] in {"src", "lib"}:
                            prefix = prefix[1:]
                        module = ".".join(prefix + ([node.module] if node.module else []))
                    else:
                        module = node.module or ""
                    python_module(path, module, node.lineno)
                    for item in node.names[:50]:
                        python_module(path, module + "." + item.name, node.lineno)
        elif PurePosixPath(path).suffix in {".ts", ".tsx", ".js", ".jsx", ".dart"}:
            # Deliberately only relative static strings. Aliases, package imports and comments
            # are not language-server resolved; edges are labelled heuristic evidence.
            pattern = r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*|\bexport\s+[^;\n]*?from\s*)['"]([^'"\n]+)['"]"""
            for match in list(re.finditer(pattern, text))[:100]:
                spec = match.group(1)
                if not spec.startswith(".") and not (path.endswith(".dart") and ":" not in spec):
                    continue
                target = posixpath.normpath(posixpath.join(str(PurePosixPath(path).parent), spec))
                if target.startswith("../") or target.startswith("/"):
                    continue
                candidates = [target]
                if target.endswith(".js"):
                    candidates += [target[:-3] + ".ts", target[:-3] + ".tsx"]
                candidates += [
                    target + s
                    for s in (
                        ".ts",
                        ".tsx",
                        ".js",
                        ".jsx",
                        ".dart",
                        "/index.ts",
                        "/index.tsx",
                        "/index.js",
                    )
                ]
                matches = [p for p in dict.fromkeys(candidates) if p in files]
                if matches:
                    add(
                        path,
                        matches[0],
                        "relative-import-heuristic",
                        text[: match.start()].count("\n") + 1,
                        spec,
                    )
        elif path.endswith(".cs"):
            for number, line in enumerate(text.splitlines(), 1):
                for symbol in set(re.findall(r"\b[A-Z]\w*\b", line)):
                    matches = types.get(symbol, set())
                    if len(matches) == 1:
                        add(path, next(iter(matches)), "csharp-type-heuristic", number, symbol)
    return {
        "nodes": sorted(files),
        "edges": sorted(edges, key=lambda e: (e["source"], e["target"], e["line"])),
        "diagnostics": diagnostics[:100],
        "scope": "Python AST imports; relative JS/TS/Dart imports and unique C# type references are heuristics. No complete call graph.",
    }


def expand_candidates(index, ranked, max_files):
    """Reserve space for seed context, one-hop dependencies and their importing tests."""
    graph = build_graph(index)
    if not ranked:
        return [], graph
    seed_pool = [r for r in ranked if not is_test(r["path"])] or ranked
    seeds = seed_pool[: max(1, min(3, max_files // 3))]
    candidates = []
    seen = set()

    def append(path, reason, score, matched=None):
        if path not in seen:
            candidates.append(
                {"path": path, "score": score, "matched": matched or [], "reason": reason}
            )
            seen.add(path)

    for r in seeds:
        append(r["path"], "lexical-seed", r["score"], r["matched"])
    # Breadth first: one dependency per seed before a second dependency from the same file.
    neighbors = []
    for seed in seeds:
        linked = sorted({e["target"] for e in graph["edges"] if e["source"] == seed["path"]})
        neighbors.append([(p, "dependency of " + seed["path"]) for p in linked])
    for i in range(max((len(n) for n in neighbors), default=0)):
        for group in neighbors:
            if i < len(group):
                p, reason = group[i]
                append(p, reason, 0)
    context = set(seen)
    related_tests = sorted(
        {e["source"] for e in graph["edges"] if e["target"] in context and is_test(e["source"])}
    )
    # Test evidence is placed before additional dependencies when the budget is tight.
    seed_count = len(seeds)
    extras = candidates[seed_count:]
    candidates = candidates[:seed_count]
    for p in related_tests:
        if p not in {c["path"] for c in candidates}:
            candidates.append(
                {"path": p, "score": 0, "matched": [], "reason": "test importing selected context"}
            )
    candidates += [r for r in extras if r["path"] not in {c["path"] for c in candidates}]
    for r in ranked:
        if r["path"] not in {c["path"] for c in candidates}:
            candidates.append({**r, "reason": "lexical-match"})
    return candidates[:max_files], graph
