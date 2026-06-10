"""Portfolio performance over the forward-recorded NAV snapshot series.

Market value can't be reconstructed for the past from cost basis alone, so — like
robodashboard — NAV history accumulates as the user refreshes prices: each refresh
records one snapshot (idempotent per day). ``performance()`` then derives time-weighted
return, cash-flow-adjusted cumulative return, and annualization from that series using
the shared ``alpha_engine_lib.quant.returns`` primitives.

Metrics are None until ≥2 snapshots exist — the caller shows "history is building",
never a fabricated number.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from alpha_engine_lib.quant.returns import ValuationPoint, annualize, cumulative_return, time_weighted_return
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import models
from api.services import analytics
from portfolio_analytics.domain.ledger import TxnType
from portfolio_analytics.prices import fetch_latest_closes


def _external_flow_on(session: Session, tenant_id: uuid.UUID, portfolio_id: uuid.UUID, when: date) -> float:
    """Net external cash flow into the portfolio on ``when`` (deposits +, withdrawals −).

    BUY/SELL/DIVIDEND/FEE are internal to the portfolio and are NOT external flows;
    only DEPOSIT/WITHDRAWAL move capital across the portfolio boundary."""
    rows = session.execute(
        select(models.Transaction.txn_type, models.Transaction.amount)
        .join(models.Account, models.Transaction.account_id == models.Account.id)
        .where(
            models.Transaction.tenant_id == tenant_id,
            models.Account.portfolio_id == portfolio_id,
            models.Transaction.trade_date == when,
            models.Transaction.txn_type.in_([TxnType.DEPOSIT.value, TxnType.WITHDRAWAL.value]),
        )
    ).all()
    flow = 0.0
    for txn_type, amount in rows:
        flow += float(amount) if txn_type == TxnType.DEPOSIT.value else -float(amount)
    return flow


def record_snapshot(
    session: Session, tenant_id: uuid.UUID, portfolio_id: uuid.UUID, *, today: date, source=None
) -> models.NavSnapshot | None:
    """Record today's NAV snapshot (idempotent per day). Returns the row, or None when
    NAV isn't computable yet (no holding has a cached price → nothing to value)."""
    held = analytics.valued_holdings(session, tenant_id, portfolio_id)
    priced = [h for h in held if h.market_value is not None]
    if not priced:
        return None  # can't snapshot a NAV we can't value — never fabricate one
    nav = sum(h.market_value for h in priced)
    cost_basis = sum(h.cost_basis for h in held)
    flow = _external_flow_on(session, tenant_id, portfolio_id, today)
    spy_point = fetch_latest_closes(["SPY"], source=source).get("SPY")
    spy_close = spy_point.close if spy_point else None

    row = session.scalars(
        select(models.NavSnapshot).where(
            models.NavSnapshot.tenant_id == tenant_id,
            models.NavSnapshot.portfolio_id == portfolio_id,
            models.NavSnapshot.snap_date == today,
        )
    ).first()
    if row is None:
        row = models.NavSnapshot(tenant_id=tenant_id, portfolio_id=portfolio_id, snap_date=today)
        session.add(row)
    row.nav = nav
    row.cost_basis = cost_basis
    row.external_flow = flow
    if spy_close is not None:
        row.spy_close = spy_close
    session.commit()
    session.refresh(row)
    return row


@dataclass
class PerfPoint:
    snap_date: date
    nav: float
    external_flow: float
    spy_close: float | None


@dataclass
class PerformanceSummary:
    n_snapshots: int
    first_date: date | None = None
    last_date: date | None = None
    days: int = 0
    latest_nav: float | None = None
    latest_cost_basis: float | None = None
    net_contributions: float = 0.0
    cumulative_return: float | None = None
    twr: float | None = None
    annualized_twr: float | None = None
    points: list[PerfPoint] = field(default_factory=list)


def performance(session: Session, tenant_id: uuid.UUID, portfolio_id: uuid.UUID) -> PerformanceSummary:
    """Performance metrics over the recorded snapshot series. Returns counts + None
    metrics until ≥2 snapshots exist."""
    snaps = session.scalars(
        select(models.NavSnapshot)
        .where(models.NavSnapshot.tenant_id == tenant_id, models.NavSnapshot.portfolio_id == portfolio_id)
        .order_by(models.NavSnapshot.snap_date)
    ).all()
    points = [
        PerfPoint(
            snap_date=s.snap_date,
            nav=float(s.nav),
            external_flow=float(s.external_flow),
            spy_close=float(s.spy_close) if s.spy_close is not None else None,
        )
        for s in snaps
    ]
    summary = PerformanceSummary(n_snapshots=len(points), points=points)
    if not points:
        return summary
    summary.first_date = points[0].snap_date
    summary.last_date = points[-1].snap_date
    summary.latest_nav = points[-1].nav
    summary.latest_cost_basis = float(snaps[-1].cost_basis)
    if len(points) < 2:
        return summary

    summary.days = (points[-1].snap_date - points[0].snap_date).days
    # Contributions after the first snapshot inflate end NAV without being performance.
    summary.net_contributions = sum(p.external_flow for p in points[1:])
    summary.cumulative_return = cumulative_return(
        points[0].nav, points[-1].nav, net_contributions=summary.net_contributions
    )
    # The lib wants each point's value BEFORE its flow; a snapshot's NAV is recorded
    # end-of-day (post-flow), so subtract the day's net deposit to recover the pre-flow
    # value. Then chaining end.value / (begin.value + begin.flow) neutralizes the flow.
    summary.twr = time_weighted_return(
        [ValuationPoint(when=p.snap_date, value=p.nav - p.external_flow, flow=p.external_flow) for p in points]
    )
    if summary.twr is not None and summary.days > 0:
        summary.annualized_twr = annualize(summary.twr, summary.days)
    return summary
