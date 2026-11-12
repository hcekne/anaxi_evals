"""Contract tests for the eval corpus CLI; these do not run the benchmark."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit


REPOSITORY = Path(__file__).resolve().parents[1]
TOOL = REPOSITORY / "tools" / "evals.py"


class CorpusCliTests(unittest.TestCase):
    def invoke(self, *args, root=REPOSITORY, success=True):
        result = subprocess.run(
            [sys.executable, str(TOOL), "--root", str(root), *map(str, args)],
            text=True,
            capture_output=True,
            cwd=REPOSITORY,
            timeout=20,
            check=False,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def copy_corpus(self, temporary_directory):
        destination = Path(temporary_directory) / "corpus"
        shutil.copytree(
            REPOSITORY,
            destination,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return destination

    def read_catalog(self, root=REPOSITORY):
        return json.loads((root / "catalog.json").read_text(encoding="utf-8"))

    def test_checked_in_corpus_validates(self):
        self.invoke("validate")

    def test_discovery_returns_catalog_scenarios(self):
        result = self.invoke("list", "--json")
        scenarios = json.loads(result.stdout)
        self.assertEqual(scenarios, self.read_catalog()["scenarios"])
        self.assertEqual(
            {entry["id"] for entry in scenarios},
            {"relaydesk", "dispatchledger", "caseflow"},
        )

    def test_each_prompt_returns_only_the_current_user_request(self):
        records = [
            json.loads(line)
            for line in (REPOSITORY / "requests.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(records), 48)
        for record in records:
            with self.subTest(scenario=record["scenario"], step=record["step"]):
                result = self.invoke("prompt", record["scenario"], record["step"])
                self.assertEqual(result.stdout, record["user_prompt"] + "\n")
                structured = self.invoke(
                    "prompt", record["scenario"], record["step"], "--json"
                )
                self.assertEqual(json.loads(structured.stdout), record)

    def test_unknown_scenarios_and_invalid_steps_are_rejected(self):
        for scenario, step in [
            ("unknown", "0"),
            ("../relaydesk", "0"),
            ("relaydesk", "-1"),
            ("relaydesk", "16"),
            ("relaydesk", "not-a-number"),
        ]:
            with self.subTest(scenario=scenario, step=step):
                result = self.invoke("prompt", scenario, step, success=False)
                self.assertEqual(result.stdout, "")

    def test_queue_drift_is_detected_and_sync_repairs_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.copy_corpus(temporary_directory)
            queue = root / "requests.jsonl"
            records = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
            records[0]["user_prompt"] = "This is a stale generated prompt."
            queue.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
            self.invoke("validate", root=root, success=False)
            self.invoke("sync", root=root)
            self.invoke("validate", root=root)
            self.assertEqual(queue.read_bytes(), (REPOSITORY / "requests.jsonl").read_bytes())

    def test_duplicate_and_missing_numbered_requests_are_rejected(self):
        for original, replacement in [("### 01 —", "### 00 —"), ("### 07 —", "### 17 —")]:
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as temporary_directory:
                root = self.copy_corpus(temporary_directory)
                spec = root / "evals" / "relaydesk" / "spec.md"
                source = spec.read_text(encoding="utf-8")
                self.assertIn(original, source)
                spec.write_text(source.replace(original, replacement, 1), encoding="utf-8")
                self.invoke("validate", root=root, success=False)

    def test_missing_files_and_charter_drift_are_rejected(self):
        for change in ["missing", "changed"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary_directory:
                root = self.copy_corpus(temporary_directory)
                charter = root / "shared" / "charter.md"
                if change == "missing":
                    charter.unlink()
                else:
                    charter.write_text(charter.read_text(encoding="utf-8") + "\nExtra treatment advice.\n", encoding="utf-8")
                self.invoke("validate", root=root, success=False)

    def test_unresolved_wiki_and_local_links_are_rejected(self):
        for invalid_link in ["[[Unshipped workspace note]]", "[Missing](missing-file.md)"]:
            with self.subTest(link=invalid_link), tempfile.TemporaryDirectory() as temporary_directory:
                root = self.copy_corpus(temporary_directory)
                spec = root / "evals" / "relaydesk" / "spec.md"
                spec.write_text(spec.read_text(encoding="utf-8") + "\n" + invalid_link + "\n", encoding="utf-8")
                self.invoke("validate", root=root, success=False)

    def test_catalog_path_escape_is_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.copy_corpus(temporary_directory)
            outside = Path(temporary_directory) / "outside.md"
            outside.write_text("Do not read or overwrite this file.\n", encoding="utf-8")
            catalog = self.read_catalog(root)
            catalog["scenarios"][0]["spec"] = "../outside.md"
            (root / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
            self.invoke("validate", root=root, success=False)
            output = Path(temporary_directory) / "bundle"
            self.invoke("export", "relaydesk", "--output", output, root=root, success=False)
            self.assertFalse(output.exists())
            self.assertEqual(outside.read_text(encoding="utf-8"), "Do not read or overwrite this file.\n")

    def test_export_is_identified_and_payload_hashes_are_verifiable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "relaydesk"
            self.invoke("export", "relaydesk", "--output", output)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"README.md", "spec.md", "requests.jsonl", "protocol.md", "charter.md", "scenario.json", "manifest.json"},
            )
            records = [json.loads(line) for line in (output / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([record["step"] for record in records], list(range(16)))
            self.assertEqual({record["scenario"] for record in records}, {"relaydesk"})
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["audience"], "operator-only")
            self.assertEqual(manifest["suite_version"], self.read_catalog()["suite_version"])
            self.assertEqual(set(manifest["files"]), {path.name for path in output.iterdir()} - {"manifest.json"})
            for name, expected_hash in manifest["files"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected_hash)

    def test_export_never_overwrites_an_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("Keep this work.\n", encoding="utf-8")
            self.invoke("export", "relaydesk", "--output", output, success=False)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "Keep this work.\n")
            self.assertEqual({path.name for path in output.iterdir()}, {"keep.txt"})

    def test_exported_markdown_navigation_is_self_contained(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            for scenario in self.read_catalog()["scenarios"]:
                with self.subTest(scenario=scenario["id"]):
                    output = Path(temporary_directory) / scenario["id"]
                    self.invoke("export", scenario["id"], "--output", output)
                    for document in output.glob("*.md"):
                        source = document.read_text(encoding="utf-8")
                        self.assertNotRegex(source, r"\[\[[^\]]+\]\]")
                        for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", source):
                            parsed = urlsplit(target.strip().strip("<>"))
                            if parsed.scheme or parsed.netloc or not parsed.path:
                                continue
                            destination = (document.parent / unquote(parsed.path)).resolve()
                            self.assertTrue(destination.is_relative_to(output), (document.name, target))
                            self.assertTrue(destination.exists(), (document.name, target))


if __name__ == "__main__":
    unittest.main()
