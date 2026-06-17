"""Per-account Performance for snapshot-sourced accounts (metron-ops#9).

Per-account NAV can't be reconstructed (snapshot-sourced brokers report only current
positions), so it accrues forward via AccountNavSnapshot. The performance endpoint, given
an account selection, returns that subset's series: a day's NAV/flow = the SUM of the
selected accounts' rows, computed only over dates where every account in the cohort has
data (so a late-starting account never reads as a spurious gain)."""

from __future__ import annotations

import io
import uuid
from datetime import date

import pytest

CSV = (
    "date,type,symbol,quantity,price,amount,account\n"
    "2024-01-02,BUY,AAPL,10,100,1000,Brokerage\n"
    "2024-01-02,BUY,MSFT,10,200,2000,IRA\n"
)


@pytest.fixture()
def tenant():
    return str(uuid.uuid4())


def _hdr(tenant):
    return {"X-Tenant-Id": tenant}


def _seed(client, tenant):
    pid = client.post("/portfolios", json={"name": "P"}, headers=_hdr(tenant)).json()["id"]
    r = client.post(
        f"/portfolios/{pid}/import/csv",
        files={"file": ("t.csv", io.BytesIO(CSV.encode()), "text/csv")},
        headers=_hdr(tenant),
    )
    assert r.status_code == 200
    return pid


def _accounts(client, tenant, pid) -> dict[str, str]:
    rows = client.get(f"/portfolios/{pid}/accounts", headers=_hdr(tenant)).json()
    return {a["name"]: a["account_id"] for a in rows}


def _acct_snap(session, tenant, pid, account_id, when, *, nav, external_flow=0.0, spy_close=None):
    from api.db import models

    session.add(
        models.AccountNavSnapshot(
            tenant_id=uuid.UUID(tenant),
            portfolio_id=uuid.UUID(pid),
            account_id=uuid.UUID(account_id),
            snap_date=when,
            nav=nav,
            cost_basis=1000.0,
            external_flow=external_flow,
            spy_close=spy_close,
        )
    )
    session.commit()


def test_single_account_series_is_that_account(client, db_session, tenant):
    pid = _seed(client, tenant)
    acct = _accounts(client, tenant, pid)
    _acct_snap(db_session, tenant, pid, acct["Brokerage"], date(2024, 1, 1), nav=1000.0)
    _acct_snap(db_session, tenant, pid, acct["Brokerage"], date(2024, 1, 31), nav=1100.0)
    # An IRA snapshot the same days must NOT leak into the Brokerage-scoped series.
    _acct_snap(db_session, tenant, pid, acct["IRA"], date(2024, 1, 1), nav=9999.0)
    _acct_snap(db_session, tenant, pid, acct["IRA"], date(2024, 1, 31), nav=9999.0)

    p = client.get(
        f"/portfolios/{pid}/performance?account_id={acct['Brokerage']}", headers=_hdr(tenant)
    ).json()
    assert p["n_snapshots"] == 2
    assert p["latest_nav"] == pytest.approx(1100.0)
    assert p["twr"] == pytest.approx(0.10)  # 1100/1000 − 1


def test_multi_account_selection_sums_the_subset(client, db_session, tenant):
    pid = _seed(client, tenant)
    acct = _accounts(client, tenant, pid)
    for d, b, i in [(date(2024, 1, 1), 1000.0, 2000.0), (date(2024, 1, 31), 1100.0, 2100.0)]:
        _acct_snap(db_session, tenant, pid, acct["Brokerage"], d, nav=b)
        _acct_snap(db_session, tenant, pid, acct["IRA"], d, nav=i)
    ids = f"account_id={acct['Brokerage']}&account_id={acct['IRA']}"
    p = client.get(f"/portfolios/{pid}/performance?{ids}", headers=_hdr(tenant)).json()
    assert p["n_snapshots"] == 2
    assert p["latest_nav"] == pytest.approx(3200.0)  # 1100 + 2100
    assert p["twr"] == pytest.approx(3200.0 / 3000.0 - 1)  # 3000 → 3200


def test_late_starting_account_trims_the_ragged_start(client, db_session, tenant):
    """Brokerage records from day 1; the IRA only joins on day 2. The subset series must
    start on day 2 (when both have data) — never count the IRA's arrival as a gain."""
    pid = _seed(client, tenant)
    acct = _accounts(client, tenant, pid)
    _acct_snap(db_session, tenant, pid, acct["Brokerage"], date(2024, 1, 1), nav=1000.0)
    _acct_snap(db_session, tenant, pid, acct["Brokerage"], date(2024, 1, 15), nav=1050.0)
    _acct_snap(db_session, tenant, pid, acct["Brokerage"], date(2024, 1, 31), nav=1100.0)
    _acct_snap(db_session, tenant, pid, acct["IRA"], date(2024, 1, 15), nav=2000.0)
    _acct_snap(db_session, tenant, pid, acct["IRA"], date(2024, 1, 31), nav=2100.0)
    ids = f"account_id={acct['Brokerage']}&account_id={acct['IRA']}"
    p = client.get(f"/portfolios/{pid}/performance?{ids}", headers=_hdr(tenant)).json()
    # Only Jan-15 and Jan-31 qualify (both present) — Jan-1 (Brokerage-only) is dropped.
    assert p["n_snapshots"] == 2
    assert p["first_date"] == "2024-01-15"
    assert p["latest_nav"] == pytest.approx(3200.0)  # 1100 + 2100


def test_unscoped_uses_portfolio_snapshots(client, db_session, tenant):
    """No selection → the whole-portfolio NavSnapshot series, independent of the
    per-account rows (which on their own would sum differently)."""
    from api.db import models

    pid = _seed(client, tenant)
    for d, nav in [(date(2024, 1, 1), 5000.0), (date(2024, 1, 31), 5500.0)]:
        db_session.add(
            models.NavSnapshot(
                tenant_id=uuid.UUID(tenant), portfolio_id=uuid.UUID(pid), snap_date=d,
                nav=nav, cost_basis=4000.0, external_flow=0.0,
            )
        )
    db_session.commit()
    p = client.get(f"/portfolios/{pid}/performance", headers=_hdr(tenant)).json()
    assert p["latest_nav"] == pytest.approx(5500.0)
    assert p["twr"] == pytest.approx(0.10)
