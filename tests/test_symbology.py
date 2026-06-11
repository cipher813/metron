"""yfinance symbology — map a broker ticker + currency + exchange to the symbol
yfinance prices it under (foreign listings need an exchange suffix)."""

from __future__ import annotations

from portfolio_analytics.prices.symbology import fx_pair_symbol, to_yf_symbol


class TestToYfSymbol:
    def test_us_usd_unchanged(self):
        assert to_yf_symbol("AAPL", "USD", "") == "AAPL"
        assert to_yf_symbol("aapl", "USD", "") == "AAPL"

    def test_hong_kong_by_exchange(self):
        # The bug: 1299 (AIA, HK) must resolve to 1299.HK, not bare 1299.
        assert to_yf_symbol("1299", "HKD", "SEHK") == "1299.HK"

    def test_falls_back_to_currency_when_exchange_unknown(self):
        assert to_yf_symbol("1299", "HKD", "") == "1299.HK"
        assert to_yf_symbol("RIO", "GBP", "") == "RIO.L"
        assert to_yf_symbol("SHOP", "CAD", "") == "SHOP.TO"

    def test_exchange_preferred_over_currency(self):
        assert to_yf_symbol("RIO", "GBP", "LSE") == "RIO.L"
        assert to_yf_symbol("BHP", "AUD", "ASX") == "BHP.AX"

    def test_already_suffixed_returned_asis(self):
        assert to_yf_symbol("1299.HK", "HKD", "SEHK") == "1299.HK"

    def test_unmappable_foreign_left_bare(self):
        # An unknown currency with no exchange falls through to the bare ticker
        # (a wrong suffix is worse than none).
        assert to_yf_symbol("FOO", "XYZ", "") == "FOO"

    def test_empty_ticker(self):
        assert to_yf_symbol("", "HKD", "SEHK") == ""


class TestFxPairSymbol:
    def test_foreign(self):
        assert fx_pair_symbol("HKD") == "HKDUSD=X"
        assert fx_pair_symbol("gbp") == "GBPUSD=X"

    def test_base_is_noop(self):
        assert fx_pair_symbol("USD") == ""
        assert fx_pair_symbol("") == ""

    def test_custom_base(self):
        assert fx_pair_symbol("USD", "EUR") == "USDEUR=X"
        assert fx_pair_symbol("EUR", "EUR") == ""
