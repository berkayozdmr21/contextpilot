import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.previous_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = str(self.root.parent)
        (self.root / "source.py").write_text(
            "def upload_offset():\n    return 4096\n", encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_ceiling is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = self.previous_ceiling

    def call(self, *args, status=0, input=None):
        env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
        r = subprocess.run(
            [sys.executable, "-m", "contextpilot", *args],
            env=env,
            input=input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        self.assertEqual(r.returncode, status, r.stderr)
        return r

    def test_pack_search_scan_report_end_to_end(self):
        root = str(self.root)
        self.assertEqual(
            json.loads(self.call("scan", "--root", root).stdout)["discovery"], "filesystem"
        )
        self.assertEqual(
            json.loads(self.call("search", "upload offset", "--root", root).stdout)[0]["path"],
            "source.py",
        )
        r = json.loads(self.call("pack", "upload offset", "--root", root, "--json").stdout)
        self.assertIn("upload_offset", r["context"])
        self.assertEqual(
            json.loads(self.call("report", "--root", root).stdout)["outputChars"], len(r["context"])
        )
        target = self.root / "report.html"
        self.call("report", "--root", root, "--html", str(target))
        self.assertIn("ContextPilot", target.read_text(encoding="utf-8"))
        self.call("report", "--root", root, "--html", str(target), status=2)

    def test_stdin_digest_does_not_mix_json_and_status(self):
        r = self.call("digest", "-", "--json", input="INFO start\nERROR bad offset\n")
        self.assertIn("bad offset", json.loads(r.stdout)["context"])
        self.assertEqual(r.stderr, "")

    def test_checkpoint_and_changes_commands(self):
        root = str(self.root)
        self.call("checkpoint", "--root", root, "--task", "Upload", "--next", "Check hash")
        self.assertIn("Check hash", self.call("recall", "--root", root).stdout)
        self.call("changes", "--root", root, status=2)
        self.call("snapshot", "--root", root)
        (self.root / "source.py").write_text("def upload_offset():\n    return 8192")
        self.assertEqual(
            json.loads(self.call("changes", "--root", root).stdout)["modified"], ["source.py"]
        )

    def test_bad_root_and_budget_exit_with_actionable_message(self):
        self.assertIn(
            "not a directory",
            self.call("scan", "--root", str(self.root / "missing"), status=2).stderr,
        )
        self.assertIn(
            "max-chars",
            self.call(
                "pack", "upload", "--root", str(self.root), "--max-chars", "9", status=2
            ).stderr,
        )

    def test_skill_installs_self_contained_and_never_overwrites(self):
        destination = self.root / "skills/contextpilot"
        command = [
            sys.executable,
            str(REPO / "scripts/install_skill.py"),
            "--destination",
            str(destination),
        ]
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        r = subprocess.run(
            [
                sys.executable,
                str(destination / "scripts/run.py"),
                "pack",
                "upload offset",
                "--root",
                str(self.root),
                "--json",
            ],
            cwd=self.root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("upload_offset", json.loads(r.stdout)["context"])
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertTrue((destination / "installation.json").exists())

    def test_repo_skill_launcher_works_without_package_install(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        r = subprocess.run(
            [sys.executable, str(REPO / "skills/contextpilot/scripts/run.py"), "--version"],
            env=env,
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0.2.0", r.stdout)


if __name__ == "__main__":
    unittest.main()
