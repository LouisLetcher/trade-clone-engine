from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from trade_clone_engine.db import ExecutedTrade, ObservedTrade, session_scope


@dataclass
class Summary:
    total_observed: int
    total_executed: int
    success: int
    failed: int
    skipped: int


def get_summary(SessionFactory) -> Summary:
    with session_scope(SessionFactory) as s:
        total_observed = s.scalar(select(func.count()).select_from(ObservedTrade)) or 0
        total_executed = s.scalar(select(func.count()).select_from(ExecutedTrade)) or 0
        success = s.scalar(select(func.count()).select_from(ExecutedTrade).where(ExecutedTrade.status == "success")) or 0
        failed = s.scalar(select(func.count()).select_from(ExecutedTrade).where(ExecutedTrade.status == "failed")) or 0
        skipped = s.scalar(select(func.count()).select_from(ExecutedTrade).where(ExecutedTrade.status == "skipped")) or 0
        return Summary(
            total_observed=total_observed,
            total_executed=total_executed,
            success=success,
            failed=failed,
            skipped=skipped,
        )
