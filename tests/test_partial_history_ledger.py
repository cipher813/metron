"""Regression: a broker activity feed that starts MID-POSITION must degrade per
(account, ticker) — never 500 every portfolio view.

The live bug (2026-06-12): the first E*TRADE sync via SnapTrade imported activities
whose history began after the position was opened — a ``SELL 27 SQ`` with no prior
BUY in the feed. The strict domain ledger raises on that (fail-loud, correctly), but
the API layer built ONE global ledger over all accounts, so the single unreplayable
group took down ``/accounts``, ``/holdings``, ``/realized``, Tax, and the portfolio
page itself ("Couldn't load this portfolio").

Two fixes under test here:
1. ``build_portfolio_ledger`` — per-(account, ticker) FIFO replay; an unreplayable
   group is skipped + flagged (WARN-logged), everything else survives. Per-account
   grouping is also the documented lot-relief semantics (a SELL in one account never
   closes a lot bought in another — mirrors ``reconstruct_tranches``).
2. ``_snapshot_sourced_account_ids`` — snapshot-sourced is classified by BROKER
   (``SNAPSHOT_SOURCES``), not by having position rows: an emptied SnapTrade account
   (activities, zero positions) is still snapshot-sourced, and its partial activity
   history must not fabricate current holdings.
"""

from __future__ import annotations

import uuid
from datetime import date

from api.db import models
from api.services import analytics
from portfolio_analytics.domain.ledger import Transaction, TxnType


def _txn(ticker: str, txn_type: TxnType, when: date, qty: float = 0.0, price: float = 0.0, amount: float = 0.0) -> Transaction:
    return Transaction(when=when, type=txn_type, ticker=ticker, quantity=qty, price=price, amount=amount)


class TestBuildPortfolioLedger:
    def test_partial_history_group_flagged_not_fatal(self):
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        txns = [
            # Account 1, AAPL: complete history.
            (a1, _txn("AAPL", TxnType.BUY, date(2024, 1, 1), qty=10, price=100.0)),
            (a1, _txn("AAPL", TxnType.SELL, date(2024, 6, 1), qty=4, price=150.0)),
            # Account 2, SQ: history starts mid-position — SELL with no visible BUY
            # (the live E*TRADE shape).
            (a2, _txn("SQ", TxnType.SELL, date(2024, 7, 17), qty=27, price=64.0)),
        ]
        ledger, incomplete = analytics.build_portfolio_ledger(txns)

        # The broken group is flagged with its identity + reason…
        assert len(incomplete) == 1
        assert incomplete[0].account_id == a2
        assert incomplete[0].ticker == "SQ"
        assert "exceeds" in incomplete[0].error
        # …and every other group is intact.
        shares, avg_cost = ledger.position("AAPL")
        assert shares == 6
        assert avg_cost == 100.0
        assert len(ledger.realized) == 1
        assert ledger.realized[0].ticker == "AAPL"
        assert "SQ" not in ledger.open_lots

    def test_fifo_lot_relief_is_per_account(self):
        """A SELL in one account must not close a lot bought in another — the documented
        lot-relief semantics the old single global ledger silently violated."""
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        txns = [
            (a1, _txn("VOO", TxnType.BUY, date(2024, 1, 1), qty=5, price=400.0)),
            (a2, _txn("VOO", TxnType.BUY, date(2024, 2, 1), qty=5, price=450.0)),
            # Account 2 sells its 5 — under global FIFO this would wrongly close
            # account 1's older $400 lot and report the wrong realized gain.
            (a2, _txn("VOO", TxnType.SELL, date(2024, 3, 1), qty=5, price=460.0)),
        ]
        ledger, incomplete = analytics.build_portfolio_ledger(txns)
        assert incomplete == []
        shares, avg_cost = ledger.position("VOO")
        assert shares == 5
        assert avg_cost == 400.0  # account 1's lot remains open, untouched
        assert len(ledger.realized) == 1
        assert ledger.realized[0].cost_basis == 5 * 450.0  # account 2's own basis

    def test_cash_and_income_merge_across_groups(self):
        a1, a2 = uuid.uuid4(), uuid.uuid4()
        txns = [
            (a1, _txn("", TxnType.DEPOSIT, date(2024, 1, 1), amount=1000.0)),
            (a2, _txn("", TxnType.DIVIDEND, date(2024, 2, 1), amount=50.0)),
            (a2, _txn("", TxnType.WITHDRAWAL, date(2024, 3, 1), amount=200.0)),
        ]
        ledger, incomplete = analytics.build_portfolio_ledger(txns)
        assert incomplete == []
        assert ledger.cash == 1000.0 + 50.0 - 200.0


def _seed_portfolio(session):
    tenant = models.Tenant(name="t-partial")
    session.add(tenant)
    session.flush()
    pf = models.Portfolio(tenant_id=tenant.id, name="P", base_currency="USD")
    session.add(pf)
    session.flush()
    return tenant, pf


def _add_account(session, tenant, pf, broker: str, external_id: str) -> models.Account:
    acct = models.Account(
        tenant_id=tenant.id, portfolio_id=pf.id, broker=broker,
        external_id=external_id, currency="USD",
    )
    session.add(acct)
    session.flush()
    return acct


def _add_txn(session, tenant, acct, sec, *, txn_type: str, qty: float, price: float, when: date, key: str):
    session.add(
        models.Transaction(
            tenant_id=tenant.id, account_id=acct.id, security_id=sec.id,
            txn_type=txn_type, quantity=qty, price=price, amount=qty * price,
            currency="USD", trade_date=when, source_key=key,
        )
    )


def test_emptied_snapshot_account_is_excluded_from_holdings_ledger(db_session):
    """An account from a snapshot source (SnapTrade) that holds NOTHING — activities
    on disk, zero position rows (everything sold) — must contribute nothing to current
    holdings. Before the fix it fell on the ledger side ("has no positions") and its
    partial activity history either crashed the view or fabricated holdings."""
    tenant, pf = _seed_portfolio(db_session)
    sec = models.Security(symbol="SQ", currency="USD")
    db_session.add(sec)
    db_session.flush()
    emptied = _add_account(db_session, tenant, pf, "snaptrade", "ET-1")
    # Partial history: a BUY the feed DOES reach back to… (would fabricate 10 open
    # shares if replayed into current holdings)
    _add_txn(db_session, tenant, emptied, sec, txn_type="BUY", qty=10, price=60.0, when=date(2024, 1, 2), key="b1")
    # …and a SELL larger than it (the part the feed can't explain).
    _add_txn(db_session, tenant, emptied, sec, txn_type="SELL", qty=27, price=64.0, when=date(2024, 7, 17), key="s1")
    db_session.commit()

    held = analytics.holdings(db_session, tenant.id, pf.id)
    assert held == []  # empty snapshot is authoritative: no phantom SQ position

    # And the accounts panel (the view that 500'd live) renders every account.
    infos = analytics.accounts(db_session, tenant.id, pf.id)
    assert [a.external_id for a in infos] == ["ET-1"]


def test_portfolio_views_survive_partial_history_in_one_account(db_session):
    """End-to-end DB shape of the live incident: one healthy CSV account + one
    snapshot account with unreplayable history. holdings/accounts/realized/summary
    must all return (degraded for the broken group only), not raise."""
    tenant, pf = _seed_portfolio(db_session)
    aapl = models.Security(symbol="AAPL", currency="USD")
    sq = models.Security(symbol="SQ", currency="USD")
    db_session.add_all([aapl, sq])
    db_session.flush()

    csv_acct = _add_account(db_session, tenant, pf, "csv", "CSV-1")
    _add_txn(db_session, tenant, csv_acct, aapl, txn_type="BUY", qty=10, price=100.0, when=date(2024, 1, 1), key="c1")

    etrade = _add_account(db_session, tenant, pf, "snaptrade", "ET-2")
    _add_txn(db_session, tenant, etrade, sq, txn_type="SELL", qty=27, price=64.0, when=date(2024, 7, 17), key="e1")
    db_session.commit()

    held = analytics.holdings(db_session, tenant.id, pf.id)
    assert [h.ticker for h in held] == ["AAPL"]

    infos = analytics.accounts(db_session, tenant.id, pf.id)
    assert {a.external_id for a in infos} == {"CSV-1", "ET-2"}

    # Realized view: the unreplayable SQ group is absent, nothing raises.
    closed = analytics.realized(db_session, tenant.id, pf.id)
    assert closed == []

    summary = analytics.summary(db_session, tenant.id, pf.id)
    assert summary.n_accounts == 2
    assert summary.n_holdings == 1
