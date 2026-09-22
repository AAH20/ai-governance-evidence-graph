import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assurancegraph.decisions import (
    FixtureProvider,
    JevProvider,
    assurance_envelope,
    propose,
    run_pack,
    sha256,
    validate_choice,
    validate_pack,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = json.loads((ROOT / "fixtures/shadow-decisions/pilots.v1.json").read_text())


class DecisionPilotTests(unittest.TestCase):
    def test_three_pilots_and_confident_error_are_visible(self):
        self.assertEqual([], validate_pack(PACK))
        report = run_pack(PACK, FixtureProvider())
        self.assertEqual(6, report["summary"]["cases"])
        self.assertEqual(5, report["summary"]["correct"])
        self.assertEqual(1, report["summary"]["critical_misroutes"])
        self.assertEqual(1.0, report["summary"]["coverage"])
        self.assertGreater(report["summary"]["brier_score"], 0)
        self.assertEqual(3, len({p["domain"] for p in report["proposals"]}))
        iam_error = next(p for p in report["proposals"] if p["case_id"] == "IAM-002")
        self.assertEqual("escalate-review", iam_error["disposition"])
        self.assertGreater(iam_error["answer"]["confidence"], 0.9)
        self.assertTrue(all(p["shadow_only"] for p in report["proposals"]))

    def test_low_confidence_escalates_even_when_choice_is_right(self):
        report = run_pack(PACK, FixtureProvider())
        grc = next(p for p in report["proposals"] if p["case_id"] == "GRC-002")
        self.assertTrue(grc["evaluation"]["correct"])
        self.assertEqual("escalate-review", grc["disposition"])

    def test_invalid_answer_abstains_and_state_is_not_exported(self):
        case = copy.deepcopy(PACK["cases"][0])
        case["mock_answer"]["probabilities"]["evidence-gap"] = float("nan")
        proposal = propose(case, FixtureProvider())
        self.assertEqual("abstain", proposal["disposition"])
        self.assertIsNone(proposal["answer"])
        self.assertNotIn("signature_present", json.dumps(proposal))
        self.assertEqual(sha256(case["state"]), proposal["input"]["state_sha256"])

    def test_non_synthetic_state_is_rejected(self):
        pack = copy.deepcopy(PACK)
        pack["cases"][0]["data_classification"] = "customer-confidential"
        self.assertTrue(validate_pack(pack))
        with self.assertRaises(ValueError):
            run_pack(pack, FixtureProvider())

    def test_choice_contract_rejects_missing_options(self):
        answer = copy.deepcopy(PACK["cases"][0]["mock_answer"])
        del answer["probabilities"]["source-review"]
        with self.assertRaises(ValueError):
            validate_choice(answer, PACK["cases"][0]["question"]["criteria"])

    def test_live_provider_requires_explicit_network_and_key(self):
        with self.assertRaises(ValueError):
            JevProvider(allow_network=False, api_key="synthetic-key")
        with (
            patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}),
            self.assertRaises(ValueError),
        ):
            JevProvider(allow_network=True)

    def test_jev_http_adapter_uses_typed_question_without_network(self):
        case = PACK["cases"][0]
        payloads = []

        class Headers:
            def get_content_type(self):
                return "application/json"

        class Response:
            status = 200
            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size):
                return json.dumps(
                    {
                        "answers": {"evidence_route": case["mock_answer"]},
                        "model": "jev-1.13.0",
                        "usage": {"input_tokens": 42, "output_tokens": 5},
                    }
                ).encode()

        class Opener:
            def open(self, call, timeout):
                payloads.append((call.full_url, json.loads(call.data)))
                return Response()

        provider = JevProvider(allow_network=True, api_key="synthetic-key")
        provider.opener = Opener()
        answer, usage = provider.evaluate(case)
        self.assertEqual("evidence-gap", answer["choice"])
        self.assertEqual(42, usage["input_tokens"])
        self.assertEqual("jev-1.13.0", usage["resolved_model"])
        self.assertEqual("https://api.typesafe.ai/v1/systemone", payloads[0][0])
        self.assertEqual(
            "choice", payloads[0][1]["questions"]["evidence_route"]["type"]
        )
        self.assertEqual(case["state"], payloads[0][1]["state"])
        proposal = propose(case, provider)
        self.assertEqual("jev-1.13.0", proposal["provider"]["resolved_model"])
        self.assertNotIn("synthetic-key", json.dumps(proposal))

    def test_assurance_export_binds_report_and_flags_failed_case(self):
        report = run_pack(PACK, FixtureProvider())
        envelope = assurance_envelope(PACK, report)
        self.assertEqual("not-scored", envelope["qualification"]["score_basis"])
        self.assertEqual(sha256(report), envelope["evidence"]["artifact_sha256"])
        self.assertIn("IAM-002", envelope["qualification"]["failed_gates"])
        self.assertIn("GRC-002", envelope["qualification"]["failed_gates"])
        self.assertEqual("none", envelope["evidence"]["verification"])

    def test_cli_writes_both_artifacts_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "report.json"
            assurance = Path(directory) / "assurance.json"
            cmd = [
                sys.executable,
                "-m",
                "assurancegraph.decision_cli",
                str(ROOT / "fixtures/shadow-decisions/pilots.v1.json"),
                "--output",
                str(result),
                "--assurance-output",
                str(assurance),
            ]
            process = subprocess.run(
                cmd, capture_output=True, text=True, cwd=ROOT, check=False
            )
            self.assertEqual(0, process.returncode, process.stderr)
            self.assertEqual("fixture", json.loads(result.read_text())["provider"])
            self.assertEqual(
                "bpa.assurance-result.v1",
                json.loads(assurance.read_text())["schema_version"],
            )


if __name__ == "__main__":
    unittest.main()
