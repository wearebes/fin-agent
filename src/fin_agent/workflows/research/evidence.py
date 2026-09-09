"""Bounded evidence formatting without cutting through financial records."""

from __future__ import annotations

import json
from typing import Any

from fin_agent.domain.types import EvidenceItem, FinancialStatementRecord


def compact_records(records: list[dict[str, Any]], limit: int = 12000) -> str:
    """Keep complete records in caller-defined priority order; disclose omissions."""
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    if len(payload) <= limit:
        return payload
    kept: list[dict[str, Any]] = []
    for record in records:
        candidate = json.dumps(
            {"records": [*kept, record], "omitted_records": len(records) - len(kept) - 1},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(candidate) > limit:
            continue
        kept.append(record)
    return json.dumps(
        {"records": kept, "omitted_records": len(records) - len(kept)},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def render_evidence(evidence: list[EvidenceItem], limit: int = 60000) -> str:
    """Expose newly retrieved evidence even after the prompt budget is full."""
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in reversed(evidence):
        identity = (item.source, item.summary)
        if identity in seen:
            continue
        seen.add(identity)
        records.append(item.model_dump())
    return compact_records(records, limit=limit)


def format_financials(records: list[FinancialStatementRecord]) -> str:
    latest = sorted(
        records, key=lambda row: (row.fiscal_year, row.fiscal_quarter or 0), reverse=True
    )[:8]
    return compact_records([row.model_dump(mode="json", exclude_none=True) for row in latest])
