"""Optional Bedrock contextual grounding inside the answer/repair/fallback gate.

Disabled by default. This is an additional fallible check, not an authorization
mechanism or a proof of completeness. Unavailable assessments fail closed in the
application but MUST NOT count as detected factual errors in experiments.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time

from .guardrails import BLOCKED_OUTPUT_MSG, GuardResult
from .provenance import trusted_log


def grounding_source(tool_log: list[dict]) -> str:
    # Keep tool/record boundaries and only the latest result for identical inputs.
    # A later not-found response must supersede an earlier successful lookup.
    latest = {}
    for call in trusted_log(tool_log):
        key = (call["name"], json.dumps(call.get("input", {}), sort_keys=True))
        latest[key] = {k: call[k] for k in ("name", "input", "result") if k in call}
    return json.dumps(list(latest.values()), sort_keys=True, ensure_ascii=False) if latest else ""


def runtime_client(region: str):
    import boto3
    from botocore.config import Config
    # No invisible retry calls in evaluation cost/latency accounting.
    return boto3.client("bedrock-runtime", region_name=region,
                        config=Config(connect_timeout=3, read_timeout=10,
                                      retries={"total_max_attempts": 1, "mode": "standard"}))


class BedrockGroundingVerifier:
    name = "bedrock_grounding"

    def __init__(self, guardrail_id: str, version: str, region: str, question: str,
                 *, client=None, clock=time.perf_counter):
        if not guardrail_id or not re.fullmatch(r"[1-9][0-9]{0,7}", version):
            raise ValueError("Semantic verification needs a guardrail ID and a published numeric version, not DRAFT.")
        self.guardrail_id, self.version, self.region = guardrail_id, version, region
        self.question, self.client, self.clock = question, client, clock

    def check(self, answer, tool_log, focus):
        started = self.clock()
        detail = {"kind": "semantic_grounding", "method": self.name,
                  "guardrail_id": self.guardrail_id, "version": self.version, "region": self.region,
                  "verdict": "unavailable", "filters": [], "usage": None, "provider_called": False}

        def result(verdict, reasons):
            detail.update(verdict=verdict, latency_ms=round((self.clock() - started) * 1000, 3))
            action = "allow" if verdict == "supported" else "block"
            return GuardResult(action, answer if action == "allow" else BLOCKED_OUTPUT_MSG, reasons, [detail])

        source = grounding_source(tool_log)
        for label, value, limit in (("source", source, 100000), ("query", self.question, 1000),
                                    ("answer", answer, 5000)):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                return result("unavailable", [f"semantic_unavailable:invalid_{label}_length"])
        detail["source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
        try:
            if self.client is None:
                self.client = runtime_client(self.region)
            detail["provider_called"] = True
            response = self.client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id, guardrailVersion=self.version,
                source="OUTPUT", outputScope="FULL", content=[
                    {"text": {"text": source, "qualifiers": ["grounding_source"]}},
                    {"text": {"text": self.question, "qualifiers": ["query"]}},
                    {"text": {"text": answer, "qualifiers": ["guard_content"]}},
                ])
        except Exception as exc:
            # Never persist exception text: SDK errors can contain request data.
            detail["error_type"] = type(exc).__name__
            return result("unavailable", ["semantic_unavailable:provider_error"])
        try:
            if response["action"] not in ("NONE", "GUARDRAIL_INTERVENED"):
                raise ValueError("action")
            detail["usage"] = response.get("usage")
            detail["request_id"] = response.get("ResponseMetadata", {}).get("RequestId")
            assessments = response["assessments"]
            if not isinstance(assessments, list) or not assessments:
                raise ValueError("assessments")
            filters = []
            for assessment in assessments:
                # Require a dedicated contextual-grounding guardrail. Other
                # policies would confound a semantic-only ablation.
                if any(k.endswith("Policy") and k != "contextualGroundingPolicy" and v
                       for k, v in assessment.items()):
                    return result("unavailable", ["semantic_unavailable:mixed_policies"])
                applied = assessment.get("appliedGuardrailDetails", {})
                if applied.get("guardrailVersion", self.version) != self.version:
                    raise ValueError("version")
                batch = assessment.get("contextualGroundingPolicy", {}).get("filters", [])
                if not isinstance(batch, list) or {f["type"] for f in batch} != {"GROUNDING", "RELEVANCE"}:
                    raise ValueError("missing_filters")
                for f in batch:
                    score, threshold = f["score"], f["threshold"]
                    if (type(score) not in (int, float) or type(threshold) not in (int, float)
                            or not math.isfinite(score) or not math.isfinite(threshold)
                            or not 0 <= score <= 1 or not 0 <= threshold < 1
                            or f["action"] not in ("NONE", "BLOCKED")):
                        raise ValueError("filter")
                    detected = score < threshold
                    if "detected" in f and (type(f["detected"]) is not bool or f["detected"] != detected):
                        raise ValueError("detected")
                    if f["action"] == "BLOCKED" and not detected:
                        raise ValueError("inconsistent_filter")
                    filters.append({"type": f["type"], "score": score, "threshold": threshold,
                                    "detected": detected, "action": f["action"]})
            detail["filters"] = filters
            blocked = any(f["action"] == "BLOCKED" for f in filters)
            if (response["action"] == "GUARDRAIL_INTERVENED") != blocked:
                raise ValueError("inconsistent_action")
            failures = sorted({f["type"].lower() for f in filters if f["detected"]})
            # Enforce thresholds even if the AWS filter is configured detect-only.
            return result("unsupported" if failures else "supported",
                          [f"semantic_{name}_below_threshold" for name in failures])
        except (KeyError, TypeError, ValueError, AttributeError):
            return result("unavailable", ["semantic_unavailable:malformed_assessment"])


def configured_verifier(settings, question: str):
    if settings.semantic_verification == "off":
        return ()
    if settings.semantic_verification != "bedrock":
        raise ValueError("FINBOT_SEMANTIC_VERIFICATION must be off or bedrock")
    return (BedrockGroundingVerifier(settings.semantic_guardrail_id, settings.semantic_guardrail_version,
                                     settings.aws_region, question),)
