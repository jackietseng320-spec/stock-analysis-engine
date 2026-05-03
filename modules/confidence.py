from datetime import datetime, timezone
from typing import Any, Optional


def tag(
    value: Any,
    source: str,
    data_type: str,
    delay_note: Optional[str] = None,
    needs_manual_review: bool = False,
    confidence_level: Optional[str] = None,
) -> dict:
    level_map = {
        "sec_edgar": "high",
        "yahoo_finance": "medium",
        "user_input": "unverified",
        "system_estimate": "low",
        "public_market": "medium",
    }
    return {
        "value": value,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_type": data_type,
        "delay_note": delay_note,
        "needs_manual_review": needs_manual_review,
        "confidence_level": confidence_level or level_map.get(source, "low"),
    }


def official(value: Any, source: str = "sec_edgar") -> dict:
    return tag(value, source, "confirmed", confidence_level="high")


def market(value: Any, delay: str = "可能 15–20 分鐘延遲") -> dict:
    return tag(value, "yahoo_finance", "public_market", delay_note=delay, confidence_level="medium")


def inferred(value: Any, note: Optional[str] = None) -> dict:
    return tag(value, "system_estimate", "inference", delay_note=note, confidence_level="low")


def user(value: Any) -> dict:
    return tag(value, "user_input", "user_input",
               needs_manual_review=True, confidence_level="unverified")


def qualitative(value: Any) -> dict:
    return tag(value, "gpt_inference", "inference",
               needs_manual_review=True, confidence_level="low")
