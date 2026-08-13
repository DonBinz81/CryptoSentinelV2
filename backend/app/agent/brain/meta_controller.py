"""Claude meta-controller with constrained trading powers."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

import httpx

from backend.app.agent.brain.models import BrainDecision, BrainUsage
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger

logger = get_logger("agent.brain")


class MetaControllerError(RuntimeError):
    """Raised when the meta-controller cannot produce a decision."""


class ClaudeMetaController:
    """LLM meta-controller that can approve, reduce, block, or skip only."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if self.settings.anthropic_api_key:
            logger.info(
                "claude_meta_controller_ready",
                model=self.settings.anthropic_model,
                max_tokens=self.settings.anthropic_max_tokens,
            )
        else:
            logger.warning("claude_meta_controller_no_api_key", fallback="local_deterministic")

    async def decide(self, *, signal: dict[str, Any], risk: dict[str, Any]) -> tuple[BrainDecision, BrainUsage | None]:
        if not self.settings.anthropic_api_key:
            logger.warning("claude_meta_controller_skipped", reason="no_api_key")
            return self._local_fallback(signal, risk), None
        logger.info(
            "claude_meta_controller_calling",
            model=self.settings.anthropic_model,
            asset=signal.get("asset"),
            signal_action=signal.get("action"),
        )
        try:
            payload = self._build_payload(signal, risk)
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
            if not response.is_success:
                logger.warning(
                    "claude_meta_controller_http_error",
                    status_code=response.status_code,
                    model=self.settings.anthropic_model,
                    body=response.text[:300],
                )
            response.raise_for_status()
            body = response.json()
            result = self._parse_response(body)
            usage_data = body.get("usage", {})
            usage = BrainUsage(
                model=self.settings.anthropic_model,
                input_tokens=int(usage_data.get("input_tokens", 0)),
                output_tokens=int(usage_data.get("output_tokens", 0)),
            )
            logger.info(
                "claude_meta_controller_ok",
                action=result.action,
                confidence=str(result.confidence),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
            return result, usage
        except Exception as exc:
            logger.warning(
                "claude_meta_controller_failed",
                error=str(exc),
                model=self.settings.anthropic_model,
                error_type=type(exc).__name__,
            )
            if self.settings.execution_mode == "dry_run":
                return self._local_fallback(signal, risk, reason_prefix="claude_unavailable_dry_run"), None
            raise MetaControllerError("claude_meta_controller_unavailable") from exc

    def _local_fallback(
        self,
        signal: dict[str, Any],
        risk: dict[str, Any],
        *,
        reason_prefix: str = "claude_not_configured_dry_run",
    ) -> BrainDecision:
        if self.settings.execution_mode != "dry_run":
            return BrainDecision(
                action="block",
                confidence=Decimal("0"),
                reasoning="Claude unavailable; fail-closed outside dry-run.",
            )
        if not risk.get("allowed"):
            return BrainDecision(
                action="block",
                confidence=Decimal("0"),
                reasoning=f"{reason_prefix}; risk blocked: {risk.get('reason')}",
            )
        quality = Decimal(str(signal.get("quality", 0)))
        if quality >= Decimal("0.85"):
            return BrainDecision(
                action="approve",
                confidence=quality,
                reasoning=f"{reason_prefix}; deterministic dry-run approval.",
            )
        if quality >= Decimal("0.65"):
            return BrainDecision(
                action="reduce",
                confidence=quality,
                size_multiplier=Decimal("0.5"),
                reasoning=f"{reason_prefix}; deterministic dry-run reduced size.",
            )
        return BrainDecision(
            action="skip",
            confidence=quality,
            reasoning=f"{reason_prefix}; quality below dry-run threshold.",
        )

    def _build_payload(self, signal: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.settings.anthropic_model,
            "max_tokens": min(self.settings.anthropic_max_tokens, 1024),
            "system": (
                "You are a constrained trading meta-controller. "
                "You may only choose approve, reduce, block, or skip. "
                "Never increase leverage, never invert direction, never change strategy parameters. "
                "Return strict JSON with action, confidence, size_multiplier, reasoning."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "signal": signal,
                            "risk": risk,
                            "allowed_actions": ["approve", "reduce", "block", "skip"],
                        },
                        default=str,
                    ),
                }
            ],
        }

    def _parse_response(self, payload: dict[str, Any]) -> BrainDecision:
        content = payload.get("content") or []
        text = ""
        if content and isinstance(content[0], dict):
            text = str(content[0].get("text", ""))
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        stripped = re.sub(r"```(?:json)?\s*", "", text).strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            # Last resort: find first {...} block in the text
            match = re.search(r"\{.*\}", stripped, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError as exc:
                    raise MetaControllerError("claude_returned_non_json") from exc
            else:
                raise MetaControllerError("claude_returned_non_json")
        action = str(parsed.get("action", "block")).lower()
        if action not in {"approve", "reduce", "block", "skip"}:
            action = "block"
        confidence = _decimal_between(parsed.get("confidence", 0), Decimal("0"), Decimal("1"))
        multiplier = _decimal_between(parsed.get("size_multiplier", 1), Decimal("0"), Decimal("1"))
        return BrainDecision(
            action=action,  # type: ignore[arg-type]
            confidence=confidence,
            size_multiplier=multiplier,
            reasoning=str(parsed.get("reasoning") or "Claude decision without reasoning."),
        )


def _decimal_between(value: Any, minimum: Decimal, maximum: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception:
        parsed = minimum
    return max(minimum, min(maximum, parsed))
