import copy
import json
import unittest
from datetime import date
from pathlib import Path

from assurancegraph.change import impact
from assurancegraph.core import assess, evidence_score, load_case, validate_case
from assurancegraph.economics import calculate
from assurancegraph.exporters import intoto_statement, markdown_brief, offline_html, oscal_assessment

ROOT=Path(__file__).parents[1]


class AssuranceGraphTests(unittest.TestCase):
    def setUp(self): self.case=load_case(ROOT/"fixtures/refund-agent/case.json")

    def test_case_is_valid(self): self.assertEqual(validate_case(self.case),[])
    def test_all_evidence_integrity_is_verified(self):
        scores=[evidence_score(e,self.case,date(2026,9,6)) for e in self.case["evidence"]]
        self.assertTrue(all(s["checks"]["integrity"] for s in scores))
    def test_wrong_digest_fails_integrity(self):
        item=copy.deepcopy(self.case["evidence"][0]); item["sha256"]="0"*64
        self.assertFalse(evidence_score(item,self.case,date(2026,9,6))["checks"]["integrity"])
    def test_expired_evidence_fails_freshness(self):
        item=copy.deepcopy(self.case["evidence"][0]); item["expires_at"]="2026-01-01"
        self.assertFalse(evidence_score(item,self.case,date(2026,9,6))["checks"]["freshness"])
    def test_environment_mismatch_reduces_score(self):
        item=copy.deepcopy(self.case["evidence"][0]); item["environment"]="development"
        self.assertFalse(evidence_score(item,self.case,date(2026,9,6))["checks"]["environment_equivalence"])
    def test_baseline_is_approved(self):
        result=assess(self.case,date(2026,9,6)); self.assertEqual(result["decision"],"APPROVE"); self.assertEqual(result["claims_supported"],4)
    def test_claim_input_order_does_not_change_decision(self):
        case=copy.deepcopy(self.case); case["claims"].reverse()
        self.assertEqual(assess(case,date(2026,9,6))["decision"],"APPROVE")
    def test_failed_critical_evidence_rejects(self):
        case=copy.deepcopy(self.case); next(e for e in case["evidence"] if e["id"]=="E-PAYMENT")["result"]="fail"
        result=assess(case,date(2026,9,6)); self.assertEqual(result["decision"],"REJECT")
    def test_counterevidence_rejects_critical_claim(self):
        case=copy.deepcopy(self.case); next(c for c in case["claims"] if c["id"]=="CLAIM-PAYMENT")["counterevidence"]=["E-PAYMENT"]; next(e for e in case["evidence"] if e["id"]=="E-PAYMENT")["result"]="fail"
        self.assertEqual(assess(case,date(2026,9,6))["decision"],"REJECT")
    def test_invalid_assumption_rejects(self):
        case=copy.deepcopy(self.case); next(c for c in case["claims"] if c["id"]=="CLAIM-PAYMENT")["assumptions"][0]["status"]="invalid"
        self.assertEqual(assess(case,date(2026,9,6))["decision"],"REJECT")
    def test_unknown_reference_is_rejected(self):
        case=copy.deepcopy(self.case); case["claims"][0]["evidence"]=["E-MISSING"]
        self.assertIn("unknown-evidence-reference",[i.code for i in validate_case(case)])
    def test_cycles_are_rejected(self):
        case=copy.deepcopy(self.case); case["claims"][0]["depends_on"]=["CLAIM-TOP"]
        self.assertIn("claim-cycle",[i.code for i in validate_case(case)])
    def test_material_change_invalidates_payment_and_top_claims(self):
        change=json.loads((ROOT/"fixtures/refund-agent/change.json").read_text()); result=impact(self.case,change)
        self.assertEqual(result["decision"],"REASSESS"); self.assertTrue(result["release_blocked"]); self.assertEqual(len(result["affected_claims"]),2)
    def test_unrelated_change_has_no_impact(self):
        self.assertEqual(impact(self.case,{"id":"X","category":"office-furniture"})["decision"],"NO_CASE_IMPACT")
    def test_oscal_export_contains_observations(self):
        output=oscal_assessment(self.case,assess(self.case,date(2026,9,6)))
        self.assertEqual(len(output["assessment-results"]["results"][0]["observations"]),4)
    def test_intoto_subject_uses_assessment_digest(self):
        result=assess(self.case,date(2026,9,6)); output=intoto_statement(self.case,result)
        self.assertEqual(output["subject"][0]["digest"]["sha256"],result["assessment_sha256"])
    def test_brief_contains_legal_boundary(self):
        brief=markdown_brief(self.case,assess(self.case,date(2026,9,6)))
        self.assertIn("Review legal applicability",brief)
    def test_html_escapes_untrusted_content(self): self.assertIn("&lt;script&gt;",offline_html("<script>"))
    def test_economics_excludes_capacity(self):
        data=json.loads((ROOT/"fixtures/economics.json").read_text()); first=calculate(data); data["additional_reviews"]=99999; second=calculate(data)
        self.assertEqual(first["net_assurance_value_p50"],second["net_assurance_value_p50"])


if __name__=="__main__": unittest.main()
