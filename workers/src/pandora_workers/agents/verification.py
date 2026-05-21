"""Verification agent — ``pandora.verification.start`` → ``pandora.verification.complete``."""

from __future__ import annotations

import json
import logging
from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import (
    VerificationCompletePayload,
    VerificationStartWorkPayload,
)
from pandora_shared.queues import VERIFICATION_COMPLETE, VERIFICATION_START

from pandora_workers.base_agent import BaseAgent
from pandora_workers.envelopes import build_result
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 28_000
_MAX_ISSUES = 20
_BLOCKING = frozenset({"P1", "P2"})


def _json_for_prompt(obj: Any, *, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    raw = json.dumps(obj if obj is not None else {}, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + '"…[truncated]"'


def _normalize_issue(raw: dict[str, Any]) -> dict[str, Any] | None:
    priority = str(raw.get("priority") or "P3").upper()
    if priority not in ("P1", "P2", "P3"):
        priority = "P3"
    message = raw.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    out: dict[str, Any] = {"priority": priority, "message": message.strip()[:500]}
    raw_id = raw.get("component_id")
    if raw_id is not None:
        try:
            out["component_id"] = int(raw_id)
        except (TypeError, ValueError):
            if priority in _BLOCKING:
                return None
    elif priority in _BLOCKING:
        return None
    return out


def _component_css_and_tsx(comp: dict[str, Any]) -> str:
    return (comp.get("css_preview") or "") + (comp.get("tsx_preview") or "")


def _token_used_in_styles(token_value: str, styles: str) -> bool:
    """True if primary (or other) token appears in generated CSS/TSX."""
    if token_value in styles:
        return True
    normalized = token_value.strip().lower()
    if normalized and normalized in styles.lower():
        return True
    if token_value.startswith("#") and len(token_value) >= 4:
        var_name = f"--primary"
        if var_name in styles:
            return True
    return False


def _deterministic_issues(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Pre-LLM lint: token drift and missing spec variants (W-04)."""
    issues: list[dict[str, Any]] = []
    tokens = work.get("design_tokens") if isinstance(work.get("design_tokens"), dict) else {}
    primary = tokens.get("primary")

    for comp in work.get("components") or []:
        if not isinstance(comp, dict):
            continue
        if comp.get("status") != "validated":
            continue
        cid = comp.get("id")
        if cid is None:
            continue
        try:
            component_id = int(cid)
        except (TypeError, ValueError):
            continue

        styles = _component_css_and_tsx(comp)
        if primary and isinstance(primary, str) and primary.strip():
            if not _token_used_in_styles(primary.strip(), styles):
                issues.append(
                    {
                        "priority": "P2",
                        "component_id": component_id,
                        "message": (
                            f"Use design token primary ({primary}) in styles; "
                            "avoid unrelated palette."
                        ),
                    }
                )

        spec = comp.get("spec") if isinstance(comp.get("spec"), dict) else {}
        variants = spec.get("variants")
        if isinstance(variants, list) and len(variants) > 1:
            for variant in variants:
                if not isinstance(variant, str) or not variant.strip():
                    continue
                v = variant.strip()
                if v not in styles and f"--{v}" not in styles:
                    issues.append(
                        {
                            "priority": "P2",
                            "component_id": component_id,
                            "message": (
                                f"Variant `{v}` from spec must appear in CSS "
                                "(class modifier or token hook)."
                            ),
                        }
                    )

    return issues[:_MAX_ISSUES]


def _issues_from_failed_components(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Non-blocking notes for components that failed validation."""
    out: list[dict[str, Any]] = []
    for item in work.get("components") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "failed":
            continue
        cid = item.get("id")
        if cid is None:
            continue
        reason = item.get("error_reason") or "validation failed"
        out.append(
            {
                "priority": "P3",
                "component_id": int(cid),
                "message": f"Component failed validation: {reason}"[:500],
            }
        )
    return out


def _append_unique_issues(
    issues: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> None:
    seen = {(i.get("component_id"), i.get("message")) for i in issues}
    for item in candidates:
        key = (item.get("component_id"), item.get("message"))
        if key in seen:
            continue
        issues.append(item)
        seen.add(key)
        if len(issues) >= _MAX_ISSUES:
            break


def _merge_verification(
    llm: dict[str, Any],
    *,
    work: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = list(_deterministic_issues(work))

    raw_issues = llm.get("issues")
    llm_normalized: list[dict[str, Any]] = []
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if isinstance(item, dict):
                normalized = _normalize_issue(item)
                if normalized:
                    llm_normalized.append(normalized)
    _append_unique_issues(issues, llm_normalized)

    existing_ids = {i.get("component_id") for i in issues if i.get("component_id") is not None}
    for extra in _issues_from_failed_components(work):
        if extra.get("component_id") in existing_ids:
            continue
        issues.append(extra)
        if len(issues) >= _MAX_ISSUES:
            break

    approved = bool(llm.get("approved")) if "approved" in llm else not any(
        i.get("priority") in _BLOCKING for i in issues
    )
    revisions = [
        {
            "component_id": i["component_id"],
            "revision_instruction": i["message"],
        }
        for i in issues
        if i.get("priority") in _BLOCKING and i.get("component_id") is not None
    ]
    return {
        "issues": issues,
        "approved": approved,
        "revisions": revisions,
    }


def _fallback_pass(work: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on LLM failure: keep deterministic P2 issues (W-04)."""
    issues: list[dict[str, Any]] = list(_deterministic_issues(work))
    _append_unique_issues(issues, _issues_from_failed_components(work))
    blocking = [i for i in issues if i.get("priority") in _BLOCKING and i.get("component_id") is not None]
    revisions = [
        {
            "component_id": i["component_id"],
            "revision_instruction": i["message"],
        }
        for i in blocking
    ]
    return {
        "issues": issues,
        "approved": not any(i.get("priority") in _BLOCKING for i in issues),
        "revisions": revisions,
    }


class VerificationAgent(BaseAgent):
    work_queue = VERIFICATION_START
    result_queue = VERIFICATION_COMPLETE

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        work_payload = VerificationStartWorkPayload.model_validate(work.payload)
        work_dict = work_payload.model_dump()

        system = render_prompt("design_system_lead_system.jinja2")
        user = render_prompt(
            "verification_user.jinja2",
            design_tokens_json=_json_for_prompt(work_payload.design_tokens or {}),
            global_config_json=_json_for_prompt(work_payload.global_config or {}),
            components_json=_json_for_prompt(work_payload.components),
        )

        merged: dict[str, Any]
        try:
            raw = await complete_json(system, user)
            if isinstance(raw, dict):
                merged = _merge_verification(raw, work=work_dict)
            else:
                merged = _fallback_pass(work_dict)
        except Exception as exc:
            logger.warning(
                "verification LLM failed project_id=%s: %s",
                work.project_id,
                exc,
            )
            merged = _fallback_pass(work_dict)

        try:
            validated = VerificationCompletePayload.model_validate(merged)
        except Exception as exc:
            logger.warning("verification payload validation failed: %s", exc)
            validated = VerificationCompletePayload.model_validate(_fallback_pass(work_dict))

        return build_result(
            work,
            event=PipelineEvent.VERIFICATION_COMPLETE,
            payload=validated.model_dump(),
        )
