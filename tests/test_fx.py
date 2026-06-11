"""FX rate cache — fetch {CCY}USD=X, cache, look up; no fabrication on a missing rate."""

from __future__ import annotations

from datetime import date

import pytest

from api.db import models
from api.services import fx
from portfolio_analytics.prices import ClosePoint


def _fx_source(rates: dict[str, float]):
    def src(symbols, *, source=None):
        return {s: ClosePoint(date(2026, 6, 9), rates[s]) for s in symbols if s in rates}

    return src


class TestFx:
    def test_usd_is_identity(self, db_session):
        assert fx.latest_rate_to_base(db_session, "USD") == 1.0
        assert fx.latest_rate_to_base(db_session, "usd") == 1.0
        assert fx.latest_rate_to_base(db_session, "") == 1.0

    def test_missing_rate_is_none_not_one(self, db_session):
        # The no-fabrication rule: an unsourced currency returns None, never a 1.0 that
        # would silently treat 1 HKD as 1 USD.
        assert fx.latest_rate_to_base(db_session, "HKD") is None

    def test_refresh_and_lookup(self, db_session):
        n = fx.refresh_fx_rates(db_session, ["HKD", "GBP", "USD"], source=_fx_source({"HKDUSD=X": 0.128, "GBPUSD=X": 1.27}))
        assert n == 2  # USD skipped
        assert fx.latest_rate_to_base(db_session, "HKD") == pytest.approx(0.128)
        assert fx.latest_rate_to_base(db_session, "GBP") == pytest.approx(1.27)

    def test_refresh_is_idempotent_per_day(self, db_session):
        fx.refresh_fx_rates(db_session, ["HKD"], source=_fx_source({"HKDUSD=X": 0.128}))
        fx.refresh_fx_rates(db_session, ["HKD"], source=_fx_source({"HKDUSD=X": 0.130}))
        rows = db_session.query(models.FxRate).filter(models.FxRate.currency == "HKD").all()
        assert len(rows) == 1 and float(rows[0].rate) == pytest.approx(0.130)  # updated, not duplicated

    def test_rates_to_base_batch(self, db_session):
        fx.refresh_fx_rates(db_session, ["HKD"], source=_fx_source({"HKDUSD=X": 0.128}))
        out = fx.rates_to_base(db_session, ["USD", "HKD", "JPY"])
        assert out["USD"] == 1.0
        assert out["HKD"] == pytest.approx(0.128)
        assert out["JPY"] is None  # no rate cached
