from __future__ import annotations

from typing import Any


def calculate(data: dict[str, Any]) -> dict[str, Any]:
    cases=max(1,float(data["completed_cases"])); claims=max(1,float(data["defensible_claims"])); hourly=float(data["loaded_hourly_cost"])
    collection=float(data["collection_hours"])*hourly; validation=float(data["validation_hours"])*hourly
    review=float(data["review_hours"])*hourly; platform=float(data["platform_cost"]); total=collection+validation+review+platform
    change_savings=float(data["full_reassessment_hours_avoided"])*hourly
    audit_savings=float(data["audit_hours_avoided"])*hourly
    engineering_savings=float(data["engineering_hours_avoided"])*hourly
    effectiveness=float(data["demonstrated_assurance_effectiveness"])
    risk={k:round(float(data["event_probability"][k])*float(data["probable_impact"][k])*effectiveness,2) for k in ("p10","p50","p90")}
    direct=float(data.get("direct_revenue_enabled",0)); contributory=float(data.get("contributory_revenue",0))*float(data.get("attribution_factor",0))
    capacity=float(data.get("additional_reviews",0))*float(data.get("qualification_rate",0))*float(data.get("average_contract_value",0))
    net=risk["p50"]+change_savings+audit_savings+engineering_savings+direct+contributory-total
    return {
        "cost_per_assurance_case":round(total/cases,2),"cost_per_defensible_claim":round(total/claims,2),
        "change_impact_savings":round(change_savings,2),"audit_savings":round(audit_savings,2),"engineering_savings":round(engineering_savings,2),
        "expected_loss_reduction":risk,"direct_revenue_enabled":round(direct,2),"contributory_revenue_attributed":round(contributory,2),
        "capacity_enabled_pipeline":round(capacity,2),"net_assurance_value_p50":round(net,2),"assurance_roi_p50":round(net/total,3) if total else 0,
        "disclaimer":"Illustrative decision support. Capacity pipeline is excluded from net value and is not booked revenue."
    }
