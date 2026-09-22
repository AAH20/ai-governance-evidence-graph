"""Provider-neutral, shadow-only typed decision proposals.

No proposal authorizes an access grant, physical action, or compliance claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from urllib import error, request

SCHEMA_VERSION = "a2z.decision-proposal.v1"
JEV_URL = "https://api.typesafe.ai/v1/systemone"
MAX_STATE_BYTES = 4096
MAX_RESPONSE_BYTES = 65536
DOMAINS = {"grc-evidence", "iam-request", "physical-incident"}


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_pack(pack: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(pack, dict) or not pack.get("pack_id") or not pack.get("version"):
        return ["pack_id and version are required"]
    cases = pack.get("cases")
    if not isinstance(cases, list) or not cases:
        return ["cases must be a non-empty array"]
    seen: set[str] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{label} must be an object")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            errors.append(f"{label}.case_id must be unique and non-empty")
        if isinstance(case_id, str):
            seen.add(case_id)
        if case.get("domain") not in DOMAINS:
            errors.append(f"{label}.domain is invalid")
        if case.get("data_classification") != "public-synthetic":
            errors.append(f"{label} must declare public-synthetic data")
        state = case.get("state")
        try:
            if not isinstance(state, dict) or len(canonical(state)) > MAX_STATE_BYTES:
                errors.append(f"{label}.state must be an object of at most 4096 bytes")
        except (TypeError, ValueError):
            errors.append(f"{label}.state is not valid JSON")
        question = case.get("question")
        if not isinstance(question, dict) or question.get("type") != "choice":
            errors.append(f"{label}.question must be a Choice question")
            continue
        if not isinstance(question.get("id"), str) or not question["id"]:
            errors.append(f"{label}.question.id is required")
        if (
            not isinstance(question.get("instructions"), str)
            or not question["instructions"]
        ):
            errors.append(f"{label}.question.instructions is required")
        criteria = question.get("criteria")
        if (
            not isinstance(criteria, dict)
            or len(criteria) < 2
            or any(
                not isinstance(k, str) or not k or not isinstance(v, str) or not v
                for k, v in criteria.items()
            )
        ):
            errors.append(
                f"{label}.question.criteria needs at least two described choices"
            )
        elif (
            not isinstance(case.get("expected"), str)
            or case["expected"] not in criteria
        ):
            errors.append(f"{label}.expected must be a declared choice")
        threshold = case.get("shadow_review_threshold")
        if "critical" in case and not isinstance(case["critical"], bool):
            errors.append(f"{label}.critical must be boolean")
        if (
            not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not 0 <= threshold <= 1
        ):
            errors.append(f"{label}.shadow_review_threshold must be in [0,1]")
        if not isinstance(case.get("mock_answer"), dict):
            errors.append(f"{label}.mock_answer is required for offline replay")
    return errors


def validate_choice(answer: dict, criteria: dict) -> dict:
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ValueError("expected a Choice answer")
    choice = answer.get("choice")
    probabilities = answer.get("probabilities")
    confidence = answer.get("confidence")
    if (
        not isinstance(choice, str)
        or choice not in criteria
        or not isinstance(probabilities, dict)
        or set(probabilities) != set(criteria)
    ):
        raise ValueError("choice or probability keys differ from declared criteria")
    values = list(probabilities.values())
    if any(
        not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1
        for p in values
    ):
        raise ValueError("probabilities must be finite values in [0,1]")
    if abs(sum(values) - 1) > 0.02:
        raise ValueError("probabilities must sum to approximately one")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("confidence must be in [0,1]")
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": probabilities,
        "confidence": confidence,
    }


class FixtureProvider:
    name = "fixture"
    model = "synthetic-fixture-v1"

    def evaluate(self, case: dict) -> tuple[dict, dict]:
        return case["mock_answer"], {
            "input_tokens": None,
            "output_tokens": None,
            "resolved_model": None,
        }


class JevProvider:
    name = "typesafe-jev"

    def __init__(
        self,
        *,
        allow_network: bool,
        api_key: str | None = None,
        model: str = "jev-latest",
    ):
        if not allow_network:
            raise ValueError("live Jev calls require --allow-network")
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if not self.api_key:
            raise ValueError("TYPESAFE_API_KEY is required for live Jev calls")
        self.model = model
        self.opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def evaluate(self, case: dict) -> tuple[dict, dict]:
        question = case["question"]
        payload = {
            "model": self.model,
            "state": case["state"],
            "questions": {
                question["id"]: {
                    "type": "choice",
                    "instructions": question["instructions"],
                    "criteria": question["criteria"],
                }
            },
        }
        call = request.Request(
            JEV_URL,
            data=canonical(payload),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener.open(call, timeout=10) as response:
                if (
                    response.status != 200
                    or response.headers.get_content_type() != "application/json"
                ):
                    raise ValueError(
                        "Jev returned an unexpected status or content type"
                    )
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError("Jev response exceeds 64 KiB")
                data = json.loads(body)
        except (
            error.HTTPError,
            error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(f"Jev request failed: {type(exc).__name__}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise TypeError("Jev response lacks answers")
        answer = data["answers"].get(question["id"])
        if not isinstance(answer, dict):
            raise TypeError("Jev response lacks requested answer")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}

        def token_count(name: str) -> int | None:
            value = usage.get(name)
            return (
                value
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
                else None
            )

        return answer, {
            "input_tokens": token_count("input_tokens"),
            "output_tokens": token_count("output_tokens"),
            "resolved_model": data.get("model")
            if isinstance(data.get("model"), str)
            else None,
        }


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def propose(case: dict, provider: FixtureProvider | JevProvider) -> dict:
    if case["data_classification"] != "public-synthetic":
        raise ValueError("only public-synthetic state is permitted in this pilot")
    started = time.perf_counter()
    error_code = None
    answer = None
    usage: dict = {"input_tokens": None, "output_tokens": None, "resolved_model": None}
    try:
        raw_answer, usage = provider.evaluate(case)
        answer = validate_choice(raw_answer, case["question"]["criteria"])
    except (ValueError, KeyError, TypeError) as exc:
        error_code = type(exc).__name__
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    correct = answer is not None and answer["choice"] == case["expected"]
    confident = (
        answer is not None and answer["confidence"] >= case["shadow_review_threshold"]
    )
    disposition = (
        "candidate-for-review"
        if correct and confident
        else "escalate-review"
        if answer
        else "abstain"
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": f"{case['case_id']}:{sha256([case['state'], case['question'], answer])[:16]}",
        "case_id": case["case_id"],
        "domain": case["domain"],
        "data_classification": case["data_classification"],
        "provider": {
            "name": provider.name,
            "model": provider.model,
            "resolved_model": usage.get("resolved_model"),
        },
        "input": {
            "state_sha256": sha256(case["state"]),
            "question_sha256": sha256(case["question"]),
        },
        "answer": answer,
        "evaluation": {
            "expected_choice": case["expected"],
            "correct": correct,
            "critical": case.get("critical", False),
            "shadow_review_threshold": case["shadow_review_threshold"],
        },
        "disposition": disposition,
        "shadow_only": True,
        "telemetry": {
            "latency_ms": latency_ms,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        },
        "error_code": error_code,
    }
    return result


def run_pack(pack: dict, provider: FixtureProvider | JevProvider) -> dict:
    errors = validate_pack(pack)
    if errors:
        raise ValueError("; ".join(errors))
    proposals = [propose(case, provider) for case in pack["cases"]]
    total = len(proposals)
    correct = sum(item["evaluation"]["correct"] for item in proposals)
    answered = [p for p in proposals if p["answer"] is not None]
    brier = (
        sum(
            sum(
                (probability - (choice == p["evaluation"]["expected_choice"])) ** 2
                for choice, probability in p["answer"]["probabilities"].items()
            )
            for p in answered
        )
        / len(answered)
        if answered
        else None
    )
    return {
        "pack_id": pack["pack_id"],
        "pack_version": pack["version"],
        "pack_sha256": sha256(pack),
        "run_kind": "synthetic-reference"
        if provider.name == "fixture"
        else "provider-observed",
        "provider": provider.name,
        "qualification": "not-certified",
        "summary": {
            "cases": total,
            "correct": correct,
            "accuracy": round(correct / total, 4),
            "coverage": round(len(answered) / total, 4),
            "brier_score": round(brier, 4) if brier is not None else None,
            "critical_misroutes": sum(
                p["evaluation"]["critical"]
                and p["answer"] is not None
                and not p["evaluation"]["correct"]
                for p in proposals
            ),
            "mean_latency_ms": round(
                sum(p["telemetry"]["latency_ms"] for p in proposals) / total, 3
            ),
            "observed_input_tokens": sum(
                p["telemetry"]["input_tokens"] or 0 for p in proposals
            )
            if any(p["telemetry"]["input_tokens"] is not None for p in proposals)
            else None,
            "abstained": sum(p["disposition"] == "abstain" for p in proposals),
            "escalated": sum(p["disposition"] == "escalate-review" for p in proposals),
        },
        "proposals": proposals,
        "limitations": [
            "Synthetic pilot data; no production actions or access grants.",
            "Fixture outputs are scripted examples, not Jev performance measurements."
            if provider.name == "fixture"
            else "Jev output is observed but not independently verified or calibrated for this domain.",
        ],
    }


def assurance_envelope(pack: dict, report: dict) -> dict:
    failed = [
        item["case_id"]
        for item in report["proposals"]
        if item["disposition"] != "candidate-for-review"
    ]
    artifact_hash = sha256(report)
    return {
        "schema_version": "bpa.assurance-result.v1",
        "result_id": f"{pack['pack_id']}:{artifact_hash[:16]}",
        "producer": {
            "repository": "AAH20/ai-governance-evidence-graph",
            "component": "shadow-decisions",
            "version": "0.1.0",
        },
        "run": {
            "kind": report["run_kind"],
            "environment": "synthetic-fixture"
            if report["provider"] == "fixture"
            else "hosted-jev",
        },
        "subject": {
            "pack_id": pack["pack_id"],
            "pack_version": pack["version"],
            "pack_sha256": sha256(pack),
        },
        "qualification": {
            "qualified": not failed,
            "failed_gates": failed,
            "score": None,
            "score_basis": "not-scored",
        },
        "evidence": {
            "artifact_sha256": artifact_hash,
            "receipt_root_sha256": None,
            "verification": "none",
        },
        "limitations": report["limitations"],
    }
