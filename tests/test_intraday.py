"""Live intraday revaluation (metron-ops#79) — fresh NAV from current balances.

Service: overlays the data-spine intraday ``quotes`` (per-held-ticker last price) on the
EOD close, feed-gated, with per-symbol fallback (stale / missing / suspect → EOD). The
overlaid price map flows into ``valued_holdings`` / ``summary`` so the headline NAV
recomputes from live balances. Persistence (the daily snapshot) never sees intraday.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from api.config import settings
from api.db import models
from api.services import analytics, intraday

_AS_OF = "2026-06-12T15:00:00Z"
_NOW = datetime(2026, 6, 12, 15, 3, tzinfo=UTC)   # 3 min after the write — fresh
_STALE_NOW = datetime(2026, 6, 12, 15, 45, tzinfo=UTC)  # 45 min after — stale


def _art(quotes: dict) -> dict:
    return {"schema_version": 1, "as_of_utc": _AS_OF, "source": "yfinance_delayed", "quotes": quotes}


def _seed_one_holding(session, *, symbol="AAPL", yf_symbol="AAPL", qty=10, buy_px=100.0, eod_close=120.0):
    """One USD holding with a BUY (cost basis) + a cached EOD close bar."""
    tenant = models.Tenant(name="t")
    session.add(tenant)
    session.flush()
    pf = models.Portfolio(tenant_id=tenant.id, name="P", base_currency="USD")
    session.add(pf)
    session.flush()
    acct = models.Account(
        tenant_id=tenant.id, portfolio_id=pf.id, broker="csv", external_id="A1", currency="USD"
    )
    sec = models.Security(symbol=symbol, yf_symbol=yf_symbol, currency="USD")
    session.add_all([acct, sec])
    session.flush()
    session.add(
        models.Transaction(
            tenant_id=tenant.id, account_id=acct.id, security_id=sec.id,
            txn_type="BUY", quantity=qty, price=buy_px, amount=qty * buy_px, currency="USD",
            trade_date=date(2024, 1, 1), source_key="buy-1",
        )
    )
    session.add(
        models.PriceBar(security_id=sec.id, bar_date=date(2026, 6, 11), close=eod_close, currency="USD")
    )
    session.commit()
    return tenant.id, pf.id


class TestLoadQuotes:
    def test_fresh_quotes(self):
        quotes, as_of, stale = intraday.load_quotes(reader=lambda: _art({"AAPL": {"last": 130.0}}), now=_NOW)
        assert quotes == {"AAPL": {"last": 130.0}} and as_of == _AS_OF and stale is False

    def test_stale_when_old(self):
        _, _, stale = intraday.load_quotes(reader=lambda: _art({"AAPL": {"last": 130.0}}), now=_STALE_NOW)
        assert stale is True

    def test_missing_artifact(self):
        quotes, as_of, stale = intraday.load_quotes(reader=lambda: None, now=_NOW)
        assert quotes == {} and as_of is None and stale is True


class TestLivePrices:
    def test_not_applied_without_feed(self, db_session):
        tid, pid = _seed_one_holding(db_session)
        prices, meta = intraday.live_prices(
            db_session, ["AAPL"], feed_entitled=False, reader=lambda: _art({"AAPL": {"last": 130.0}}), now=_NOW
        )
        assert prices is None and meta.applied is False and meta.reason == "feed"

    def test_not_applied_when_stale(self, db_session):
        _seed_one_holding(db_session)
        prices, meta = intraday.live_prices(
            db_session, ["AAPL"], feed_entitled=True,
            reader=lambda: _art({"AAPL": {"last": 130.0}}), now=_STALE_NOW,
        )
        assert prices is None and meta.applied is False and meta.reason == "stale"

    def test_overlay_merges_intraday_over_eod(self, db_session):
        _seed_one_holding(db_session)
        prices, meta = intraday.live_prices(
            db_session, ["AAPL"], feed_entitled=True,
            reader=lambda: _art({"AAPL": {"last": 130.0, "session_date": "2026-06-12"}}), now=_NOW,
        )
        assert meta.applied is True and meta.n_priced == 1
        assert prices["AAPL"].close == 130.0  # intraday last, not the 120 EOD close
        assert prices["AAPL"].bar_date == date(2026, 6, 12)

    def test_suspect_quote_skipped(self, db_session):
        _seed_one_holding(db_session)
        prices, meta = intraday.live_prices(
            db_session, ["AAPL"], feed_entitled=True,
            reader=lambda: _art({"AAPL": {"last": 999.0, "suspect": True}}), now=_NOW,
        )
        assert prices is None and meta.applied is False  # no usable quote → EOD valuation

    def test_missing_last_skipped(self, db_session):
        _seed_one_holding(db_session)
        prices, meta = intraday.live_prices(
            db_session, ["AAPL"], feed_entitled=True,
            reader=lambda: _art({"AAPL": {"prev_close": 120.0}}), now=_NOW,
        )
        assert prices is None and meta.applied is False


class TestLiveValuation:
    def test_nav_recomputes_from_intraday(self, db_session):
        tid, pid = _seed_one_holding(db_session, qty=10, eod_close=120.0)
        # EOD NAV = 10 × 120 = 1200.
        eod = analytics.summary(db_session, tid, pid)
        assert eod.market_value == 1200.0
        # Live NAV = 10 × 130 (intraday last).
        prices, _ = intraday.live_prices(
            db_session, ["AAPL"], feed_entitled=True, reader=lambda: _art({"AAPL": {"last": 130.0}}), now=_NOW
        )
        live = analytics.summary(db_session, tid, pid, prices=prices)
        assert live.market_value == 1300.0

    def test_persistence_path_stays_eod(self, db_session):
        """valued_holdings with no override (the snapshot path) always uses EOD close —
        intraday never enters the recorded NAV history."""
        tid, pid = _seed_one_holding(db_session, qty=10, eod_close=120.0)
        held = analytics.valued_holdings(db_session, tid, pid)  # default = EOD
        assert held[0].market_value == 1200.0


@pytest.fixture()
def tenant():
    return str(uuid.uuid4())


class TestIntradayStatusEndpoint:
    def test_feed_off_reports_not_applied(self, client, tenant, monkeypatch):
        monkeypatch.setattr(settings, "feed_entitled", False)
        pid = client.post("/portfolios", json={"name": "P"}, headers={"X-Tenant-Id": tenant}).json()["id"]
        r = client.get(f"/portfolios/{pid}/intraday", headers={"X-Tenant-Id": tenant})
        assert r.status_code == 200
        body = r.json()
        assert body["applied"] is False and body["reason"] == "feed"

    def test_feed_on_no_holdings_unavailable(self, client, tenant, monkeypatch):
        monkeypatch.setattr(settings, "feed_entitled", True)
        # No holdings → nothing to overlay; wiring still returns a clean status (not 500).
        pid = client.post("/portfolios", json={"name": "P"}, headers={"X-Tenant-Id": tenant}).json()["id"]
        r = client.get(f"/portfolios/{pid}/intraday", headers={"X-Tenant-Id": tenant})
        assert r.status_code == 200
        assert r.json()["applied"] is False
