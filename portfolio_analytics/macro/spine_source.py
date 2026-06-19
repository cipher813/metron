"""Macro indicator series from the alpha-engine-data **data spine**.

`alpha-engine-data` is the single market/reference-data ground truth for the Nous Ergon
system — Metron reads macro indicators from its S3 artifact and makes no direct FRED
call. Reads `market_data/macro/latest.json` (produced by
alpha-engine-data/collectors/metron_market_data.py), keyed by FRED series id.

Fail-soft: a missing artifact / absent series → omitted (the Macro page surfaces it as
unavailable, never fabricated). Bucket from ``MARKET_DATA_BUCKET`` (default
``alpha-engine-research``).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date

from portfolio_analytics.macro.source import Indicator, MacroObservation, MacroSeries

logger = logging.getLogger(__name__)

MACRO_LATEST_KEY = "market_data/macro/latest.json"


def _bucket() -> str:
    return os.environ.get("MARKET_DATA_BUCKET", "alpha-engine-research")


def _s3():
    import boto3
    return boto3.client("s3")


def _read_json(s3, key: str) -> dict | None:
    try:
        obj = s3.get_object(Bucket=_bucket(), Key=key)
        return json.loads(obj["Body"].read())
    except Exception as e:
        logger.warning("data-spine read failed %s: %s", key, e)
        return None


def spine_macro_series(indicators: list[Indicator], api_key: str = "", *, s3=None) -> dict[str, MacroSeries]:
    """Recent observation series per indicator key, from the spine. ``api_key`` is
    ignored (the producer already fetched FRED) — kept for ``MacroSource`` compatibility.
    Indicators whose series the artifact lacks are omitted."""
    art = _read_json(s3 or _s3(), MACRO_LATEST_KEY) or {}
    series_by_id = art.get("series", {})
    next_release_by_id = art.get("next_release", {}) or {}  # spine schema v2 (metron-ops#49)
    out: dict[str, MacroSeries] = {}
    for ind in indicators:
        rows = series_by_id.get(ind.series_id)
        if not rows:
            continue
        obs: list[MacroObservation] = []
        for row in rows:
            try:
                obs.append(MacroObservation(obs_date=date.fromisoformat(row[0]), value=float(row[1])))
            except (TypeError, ValueError, IndexError):
                continue
        if obs:
            nr = None
            raw = next_release_by_id.get(ind.series_id)
            if raw:
                try:
                    nr = date.fromisoformat(str(raw))
                except ValueError:
                    nr = None
            out[ind.key] = MacroSeries(observations=obs, next_release=nr)
    return out


def spine_macro_events(*, s3=None) -> list[dict]:
    """The forward macro event calendar (FOMC + curated FRED releases) from the spine's
    macro artifact (schema v2 — metron-ops#49) → ``[{date, kind, series_id, label}, …]``.
    Fail-soft: a missing artifact / field → ``[]`` (the Calendar shows no macro rows, never
    fabricated)."""
    art = _read_json(s3 or _s3(), MACRO_LATEST_KEY) or {}
    events = art.get("release_events")
    return events if isinstance(events, list) else []
