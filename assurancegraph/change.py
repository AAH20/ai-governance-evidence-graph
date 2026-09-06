from __future__ import annotations

from typing import Any


def impact(case: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    category = change["category"]
    affected = []
    for claim in case["claims"]:
        triggers = set(claim.get("reassessment_triggers", []))
        if category in triggers or ("any-material-change" in triggers and change.get("material") is True):
            affected.append({"claim_id":claim["id"],"reason":f"trigger:{category}","prior_status":"supported-or-unassessed","new_status":"invalidated"})
    critical = [item for item in affected if next(c for c in case["claims"] if c["id"] == item["claim_id"])["criticality"] == "critical"]
    return {
        "change_id":change["id"],"category":category,"affected_claims":affected,
        "decision":"EMERGENCY_SUSPEND" if change.get("emergency") and critical else ("REASSESS" if affected else "NO_CASE_IMPACT"),
        "release_blocked":bool(critical),
    }
