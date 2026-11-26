import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.naacl2027 import public_wording_study as study


class PublicWordingProtocol(unittest.TestCase):
    def test_old_added_references_cannot_make_a_reused_question_new(self):
        question = "Why has my card payment not gone through?"
        previous = {study.normalized(question)}
        for wrapped in (question + " The reference is txn_ABC1234567.",
                        question + " (txn_ABC1234567)", "Re txn_ABC1234567: " + question,
                        "txn_ABC1234567 - " + question):
            self.assertEqual(study.overlap(study.normalized(wrapped), previous)["method"], "exact")
        self.assertIsNotNone(study.overlap(study.normalized("Why has my card payment not gone through yet?"), previous))

    def test_changed_or_added_runtime_source_invalidates_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "prior-questions.json").write_text("{}")
            (path / "protocol.json").write_text(json.dumps({"sources": {"finbot/a.py": "old"},
                "prior_sha256": study.sha(b"{}")}))
            with patch.object(study, "DATA", path), patch.object(study, "sources", return_value={"finbot/a.py": "new"}):
                with self.assertRaisesRegex(ValueError, "Frozen runtime"):
                    study.verify()
            with patch.object(study, "DATA", path), patch.object(study, "sources", return_value={"finbot/a.py": "old", "finbot/b.py": "extra"}):
                with self.assertRaisesRegex(ValueError, "Frozen runtime"):
                    study.verify()

    def test_changed_selected_questions_invalidate_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "protocol.json").write_text("{}")
            (path / "cases.json").write_text('{"cases": []}')
            (path / "selection.json").write_text(json.dumps({"cases_sha256": "old",
                "protocol_sha256": study.sha(b"{}")}))
            with patch.object(study, "DATA", path), patch.object(study, "verify", return_value={}):
                with self.assertRaisesRegex(ValueError, "Selected cases"):
                    study.verify_cases()


if __name__ == "__main__":
    unittest.main()
