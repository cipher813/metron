"""Major-index intraday strip endpoint (the Overview "markets" row).

Global (not tenant-scoped) market data — SPY / QQQ / IWM as proxies for the
S&P 500 / Nasdaq 100 / Russell 2000, read from the data spine's intraday artifact and
refreshed client-side every ~5 min. The index/ETF quotes come from the licensed feed, so
the feature is feed-gated (Pro): this endpoint resolves the ``indices`` entitlement for
the deployment (honoring the owner tier-simulator preview headers) and returns an honest
locked response — with the upsell ``required_tier`` — in the no-feed beta, instead of
serving the data.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from api import entitlements
from api.config import settings
from api.db.session import get_session
from api.services import indices, security_perf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["indices"])


def _parse_feed(raw: str | None) -> bool | None:
    return None if raw is None else raw.strip().lower() == "true"


class IndexQuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    label: str
    last: float | None
    prev_close: float | None
    open: float | None
    change: float | None
    change_pct: float | None  # "Today" return
    session_date: str | None
    suspect: bool
    ytd_pct: float | None = None
    ltm_pct: float | None = None


class IndicesOut(BaseModel):
    available: bool
    reason: str | None = None
    required_tier: str | None = None  # set only when locked by tier/feed (the upsell)
    as_of_utc: str | None = None
    stale: bool = False
    indices: list[IndexQuoteOut] = []


@router.get("/indices/intraday", response_model=IndicesOut)
def get_indices_intraday(
    x_preview_tier: str | None = Header(default=None),
    x_preview_feed: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> IndicesOut:
    """Latest intraday levels for the major-index ETF proxies. Feed-gated: an unentitled
    deployment (the no-feed beta) gets ``available=false`` with ``required_tier`` so the
    UI renders a locked upsell; an entitled deployment whose feed hasn't published yet
    gets ``available=false`` with a reason and no ``required_tier``."""
    feat = entitlements.feature_state(
        "indices",
        default_tier=settings.default_tier,
        feed_entitled=settings.feed_entitled,
        simulator=settings.tier_simulator,
        preview_tier=x_preview_tier,
        preview_feed=_parse_feed(x_preview_feed),
    )
    if not feat["available"]:
        return IndicesOut(available=False, reason=feat["reason"], required_tier=feat["required_tier"])

    snap = indices.load_indices()
    # Enrich each index with YTD/LTM returns from cached daily closes (metron-ops#87) — so
    # Markets reads Today/YTD/LTM, TWR-comparable to the perf tiles. Best-effort: a symbol
    # with no cached history keeps None.
    if snap.available and snap.indices:
        syms = [q.symbol for q in snap.indices]
        today = date.today()
        # Ensure this endpoint owns its own close-history coverage instead of relying on a
        # prior Performance-page visit to have warmed price_bars for these proxies (else
        # YTD/LTM render "—" on the Overview). Best-effort: the underlying close fetch is a
        # SECONDARY enrichment — the primary deliverable (live levels + Today, from S3) is
        # already built, so a fetch failure is logged (recording surface) and the period
        # columns fall back to None rather than failing the whole strip.
        try:
            security_perf.ensure_index_history(session, syms, as_of=today)
        except Exception as e:
            logger.warning("index close-history backfill failed; YTD/LTM may be blank: %s", e)
        periods = security_perf.index_period_returns(session, syms, as_of=today)
        for q in snap.indices:
            r = periods.get(q.symbol)
            if r is not None:
                q.ytd_pct, q.ltm_pct = r
    return IndicesOut(
        available=snap.available,
        reason=snap.reason,
        as_of_utc=snap.as_of_utc,
        stale=snap.stale,
        indices=[IndexQuoteOut.model_validate(q) for q in snap.indices],
    )
