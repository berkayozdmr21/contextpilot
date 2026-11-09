import importlib.util
import json
import os
import subprocess
import sys
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from contextpilot.engine import pack, scan, rank
from contextpilot.graph import build_graph, expand_candidates, is_test
from contextpilot.sessions import create, acknowledge, load, session_path
from contextpilot.comparison import compare


class LocalFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.previous_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = str(self.root.parent)

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_ceiling is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = self.previous_ceiling

    def put(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def service(self):
        self.put(
            "app/service.py",
            "from .policy import valid_window\n\ndef schedule_dispatch(zone):\n    return valid_window(zone)\n",
        )
        self.put(
            "app/policy.py", 'def valid_window(zone):\n    return zone in {"north", "south"}\n'
        )
        self.put(
            "tests/test_dispatch.py",
            'from app.service import schedule_dispatch\n\ndef test_delivery():\n    assert schedule_dispatch("north")\n',
        )


class Dependencies(LocalFixture):
    def test_python_relative_import_and_test_expansion(self):
        self.service()
        index = scan(self.root)
        graph = build_graph(index)
        self.assertTrue(
            any(
                e["source"] == "app/service.py" and e["target"] == "app/policy.py"
                for e in graph["edges"]
            )
        )
        output, report = pack(self.root, "schedule_dispatch", 6000, 4, dependencies=True)
        self.assertEqual(
            {r["path"] for r in report["selected"]},
            {"app/service.py", "app/policy.py", "tests/test_dispatch.py"},
        )
        self.assertIn("return zone in", output)
        self.assertIn("Selection: dependency of", output)

    def test_python_from_package_import_and_parent_level(self):
        self.put("src/pkg/utils.py", "value=1\n")
        self.put("src/pkg/sub/handler.py", "from .. import utils\n")
        graph = build_graph(scan(self.root))
        self.assertTrue(any(e["target"] == "src/pkg/utils.py" for e in graph["edges"]))

    def test_relative_typescript_and_javascript_alias(self):
        self.put("web/main.ts", 'import { calc } from "./calc.js";\nexport { theme } from "./ui";')
        self.put("web/calc.ts", "export const calc=1;")
        self.put("web/ui/index.ts", "export const theme=1;")
        graph = build_graph(scan(self.root))
        self.assertEqual({e["target"] for e in graph["edges"]}, {"web/calc.ts", "web/ui/index.ts"})

    def test_dart_local_import(self):
        self.put("lib/screen.dart", "import 'widgets/card.dart';\n")
        self.put("lib/widgets/card.dart", "class Card {}")
        self.assertEqual(
            build_graph(scan(self.root))["edges"][0]["target"], "lib/widgets/card.dart"
        )

    def test_unique_csharp_type_reference_and_ambiguity(self):
        self.put("Core/Invoice.cs", "public class Invoice {}")
        self.put("Api/Handler.cs", "public class Handler { Invoice Calculate() => new Invoice(); }")
        graph = build_graph(scan(self.root))
        self.assertTrue(any(e["target"] == "Core/Invoice.cs" for e in graph["edges"]))
        self.put("Other/Invoice.cs", "public class Invoice {}")
        self.assertFalse(
            any(e["target"] == "Core/Invoice.cs" for e in build_graph(scan(self.root))["edges"])
        )

    def test_cycle_does_not_expand_forever_or_duplicate_files(self):
        self.put("a.py", "import b\ndef execute_cycle(): return 1")
        self.put("b.py", "import a\nvalue=1")
        _, report = pack(self.root, "execute_cycle", 4000, 8, dependencies=True)
        paths = [r["path"] for r in report["selected"]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(paths), {"a.py", "b.py"})

    def test_secret_exclusion_cannot_be_bypassed_by_import(self):
        self.put("main.py", "import credentials\ndef execute(): pass")
        self.put("credentials.py", "hidden_value=1234")
        output, report = pack(self.root, "execute", 4000, 5, dependencies=True)
        self.assertNotIn("hidden_value", output)
        self.assertNotIn("credentials.py", {r["path"] for r in report["selected"]})

    def test_invalid_python_is_diagnostic_not_execution(self):
        self.put("broken.py", "def syntax(:\n")
        graph = build_graph(scan(self.root))
        self.assertTrue(graph["diagnostics"])

    def test_paired_comparison_exposes_missing_lexical_dependency(self):
        self.service()
        result = compare(
            self.root,
            "schedule_dispatch",
            6000,
            4,
            expected_files=["app/service.py", "app/policy.py", "tests/test_dispatch.py"],
            evidence=["return zone in"],
        )
        self.assertLess(result["modes"]["lexical"]["evidenceRecall"], 1)
        self.assertEqual(result["modes"]["dependency-aware"]["evidenceRecall"], 1)


class ContextSessions(LocalFixture):
    def test_corrupt_session_schema_is_actionable(self):
        create(self.root, "chat1")
        session_path(self.root, "chat1").write_text("[]")
        with self.assertRaises(ValueError):
            load(self.root, "chat1")

    def file(self):
        return self.put("logic.py", "def compute_total():\n    return 42\n")

    def test_no_reference_until_explicit_acknowledgement(self):
        self.file()
        create(self.root, "chat1")
        first, r = pack(self.root, "compute_total", 3000, 2, session="chat1")
        second, _ = pack(self.root, "compute_total", 3000, 2, session="chat1")
        self.assertIn("return 42", first)
        self.assertIn("return 42", second)
        with self.assertRaises(ValueError):
            acknowledge(self.root, "chat1", r["session"]["receipt"])

    def test_acknowledged_complete_file_can_be_reference_only(self):
        self.file()
        create(self.root, "chat1")
        _, r = pack(self.root, "compute_total", 3000, 2, session="chat1")
        acknowledge(self.root, "chat1", r["session"]["receipt"])
        output, r = pack(self.root, "compute_total", 3000, 2, session="chat1")
        self.assertIn("Previously acknowledged COMPLETE", output)
        self.assertNotIn("return 42", output)
        self.assertEqual(r["selected"][0]["deltaKind"], "unchanged")

    def test_changed_file_returns_unified_diff_against_acknowledged_text(self):
        p = self.file()
        create(self.root, "chat1")
        _, r = pack(self.root, "compute_total", 3000, 2, session="chat1")
        acknowledge(self.root, "chat1", r["session"]["receipt"])
        p.write_text("def compute_total():\n    return 99\n")
        output, r = pack(self.root, "compute_total", 3000, 2, session="chat1")
        self.assertIn("-    return 42", output)
        self.assertIn("+    return 99", output)
        self.assertEqual(r["selected"][0]["deltaKind"], "changed")

    def test_partial_file_never_becomes_acknowledged_complete(self):
        self.put(
            "big.py",
            "\n".join(["# filler"] * 100 + ["def compute_total(): return 42"] + ["# filler"] * 100),
        )
        create(self.root, "chat1")
        _, r = pack(self.root, "compute_total", 1500, 2, session="chat1")
        result = acknowledge(self.root, "chat1", r["session"]["receipt"])
        self.assertEqual(result["acknowledgedFiles"], 0)

    def test_new_session_has_no_inherited_memory(self):
        self.file()
        create(self.root, "old")
        _, r = pack(self.root, "compute_total", 3000, 2, session="old")
        acknowledge(self.root, "old", r["session"]["receipt"])
        create(self.root, "fresh")
        output, _ = pack(self.root, "compute_total", 3000, 2, session="fresh")
        self.assertIn("return 42", output)

    def test_expiry_and_bad_ids_are_rejected(self):
        create(self.root, "chat1")
        with patch("contextpilot.sessions.time.time", return_value=time.time() + 20000):
            with self.assertRaises(ValueError):
                load(self.root, "chat1")
        with self.assertRaises(ValueError):
            create(self.root, "../escape")
        with self.assertRaises(ValueError):
            create(self.root, "chat1")

    def test_tampered_session_cannot_suppress_current_source(self):
        self.file()
        create(self.root, "chat1")
        _, r = pack(self.root, "compute_total", 3000, 2, session="chat1")
        acknowledge(self.root, "chat1", r["session"]["receipt"])
        path = session_path(self.root, "chat1")
        data = json.loads(path.read_text())
        data["acknowledged"]["logic.py"]["text"] = "fake"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            pack(self.root, "compute_total", 3000, 2, session="chat1")

    def test_diff_preserves_no_final_newline_markers(self):
        p = self.put("logic.py", "def compute_total(): return 42")
        create(self.root, "chat1")
        _, r = pack(self.root, "compute_total", 3000, 2, session="chat1")
        acknowledge(self.root, "chat1", r["session"]["receipt"])
        p.write_text("def compute_total(): return 99")
        output, _ = pack(self.root, "compute_total", 3000, 2, session="chat1")
        self.assertIn("\\ No newline at end of file", output)
        self.assertIn("+def compute_total(): return 99", output)


class SkillUpdates(LocalFixture):
    def installer(self):
        path = Path(__file__).resolve().parents[1] / "scripts/install_skill.py"
        spec = importlib.util.spec_from_file_location("cp_installer", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_owned_update_creates_verifiable_backup(self):
        installer = self.installer()
        dest = self.root / "contextpilot"
        installer.install(dest)
        original = (dest / "SKILL.md").read_bytes()
        backup = self.root / "backup"
        installer.install(dest, True, backup)
        self.assertEqual((backup / "SKILL.md").read_bytes(), original)
        self.assertEqual(json.loads((dest / "installation.json").read_text())["version"], "0.2.0")

    def test_locally_modified_skill_is_not_overwritten(self):
        installer = self.installer()
        dest = self.root / "contextpilot"
        installer.install(dest)
        (dest / "SKILL.md").write_text("my own changes")
        with self.assertRaises(ValueError):
            installer.install(dest, True, self.root / "backup")
        self.assertEqual((dest / "SKILL.md").read_text(), "my own changes")
        self.assertFalse((self.root / "backup").exists())

    def test_failed_update_restores_previous_managed_content(self):
        installer = self.installer()
        dest = self.root / "contextpilot"
        installer.install(dest)
        old = b"Previous managed skill\n"
        (dest / "SKILL.md").write_bytes(old)
        manifest = json.loads((dest / "installation.json").read_text())
        manifest["files"]["SKILL.md"] = hashlib.sha256(old).hexdigest()
        (dest / "installation.json").write_text(json.dumps(manifest))
        original = Path.replace
        calls = []

        def fail_once(path, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError("simulated write failure")
            return original(path, target)

        with patch.object(Path, "replace", fail_once):
            with self.assertRaises(OSError):
                installer.install(dest, True, self.root / "backup")
        self.assertEqual((dest / "SKILL.md").read_bytes(), old)

    def test_manifest_path_traversal_is_rejected(self):
        installer = self.installer()
        dest = self.root / "contextpilot"
        installer.install(dest)
        manifest = dest / "installation.json"
        data = json.loads(manifest.read_text())
        data["files"]["../outside"] = "x"
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            installer.install(dest, True, self.root / "backup")


class NewCommands(LocalFixture):
    def call(self, *args):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        r = subprocess.run(
            [sys.executable, "-m", "contextpilot", *args],
            env=env,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_graph_and_compare_cli(self):
        self.service()
        graph = self.call("graph", "--root", str(self.root), "--path", "app/service.py")
        self.assertIn("app/policy.py", graph["nodes"])
        result = self.call(
            "compare",
            "schedule_dispatch",
            "--root",
            str(self.root),
            "--expected-file",
            "app/policy.py",
        )
        self.assertTrue(result["modes"]["dependency-aware"]["requiredFiles"]["app/policy.py"])

    def test_session_cli_roundtrip(self):
        self.put("logic.py", "def compute_total(): return 42\n")
        self.call("session-start", "cli-chat", "--root", str(self.root))
        packet = self.call(
            "pack", "compute_total", "--root", str(self.root), "--session", "cli-chat", "--json"
        )
        acknowledged = self.call(
            "ack", "cli-chat", packet["report"]["session"]["receipt"], "--root", str(self.root)
        )
        self.assertEqual(acknowledged["acknowledgedFiles"], 1)


@unittest.skipUnless(importlib.util.find_spec("tiktoken"), "optional tokenizer extra not installed")
class TokenBudgets(LocalFixture):
    def test_count_cli_reports_exact_text_tokens(self):
        target = self.put("sample.txt", "Merhaba dünya")
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "contextpilot",
                "count",
                str(target),
                "--encoding",
                "o200k_base",
            ],
            env=env,
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["encoding"], "o200k_base")

    def test_exact_count_matches_explicit_encoding_even_for_special_token_strings(self):
        import tiktoken
        from contextpilot.tokenization import measurement

        text = "Merhaba dünya <|endoftext|>"
        self.assertEqual(
            measurement(text, "o200k_base")["textTokens"],
            len(tiktoken.get_encoding("o200k_base").encode(text, disallowed_special=())),
        )

    def test_pack_respects_both_token_and_character_budgets(self):
        self.put(
            "unicode.py",
            'def calculate():\n    return "'
            + ("日本語 dünya " * 60)
            + '"\n'
            + "# calculate\n" * 80,
        )
        for budget in (128, 256, 500):
            output, report = pack(
                self.root, "calculate", 2000, 2, encoding="o200k_base", max_tokens=budget
            )
            self.assertLessEqual(report["tokenization"]["textTokens"], budget)
            self.assertLessEqual(len(output), 2000)

    def test_missing_encoding_for_token_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            pack(self.root, "test", max_tokens=256)

    def test_unknown_encoding_does_not_fall_back_to_heuristics(self):
        from contextpilot.tokenization import counter

        with self.assertRaises(ValueError):
            counter("not-a-model-name")


class MissingTokenizer(LocalFixture):
    def test_missing_optional_extra_fails_instead_of_faking_an_exact_count(self):
        from contextpilot.tokenization import counter

        with patch.dict(sys.modules, {"tiktoken": None}):
            with self.assertRaisesRegex(ValueError, "Tokenizer extra"):
                counter("o200k_base")

    def test_token_labels_cannot_be_silently_omitted_for_tiny_budget(self):
        with self.assertRaises(ValueError):
            pack(self.root, "query " * 100, 2000, 2, encoding="o200k_base", max_tokens=128)
