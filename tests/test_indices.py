"""Major-index intraday strip — the Overview "markets" row (SPY/QQQ/IWM proxies).

Service: reads the data-spine intraday artifact's ``indices`` map, computes change /
change% vs prior close, maps each ETF to its index label, flags staleness, and reports
unavailable WITH a reason (never fabricated) when the artifact / its indices are absent.
Endpoint: feed-gated (Pro) — locked WITH the upsell tier in the no-feed beta, honoring
the owner tier-simulator preview header.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from api.config import settings
from api.services import indices

_AS_OF = "2026-06-12T15:00:00Z"
_NOW = datetime(2026, 6, 12, 15, 3, tzinfo=UTC)  # 3 min after the write — fresh
_ART = {
    "schema_version": 2,
    "as_of_utc": _AS_OF,
    "source": "yfinance_delayed",
    "quotes": {"AAPL": {"last": 202.1, "prev_close": 201.5}},
    "indices": {
        "SPY": {"last": 605.2, "open": 603.0, "prev_close": 602.4, "session_date": "2026-06-12"},
        "QQQ": {"last": 540.1, "open": 538.5, "prev_close": 537.0, "session_date": "2026-06-12"},
        "IWM": {"last": 215.3, "open": 216.0, "prev_close": 216.5, "session_date": "2026-06-12"},
    },
}


class TestLoadIndices:
    def test_builds_quotes_with_change_labels_and_order(self):
        snap = indices.load_indices(reader=lambda: _ART, now=_NOW)
        assert snap.available is True and snap.stale is False
        assert snap.as_of_utc == _AS_OF
        assert [q.symbol for q in snap.indices] == ["SPY", "QQQ", "IWM"]  # display order
        spy = snap.indices[0]
        assert spy.label == "S&P 500"
        assert spy.change == pytest.approx(605.2 - 602.4)
        assert spy.change_pct == pytest.approx((605.2 - 602.4) / 602.4)
        # A down index keeps the sign — never abs/clamped.
        iwm = snap.indices[2]
        assert iwm.label == "Russell 2000" and iwm.change == pytest.approx(215.3 - 216.5)
        assert iwm.change_pct < 0

    def test_unavailable_when_no_artifact(self):
        snap = indices.load_indices(reader=lambda: None, now=_NOW)
        assert snap.available is False and snap.reason

    def test_unavailable_when_indices_absent_but_as_of_preserved(self):
        snap = indices.load_indices(reader=lambda: {"as_of_utc": _AS_OF, "indices": {}}, now=_NOW)
        assert snap.available is False and snap.reason
        assert snap.as_of_utc == _AS_OF

    def test_absent_symbol_omitted_not_fabricated(self):
        art = {"as_of_utc": _AS_OF, "indices": {"SPY": _ART["indices"]["SPY"]}}
        snap = indices.load_indices(reader=lambda: art, now=_NOW)
        assert [q.symbol for q in snap.indices] == ["SPY"]

    def test_missing_prev_close_yields_none_change(self):
        art = {"as_of_utc": _AS_OF, "indices": {"SPY": {"last": 605.2}}}
        snap = indices.load_indices(reader=lambda: art, now=_NOW)
        q = snap.indices[0]
        assert q.last == 605.2 and q.change is None and q.change_pct is None

    def test_stale_when_snapshot_old(self):
        old_now = datetime(2026, 6, 12, 16, 0, tzinfo=UTC)  # ~1h after the write
        snap = indices.load_indices(reader=lambda: _ART, now=old_now)
        assert snap.available is True and snap.stale is True

    def test_suspect_flag_passthrough(self):
        art = {"as_of_utc": _AS_OF, "indices": {"SPY": {"last": 9.9, "prev_close": 602.4, "suspect": True}}}
        snap = indices.load_indices(reader=lambda: art, now=_NOW)
        assert snap.indices[0].suspect is True


class TestIndicesEndpoint:
    def test_available_returns_indices_on_feed_deployment(self, client, monkeypatch):
        # Default settings: personal tier + feed entitled → indices available.
        monkeypatch.setattr(indices, "_default_reader", lambda: _ART)
        body = client.get("/indices/intraday").json()
        assert body["available"] is True and body["required_tier"] is None
        assert [q["symbol"] for q in body["indices"]] == ["SPY", "QQQ", "IWM"]
        assert body["indices"][0]["label"] == "S&P 500"

    def test_locked_when_feed_not_entitled(self, client, monkeypatch):
        called = []
        monkeypatch.setattr(indices, "_default_reader", lambda: called.append(1) or _ART)
        monkeypatch.setattr(settings, "feed_entitled", False)  # the no-feed beta
        body = client.get("/indices/intraday").json()
        assert body["available"] is False
        assert body["reason"] == "feed" and body["required_tier"] == "pro"
        assert not called  # locked → never reads the (licensed) data

    def test_simulator_preview_feed_off_locks(self, client, monkeypatch):
        monkeypatch.setattr(indices, "_default_reader", lambda: _ART)
        monkeypatch.setattr(settings, "tier_simulator", True)
        body = client.get("/indices/intraday", headers={"X-Preview-Feed": "false"}).json()
        assert body["available"] is False and body["required_tier"] == "pro"

    def test_entitled_but_no_data_is_unavailable_without_required_tier(self, client, monkeypatch):
        monkeypatch.setattr(indices, "_default_reader", lambda: None)
        body = client.get("/indices/intraday").json()
        assert body["available"] is False and body["required_tier"] is None and body["reason"]
