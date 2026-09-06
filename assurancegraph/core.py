from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Issue:
    code: str
    object_id: str
    message: str


def digest_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_case(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    case = json.loads(source.read_text())
    issues = validate_case(case)
    if issues:
        raise ValueError("; ".join(f"{i.code}:{i.object_id}:{i.message}" for i in issues))
    case["_case_dir"] = str(source.resolve().parent)
    return case


def _duplicates(values: list[str]) -> set[str]:
    return {value for value in values if values.count(value) > 1}


def validate_case(case: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for field in ("schema_version", "case_id", "system", "system_version", "environment", "claims", "evidence"):
        if field not in case:
            issues.append(Issue("missing-field", case.get("case_id", "case"), field))
    if issues:
        return issues
    if case["schema_version"] != "1.0":
        issues.append(Issue("schema-version", case["case_id"], "expected 1.0"))
    claims = {c["id"]: c for c in case["claims"]}
    evidence = {e["id"]: e for e in case["evidence"]}
    for duplicate in _duplicates([c["id"] for c in case["claims"]]):
        issues.append(Issue("duplicate-claim", duplicate, "claim IDs must be unique"))
    for duplicate in _duplicates([e["id"] for e in case["evidence"]]):
        issues.append(Issue("duplicate-evidence", duplicate, "evidence IDs must be unique"))
    for claim in case["claims"]:
        for ref in claim.get("depends_on", []):
            if ref not in claims:
                issues.append(Issue("unknown-claim-reference", claim["id"], ref))
        for ref in claim.get("evidence", []) + claim.get("counterevidence", []):
            if ref not in evidence:
                issues.append(Issue("unknown-evidence-reference", claim["id"], ref))
        if not claim.get("owner"):
            issues.append(Issue("missing-owner", claim["id"], "claim needs an accountable owner"))
        if not claim.get("context"):
            issues.append(Issue("missing-context", claim["id"], "claim needs bounded context"))

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            issues.append(Issue("claim-cycle", node, "dependency graph must be acyclic")); return
        if node in visited or node not in claims:
            return
        visiting.add(node)
        for dep in claims[node].get("depends_on", []): visit(dep)
        visiting.remove(node); visited.add(node)
    for node in claims: visit(node)
    return issues


def evidence_score(item: dict[str, Any], case: dict[str, Any], as_of: date) -> dict[str, Any]:
    declared_digest = item.get("sha256", "")
    uri = item.get("source_uri", "")
    integrity = bool(declared_digest and len(declared_digest) == 64)
    if integrity and uri and "://" not in uri and case.get("_case_dir"):
        source_path = Path(case["_case_dir"]) / uri
        integrity = source_path.is_file() and digest_file(source_path) == declared_digest
    checks = {
        "provenance": bool(item.get("producer") and item.get("source_uri")),
        "integrity": integrity,
        "freshness": date.fromisoformat(item["expires_at"]) >= as_of,
        "environment_equivalence": item.get("environment") == case["environment"],
        "version_equivalence": item.get("system_version") == case["system_version"],
        "reproducibility": bool(item.get("reproducible")),
        "independence": bool(item.get("independent_review")),
    }
    weights = {"provenance":15,"integrity":15,"freshness":15,"environment_equivalence":15,"version_equivalence":15,"reproducibility":15,"independence":10}
    score = sum(weights[name] for name, passed in checks.items() if passed)
    return {"evidence_id":item["id"],"score":score,"checks":checks,"acceptable":score >= int(case.get("minimum_evidence_score", 70))}


def assess(case: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc).date()
    evidence = {item["id"]: item for item in case["evidence"]}
    scores = {eid:evidence_score(item, case, as_of) for eid,item in evidence.items()}
    results: list[dict[str, Any]] = []
    supported: dict[str, bool] = {}
    claim_map = {claim["id"]: claim for claim in case["claims"]}
    ordered: list[dict[str, Any]] = []
    emitted: set[str] = set()
    def emit(claim_id: str) -> None:
        if claim_id in emitted:
            return
        for dependency in claim_map[claim_id].get("depends_on", []):
            emit(dependency)
        ordered.append(claim_map[claim_id]); emitted.add(claim_id)
    for claim_id in claim_map:
        emit(claim_id)
    for claim in ordered:
        expired = date.fromisoformat(claim["expires_at"]) < as_of
        invalid_assumptions = [a["id"] for a in claim.get("assumptions", []) if a.get("status") != "valid"]
        counter = [eid for eid in claim.get("counterevidence", []) if evidence[eid].get("result") == "fail"]
        weak = [eid for eid in claim.get("evidence", []) if not scores[eid]["acceptable"] or evidence[eid].get("result") != "pass"]
        failed_dependencies = [cid for cid in claim.get("depends_on", []) if not supported.get(cid, False)]
        reasons = []
        if expired: reasons.append("claim_expired")
        if invalid_assumptions: reasons.append("invalid_assumption")
        if counter: reasons.append("unresolved_counterevidence")
        if weak: reasons.append("insufficient_evidence")
        if failed_dependencies: reasons.append("unsupported_dependency")
        if not claim.get("evidence") and not claim.get("depends_on"): reasons.append("no_support")
        is_supported = not reasons
        supported[claim["id"]] = is_supported
        results.append({
            "claim_id":claim["id"],"statement":claim["statement"],"criticality":claim["criticality"],
            "supported":is_supported,"reasons":reasons,"weak_evidence":weak,"counterevidence":counter,
            "invalid_assumptions":invalid_assumptions,"failed_dependencies":failed_dependencies,
        })
    critical_failed = [r for r in results if r["criticality"] == "critical" and not r["supported"]]
    any_failed = [r for r in results if not r["supported"]]
    if critical_failed:
        decision = "REJECT"
    elif any_failed:
        decision = "APPROVE_WITH_RESTRICTIONS"
    else:
        decision = "APPROVE"
    payload = {
        "case_id":case["case_id"],"system":case["system"],"system_version":case["system_version"],
        "environment":case["environment"],"as_of":as_of.isoformat(),"decision":decision,
        "claims_total":len(results),"claims_supported":sum(r["supported"] for r in results),
        "claim_results":results,"evidence_scores":list(scores.values()),
        "disclaimer":"Decision support only; not legal advice, certification, or automatic production authorization."
    }
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    payload["assessment_sha256"]=hashlib.sha256(canonical).hexdigest()
    return payload
