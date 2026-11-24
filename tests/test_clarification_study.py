"""Study boundaries and count estimates, using explicitly simulated participant actions."""
import copy
import io
import json
import unittest

from finbot.clarification import UNKNOWN
from finbot.clarification_study import (
    PROTOCOL,
    catalogue,
    fit_model,
    run_study,
    session_setup,
    study_info,
    summarize,
    validate_model,
)
from finbot.demo import DemoApp


def request(phase="development", mode="rehearsal", code="P001"):
    return {"protocol": PROTOCOL, "participant_code": code, "phase": phase, "mode": mode,
            "consent": mode == "participant", "completed": [], "events": []}


def complete(req, model=None, *, reply_rule=None, selection_rule=None, financial=False):
    """Test oracle only; never used to manufacture participant evidence for analysis."""
    req = copy.deepcopy(req)
    tasks = {t.task_id: t for t in catalogue()[req["phase"]]}
    for _ in range(60):
        response = run_study(req, model, financial=financial)
        if response["done"]:
            return response["export"]
        current = response["current"]
        task = tasks[current["task_id"]]
        if current["can_finish"]:
            req["completed"].append({"task_id": task.task_id, "events": req["events"]})
            req["events"] = []
        elif current["pending"]:
            q = current["pending"]
            target = next((c for c in task.candidates if c.record_id == task.target), None)
            reply = target.attributes[q["template"]] if target else UNKNOWN
            if reply_rule:
                reply = reply_rule(task, q, reply)
            req["events"].append({"type": "reply", "template": q["template"], "text": reply})
        else:
            selected = selection_rule(task) if selection_rule else task.target
            req["events"].append({"type": "confirm", "record_id": selected} if selected else {"type": "unresolved"})
    raise AssertionError("Study did not terminate")


class StudyWorkflow(unittest.TestCase):
    def test_participant_payload_hides_outcomes_beliefs_and_model(self):
        result = run_study(request())
        wire = json.dumps(result)
        for field in ["target_id", "expected", "trace", "model_id", "probability", "strategy", "financial", "export"]:
            self.assertNotIn(f'"{field}"', wire)
        self.assertTrue(result["current"]["pending"])

    def test_no_answer_or_export_until_all_tasks_finished(self):
        exported = complete(request())
        req = exported["request"]
        req["completed"].pop()
        result = run_study(req)
        self.assertFalse(result["done"])
        self.assertNotIn("export", result)
        self.assertNotIn("financial", result["current"])

    def test_consent_and_frozen_model_required_for_participants(self):
        req = request(mode="participant")
        req["consent"] = False
        with self.assertRaisesRegex(ValueError, "consent"):
            run_study(req)
        with self.assertRaisesRegex(ValueError, "frozen participant"):
            run_study(request("evaluation", "participant"))

    def test_structured_replies_only_and_no_skipping_pending_probe(self):
        for event in [{"type": "reply", "template": "kind", "text": "maybe it is a transfer"},
                      {"type": "confirm", "record_id": "txn_DKIND0000"}, {"type": "unresolved"}]:
            req = request()
            req["events"] = [event]
            with self.subTest(event=event), self.assertRaises(ValueError):
                run_study(req)

    def test_foreign_record_and_out_of_order_completed_task_rejected(self):
        req = request()
        req["events"] = [{"type": "reply", "template": "kind", "text": UNKNOWN},
                         {"type": "confirm", "record_id": "txn_FOREIGN99"}]
        with self.assertRaises(ValueError):
            run_study(req)
        req = complete(request())["request"]
        req["completed"].reverse()
        with self.assertRaisesRegex(ValueError, "in order"):
            run_study(req)

    def test_task_reference_accuracy_separate_from_verifier_pass(self):
        result = complete(request("evaluation"), selection_rule=lambda t: t.candidates[0].record_id, financial=True)
        mixed = next(r for r in result["results"] if r["task_id"] == "eval-mixed")
        self.assertEqual(mixed["outcome"], "wrong_selection")
        self.assertEqual(mixed["financial"]["outcome"], "passed")
        self.assertIn(mixed["selected_id"], mixed["financial"]["final"]["answer"])

    def test_absent_or_indistinguishable_targets_remain_unresolved(self):
        result = complete(request("evaluation"), financial=True)
        for report in result["results"]:
            if report["target_id"] is None:
                self.assertEqual(report["outcome"], "appropriate_unresolved")
                self.assertIsNone(report["financial"])

    def test_correction_uses_only_final_record_evidence(self):
        export = complete(request("evaluation"))
        req = export["request"]
        entry = req["completed"][0]
        previous = entry["events"][-1]["record_id"]
        entry["events"].append({"type": "confirm", "record_id": "txn_EMIX0000"})
        report = run_study(req)["export"]["results"][0]
        self.assertEqual(report["corrections"], 1)
        self.assertNotIn(previous, json.dumps(report["financial"]))
        self.assertEqual(report["trace"][-1]["invalidated_record"], previous)

    def test_development_and_evaluation_structures_are_disjoint(self):
        families = {phase: {t.family for t in tasks} for phase, tasks in catalogue().items()}
        self.assertFalse(families["development"] & families["evaluation"])
        self.assertTrue(all(len(t.candidates) == 2 for t in catalogue()["development"]))
        self.assertEqual(len(catalogue()["evaluation"][0].candidates), 4)

    def test_allocation_and_order_repeat_for_same_participant(self):
        req = request(mode="participant")
        self.assertEqual(session_setup(req, None), session_setup(req, None))


class StudyAnalysis(unittest.TestCase):
    def test_consented_participant_protocol_unlocks_only_new_participant_evaluation(self):
        # Synthetic unit-test fixture exercising the participant branch; never saved as study evidence.
        model = fit_model([complete(request(mode="participant"))])
        self.assertTrue(study_info(model)["human_evaluation_ready"])
        export = complete(request("evaluation", "participant", "P002"), model)
        self.assertEqual(export["model_id"], model["model_id"])
        self.assertEqual(summarize([export], model)["provenance"], "participant")
        with self.assertRaisesRegex(ValueError, "new participant"):
            run_study(request("evaluation", "participant", "P001"), model)

    def test_public_rehearsal_keeps_participant_model_out(self):
        model = fit_model([complete(request(mode="participant"))])
        export = complete(request("evaluation"), model)
        self.assertEqual(export["model_id"], "assumed-v1")
        self.assertIsNone(study_info(model)["rehearsal_model_id"])

    def test_counts_conditional_accuracy_and_beta_smoothing(self):
        def replies(task, q, correct):
            if task.task_id == "dev-kind-0":
                return UNKNOWN
            if task.task_id == "dev-kind-1":
                return next(v for v in q["options"] if v != correct)
            return correct
        export = complete(request(), reply_rule=replies)
        model = fit_model([export], allow_rehearsal=True)
        self.assertEqual(model["counts"]["kind"], {"correct": 0, "incorrect": 1, "unknown": 1,
                                                  "total": 2, "raw_accuracy": 0, "raw_unknown": .5})
        self.assertAlmostEqual(model["probabilities"]["kind"]["accuracy"], 1 / 3)
        self.assertEqual(model["probabilities"]["kind"]["unknown"], .5)
        self.assertEqual(model["probabilities"]["merchant"], {"accuracy": .75, "unknown": .25})

    def test_rehearsal_rejected_by_default(self):
        with self.assertRaisesRegex(ValueError, "Rehearsal data rejected"):
            fit_model([complete(request())])

    def test_duplicate_participants_rejected(self):
        export = complete(request())
        with self.assertRaisesRegex(ValueError, "Duplicate participant"):
            fit_model([export, export], allow_rehearsal=True)

    def test_outcome_tampering_does_not_change_counts(self):
        export = complete(request())
        expected = fit_model([export], allow_rehearsal=True)
        export["results"] = [{"target_id": "fake", "outcome": "correct_selection"}]
        actual = fit_model([export], allow_rehearsal=True)
        self.assertEqual(expected, actual)  # server task definitions and replay, never client labels

    def test_incomplete_development_and_evaluation_exports_cannot_fit(self):
        export = complete(request())
        export["request"]["completed"].pop()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            fit_model([export], allow_rehearsal=True)
        with self.assertRaisesRegex(ValueError, "mix development"):
            fit_model([complete(request("evaluation"))], allow_rehearsal=True)

    def test_frozen_hash_and_provenance_are_checked(self):
        model = fit_model([complete(request())], allow_rehearsal=True)
        with self.assertRaisesRegex(ValueError, "provenance"):
            run_study(request("evaluation", "participant", "P002"), model)
        model["probabilities"]["kind"]["accuracy"] = .99
        with self.assertRaisesRegex(ValueError, "hash"):
            validate_model(model)

    def test_evaluation_rejects_development_participant_and_wrong_model(self):
        model = fit_model([complete(request())], allow_rehearsal=True)
        with self.assertRaisesRegex(ValueError, "new participant"):
            run_study(request("evaluation"), model)
        export = complete(request("evaluation", code="P002"), model)
        export["model_id"] = "changed"
        with self.assertRaisesRegex(ValueError, "mismatched frozen"):
            summarize([export], model, allow_rehearsal=True)

    def test_frozen_evaluation_counts_use_replayed_task_outcomes(self):
        model = fit_model([complete(request())], allow_rehearsal=True)
        export = complete(request("evaluation", code="P002"), model)
        result = summarize([export], model, allow_rehearsal=True)
        arm = result["arms"]["information_gain"]
        self.assertEqual((arm["participants"], arm["tasks"], arm["identified_target_tasks"]), (1, 4, 2))
        self.assertEqual((arm["correct_selection"], arm["appropriate_unresolved"], arm["wrong_selection"]), (2, 2, 0))
        self.assertEqual(result["provenance"], "rehearsal")


class StudyHTTP(unittest.TestCase):
    def call(self, body=None, path="/api/study", origin="http://127.0.0.1:8765"):
        statuses = []
        wire = json.dumps(body).encode() if body is not None else b""
        env = {"REQUEST_METHOD": "POST" if body is not None else "GET", "PATH_INFO": path,
               "HTTP_HOST": "127.0.0.1:8765", "HTTP_ORIGIN": origin,
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(wire)), "wsgi.input": io.BytesIO(wire)}
        output = b"".join(DemoApp()(env, lambda status, _: statuses.append(status)))
        return statuses[0], output

    def test_study_assets_and_configuration(self):
        for path in ["/study", "/study.js", "/study.css", "/api/study"]:
            self.assertEqual(self.call(path=path)[0], "200 OK")
        self.assertFalse(json.loads(self.call()[1])["human_evaluation_ready"])
        self.assertEqual(self.call(request())[0], "200 OK")

    def test_untrusted_labels_and_wrong_origin_rejected(self):
        req = request()
        req["target"] = "txn_FAKE0001"
        self.assertEqual(self.call(req)[0], "400 Bad Request")
        self.assertEqual(self.call(request(), origin="https://example.com")[0], "403 Forbidden")


if __name__ == "__main__":
    unittest.main()
