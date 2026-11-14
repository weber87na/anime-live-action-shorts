"""Exercise the gate against real temporary manifests and file bytes."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "selection_gate.py"
SPEC = importlib.util.spec_from_file_location("selection_gate", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class SelectionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project.json"
        self.message = self.root / "message.txt"
        self.message.write_bytes("我選甲的 a2、乙的 b1，確認。\r\n".encode("utf-8"))
        self.data = {"schema_version": 1, "project_id": "casting-example", "style": {"look": "film"},
                     "characters": [], "selection_confirmation": None}
        for letter, name, selected in (("a", "甲", 2), ("b", "乙", 1)):
            character = {"id": letter, "name": name, "appearance": {"age": "adult"},
                         "candidates": [], "selected_candidate_id": f"{letter}{selected}"}
            for number in range(1, 4):
                cid = f"{letter}{number}"
                content = f"synthetic image {cid}".encode()
                (self.root / f"{cid}.png").write_bytes(content)
                character["candidates"].append({"id": cid, "path": f"{cid}.png",
                                                 "sha256": hashlib.sha256(content).hexdigest()})
            self.data["characters"].append(character)
        self.save()

    def save(self):
        self.project.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def call(self, *args):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = gate.main([str(arg) for arg in args])
        return code, json.loads(captured.getvalue())

    def confirm(self):
        code, result = self.call("confirm", self.project, "--message-file", self.message)
        self.assertEqual(code, 0, result)
        self.data = json.loads(self.project.read_text(encoding="utf-8"))

    def assert_rejected(self):
        code, result = self.call("check", self.project)
        self.assertEqual(code, 2, result)
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])
        return result

    def test_complete_mapping_and_exact_confirmation(self):
        self.data["characters"][1]["candidates"][0]["path"] = str(self.root / "b1.png")
        self.save()
        self.confirm()
        output = self.root / "approved.json"
        code, result = self.call("check", self.project, "--write-approved", output)
        self.assertEqual(code, 0, result)
        approved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(approved["source_project"], str(self.project.resolve()))
        self.assertEqual([item["candidate_id"] for item in approved["images"]], ["a2", "b1"])
        self.assertEqual(approved["selection_confirmation"]["user_message"], "我選甲的 a2、乙的 b1，確認。\r\n")
        for image in approved["images"]:
            self.assertTrue(Path(image["path"]).is_absolute())
            self.assertEqual(image["sha256"], hashlib.sha256(Path(image["path"]).read_bytes()).hexdigest())
        self.assertEqual(self.call("check", self.project, "--write-approved", output)[0], 0)

    def test_missing_and_partial_confirmation(self):
        self.assert_rejected()
        self.data["selection_confirmation"] = {"confirmed_by": "user"}
        self.save()
        self.assert_rejected()

    def test_fewer_than_three_candidates(self):
        self.data["characters"][0]["candidates"].pop()
        self.save()
        self.assertEqual(self.call("confirm", self.project, "--message-file", self.message)[0], 2)
        self.assertIsNone(json.loads(self.project.read_text(encoding="utf-8"))["selection_confirmation"])

    def test_duplicate_content_ids_and_paths(self):
        for duplicate in ("content", "id", "path"):
            with self.subTest(duplicate=duplicate):
                original = json.loads(json.dumps(self.data))
                first, second = self.data["characters"][0]["candidates"][:2]
                if duplicate == "content":
                    (self.root / second["path"]).write_bytes((self.root / first["path"]).read_bytes())
                    second["sha256"] = first["sha256"]
                else:
                    second[duplicate] = first[duplicate]
                self.save()
                self.assertEqual(self.call("confirm", self.project, "--message-file", self.message)[0], 2)
                self.data = original
                (self.root / "a2.png").write_bytes(b"synthetic image a2")

    def test_changed_selected_or_unselected_bytes(self):
        self.confirm()
        for filename in ("a2.png", "a3.png"):
            with self.subTest(filename=filename):
                path = self.root / filename
                original = path.read_bytes()
                path.write_bytes(b"changed image")
                self.assert_rejected()
                path.write_bytes(original)

    def test_changed_identity_and_choice(self):
        self.confirm()
        original = json.loads(json.dumps(self.data))
        changes = [lambda d: d["style"].update(look="anime"),
                   lambda d: d.update(project_id="other-project"),
                   lambda d: d["characters"][0].update(id="other-character"),
                   lambda d: d["characters"][0].update(name="new name"),
                   lambda d: d["characters"][0]["appearance"].update(age="elder"),
                   lambda d: d["characters"][0]["candidates"][2].update(id="other-candidate"),
                   lambda d: d["characters"][0]["candidates"][2].update(path=str(self.root / "a3.png")),
                   lambda d: d["characters"][0].update(selected_candidate_id="a1")]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.data = json.loads(json.dumps(original))
                change(self.data)
                self.save()
                self.assert_rejected()

    def test_modified_bytes_with_updated_hash_still_requires_confirmation(self):
        self.confirm()
        path = self.root / "a3.png"
        path.write_bytes(b"replacement")
        self.data["characters"][0]["candidates"][2]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()
        self.assert_rejected()

    def test_incomplete_selections_cannot_be_confirmed(self):
        self.data["characters"][1]["selected_candidate_id"] = None
        self.save()
        self.assertEqual(self.call("confirm", self.project, "--message-file", self.message)[0], 2)

    def test_empty_user_message_and_wrong_confirmation(self):
        self.message.write_text(" \n\t", encoding="utf-8")
        self.assertEqual(self.call("confirm", self.project, "--message-file", self.message)[0], 2)
        self.message.write_text("I select a2 and b1.", encoding="utf-8")
        self.confirm()
        original = dict(self.data["selection_confirmation"])
        for key, value in (("user_message", " "), ("confirmed_by", "agent"),
                           ("confirmed_at", "2026-01-01"), ("confirmed_at", "2026-01-01T12:00:00+08:00")):
            with self.subTest(key=key, value=value):
                self.data["selection_confirmation"] = {**original, key: value}
                self.save()
                self.assert_rejected()

    def test_postprocess_changes_preserve_confirmation(self):
        self.confirm()
        digest = self.data["selection_confirmation"]["selection_digest"]
        self.data.update(layout={"aspect": "9:16"}, music="song.mp3", duration=32.5)
        self.data["characters"][0]["duration"] = 4
        self.save()
        code, result = self.call("check", self.project)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["selection_digest"], digest)

    def test_failure_leaves_existing_output_untouched_and_reports_stale(self):
        self.confirm()
        output = self.root / "approved.json"
        self.assertEqual(self.call("check", self.project, "--write-approved", output)[0], 0)
        previous = output.read_bytes()
        (self.root / "b1.png").write_bytes(b"changed")
        code, result = self.call("check", self.project, "--write-approved", output)
        self.assertEqual(code, 2)
        self.assertTrue(result["approved_output"]["stale"])
        self.assertFalse(result["approved_output"]["written"])
        self.assertEqual(output.read_bytes(), previous)

    def test_unrelated_output_is_not_overwritten(self):
        self.confirm()
        output = self.root / "important.txt"
        output.write_bytes(b"keep me")
        self.assertEqual(self.call("check", self.project, "--write-approved", output)[0], 2)
        self.assertEqual(output.read_bytes(), b"keep me")
        before = self.project.read_bytes()
        self.assertEqual(self.call("check", self.project, "--write-approved", self.project)[0], 2)
        self.assertEqual(self.project.read_bytes(), before)

    def test_empty_missing_files_and_bad_json(self):
        self.confirm()
        (self.root / "a1.png").write_bytes(b"")
        self.assert_rejected()
        (self.root / "a1.png").unlink()
        self.assert_rejected()
        self.project.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
