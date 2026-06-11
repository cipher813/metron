"""Map a broker-reported instrument to the symbol yfinance prices it under.

yfinance keys foreign listings by an exchange suffix (``1299.HK``, ``RIO.L``,
``SHOP.TO``) — a bare ``1299`` either fails to resolve or silently matches the wrong
US line. Brokers give us the listing **exchange** (IBKR Flex ``listingExchange``) and
the trade **currency**; this module turns those into the yfinance symbol.

Resolution order: explicit override (caller-supplied) → exchange code → currency
fallback → unchanged (US/USD). The result is stored once on ``Security.yf_symbol`` at
ingestion so it can be hand-corrected later from the Settings page rather than
recomputed on every fetch.
"""

from __future__ import annotations

# Broker listing-exchange code → yfinance suffix. Keys are upper-cased broker codes
# (IBKR Flex ``listingExchange`` mnemonics + common aliases). Exchange is preferred
# over currency because it is unambiguous (EUR alone spans many exchanges).
_EXCHANGE_SUFFIX: dict[str, str] = {
    "SEHK": ".HK", "HKEX": ".HK", "HKG": ".HK",            # Hong Kong
    "LSE": ".L", "LSEETF": ".L",                            # London
    "TSE": ".TO", "TSX": ".TO",                             # Toronto
    "VENTURE": ".V", "TSXV": ".V",                          # TSX Venture
    "ASX": ".AX",                                           # Australia
    "TSEJ": ".T", "TSEJP": ".T", "JPX": ".T",              # Tokyo
    "SGX": ".SI",                                           # Singapore
    "IBIS": ".DE", "FWB": ".DE", "XETRA": ".DE",           # Germany (Xetra)
    "SBF": ".PA", "ENEXT.FR": ".PA",                        # Paris
    "AEB": ".AS", "ENEXT.NL": ".AS",                        # Amsterdam
    "BVME": ".MI", "BIT": ".MI",                            # Milan
    "BM": ".MC", "BMEX": ".MC",                             # Madrid
    "EBS": ".SW", "VIRTX": ".SW",                           # Switzerland
    "SFB": ".ST", "OMX": ".ST",                             # Stockholm
    "KSE": ".KS", "KRX": ".KS",                             # Korea
    "NSE": ".NS", "BSE": ".BO",                             # India
    "TASE": ".TA",                                          # Tel Aviv
    "BVMF": ".SA",                                          # Brazil
}

# Currency-of-trade → yfinance suffix, used only when the exchange is unknown. Each
# maps to the single most-common listing venue for that currency; an instrument on a
# secondary venue (e.g. EUR across Frankfurt/Paris/Milan) needs an explicit exchange
# or a Settings override. USD intentionally absent → bare US symbol.
_CURRENCY_SUFFIX: dict[str, str] = {
    "HKD": ".HK",
    "GBP": ".L", "GBX": ".L", "GBp": ".L",
    "CAD": ".TO",
    "AUD": ".AX",
    "JPY": ".T",
    "SGD": ".SI",
    "KRW": ".KS",
    "INR": ".NS",
    "ILS": ".TA",
    "BRL": ".SA",
    "CHF": ".SW",
    "SEK": ".ST",
}


def to_yf_symbol(ticker: str, currency: str = "USD", exchange: str = "") -> str:
    """The symbol yfinance prices ``ticker`` under, given its currency and exchange.

    USD (or an unmappable foreign listing) returns the bare ticker unchanged — the
    fail-soft posture, since a wrong suffix is worse than none. A ticker that already
    carries a ``.SUFFIX`` is returned as-is (already yfinance-shaped)."""
    t = (ticker or "").strip().upper()
    if not t or "." in t:
        return t
    ccy = (currency or "").strip().upper()
    exch = (exchange or "").strip().upper()
    suffix = _EXCHANGE_SUFFIX.get(exch) or _CURRENCY_SUFFIX.get(ccy) or _CURRENCY_SUFFIX.get(currency.strip())
    return f"{t}{suffix}" if suffix else t


def fx_pair_symbol(currency: str, base: str = "USD") -> str:
    """yfinance FX symbol converting 1 unit of ``currency`` into ``base`` — e.g.
    ``HKDUSD=X``. Returns ``""`` for a no-op (same currency or missing input)."""
    ccy = (currency or "").strip().upper()
    b = (base or "USD").strip().upper()
    if not ccy or ccy == b:
        return ""
    return f"{ccy}{b}=X"
