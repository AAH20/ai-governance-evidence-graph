from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timezone
from typing import Any


NAMESPACE=uuid.UUID("734357ac-ce88-4894-af3a-b6a577c81783")


def oscal_assessment(case: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    observations=[]
    for result in assessment["claim_results"]:
        observations.append({
            "uuid":str(uuid.uuid5(NAMESPACE,case["case_id"]+result["claim_id"])),
            "title":result["statement"],"description":"supported" if result["supported"] else ", ".join(result["reasons"]),
            "methods":["EXAMINE","TEST"],"props":[{"name":"assurance-claim-id","value":result["claim_id"]},{"name":"supported","value":str(result["supported"]).lower()}]
        })
    return {"assessment-results":{"uuid":str(uuid.uuid5(NAMESPACE,case["case_id"])),"metadata":{"title":f'AI assurance assessment: {case["system"]}',"last-modified":datetime.now(timezone.utc).isoformat(),"version":case["system_version"],"oscal-version":"1.1.2","remarks":"OSCAL-shaped implementation profile; validate against the selected official schema before exchange."},"results":[{"uuid":str(uuid.uuid5(NAMESPACE,case["case_id"]+"result")),"title":assessment["decision"],"description":assessment["disclaimer"],"start":assessment["as_of"]+"T00:00:00Z","reviewed-controls":{"control-selections":[{"description":"Claims selected by the assurance case"}]},"observations":observations}]}}


def intoto_statement(case: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    return {"_type":"https://in-toto.io/Statement/v1","subject":[{"name":case["system"],"digest":{"sha256":assessment["assessment_sha256"]}}],"predicateType":"https://a2zsoc.com/assurancegraph/v1","predicate":{"case_id":case["case_id"],"system_version":case["system_version"],"environment":case["environment"],"decision":assessment["decision"],"claims_supported":assessment["claims_supported"],"claims_total":assessment["claims_total"],"assessment_date":assessment["as_of"],"notice":"Unsigned attestation. Signing and identity verification are separate controls."}}


def markdown_brief(case: dict[str, Any], assessment: dict[str, Any]) -> str:
    failed=[r for r in assessment["claim_results"] if not r["supported"]]
    return f"""# AI assurance decision: {case['system']}

**Decision:** {assessment['decision']}<br>
**Version/environment:** {case['system_version']} / {case['environment']}<br>
**Claims supported:** {assessment['claims_supported']} of {assessment['claims_total']}<br>
**Assessment date:** {assessment['as_of']}

## Decision context

{case.get('business_context','No business context supplied.')}

## Unsupported claims

{chr(10).join(f'- **{r["claim_id"]}:** {r["statement"]} — {", ".join(r["reasons"])}' for r in failed) or '- None'}

## Residual-risk ownership

{case.get('risk_acceptance',{}).get('owner','No approved risk owner recorded')}

## Limitations

{assessment['disclaimer']} Evidence applies only to the declared version, environment and context. Review legal applicability with qualified counsel.

**Assessment digest:** `{assessment['assessment_sha256']}`
"""


def offline_html(markdown: str) -> str:
    # Deliberately minimal and dependency-free; preserves content safely rather than interpreting arbitrary HTML.
    return "<!doctype html><html><head><meta charset='utf-8'><title>AI Assurance Decision</title><style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:0 20px;white-space:pre-wrap;color:#172033}code{background:#eef2f7;padding:2px 5px}</style></head><body>"+html.escape(markdown)+"</body></html>"


def dumps(data: Any) -> str:
    return json.dumps(data,indent=2)+"\n"
