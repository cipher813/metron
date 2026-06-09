"""Price-free read models — income-by-year, accounts, portfolio summary (PH2 data).

All three are fully determined by the transaction history (no prices), so they're the
backend for the free beta's Portfolio + Income pages before any licensed price feed.
"""

from __future__ import annotations

import io
import uuid

import pytest

# AAPL bought 2023, held >1yr, sold 2024 (long-term gain 500); dividends in both years,
# interest in 2023. NVDA bought + sold inside 2024 (short-term gain 100).
CSV = """date,type,symbol,quantity,price,amount,fees
2023-01-10,BUY,AAPL,10,100,1000,
2023-03-01,DIVIDEND,AAPL,,,5,
2023-06-01,INTEREST,,,,2,
2024-02-01,SELL,AAPL,10,150,1500,
2024-03-01,DIVIDEND,AAPL,,,8,
2024-05-01,BUY,NVDA,2,100,200,
2024-09-01,SELL,NVDA,2,150,300,
"""


@pytest.fixture()
def tenant():
    return str(uuid.uuid4())


def _seed(client, tenant, csv=CSV, name="Taxable"):
    pid = client.post("/portfolios", json={"name": name}, headers={"X-Tenant-Id": tenant}).json()["id"]
    r = client.post(
        f"/portfolios/{pid}/import/csv",
        files={"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")},
        headers={"X-Tenant-Id": tenant},
    )
    assert r.status_code == 200
    return pid


def _get(client, tenant, pid, path):
    return client.get(f"/portfolios/{pid}/{path}", headers={"X-Tenant-Id": tenant})


class TestIncome:
    def test_income_by_year_newest_first(self, client, tenant):
        pid = _seed(client, tenant)
        rows = _get(client, tenant, pid, "income").json()
        assert [r["year"] for r in rows] == [2024, 2023]

    def test_2024_breakdown(self, client, tenant):
        pid = _seed(client, tenant)
        y2024 = next(r for r in _get(client, tenant, pid, "income").json() if r["year"] == 2024)
        assert y2024["realized_lt"] == 500     # AAPL held >1yr
        assert y2024["realized_st"] == 100     # NVDA in-year
        assert y2024["dividends"] == 8
        assert y2024["net_capital_gains"] == 600
        assert y2024["taxable_income"] == 608

    def test_2023_breakdown(self, client, tenant):
        pid = _seed(client, tenant)
        y2023 = next(r for r in _get(client, tenant, pid, "income").json() if r["year"] == 2023)
        assert y2023["dividends"] == 5 and y2023["interest"] == 2
        assert y2023["net_capital_gains"] == 0


class TestAccounts:
    def test_lists_csv_account(self, client, tenant):
        pid = _seed(client, tenant)
        accts = _get(client, tenant, pid, "accounts").json()
        assert len(accts) == 1
        assert accts[0]["broker"] == "csv" and accts[0]["external_id"] == "CSV"

    def test_multiple_accounts_from_account_column(self, client, tenant):
        csv = "date,type,symbol,quantity,price,account\n2024-01-01,BUY,AAPL,1,100,Roth\n2024-01-01,BUY,MSFT,1,100,Taxable\n"
        pid = _seed(client, tenant, csv=csv)
        brokers = {a["external_id"] for a in _get(client, tenant, pid, "accounts").json()}
        assert brokers == {"Roth", "Taxable"}


class TestSummary:
    def test_totals(self, client, tenant):
        pid = _seed(client, tenant)
        s = _get(client, tenant, pid, "summary").json()
        assert s["n_accounts"] == 1
        assert s["n_holdings"] == 0          # AAPL + NVDA both fully sold
        assert s["total_cost_basis"] == 0
        assert s["realized_st"] == 100 and s["realized_lt"] == 500
        assert s["realized_total"] == 600
        assert s["dividends"] == 13 and s["interest"] == 2
        assert s["taxable_income"] == 615
        assert s["base_currency"] == "USD"

    def test_open_position_counts_in_holdings(self, client, tenant):
        csv = "date,type,symbol,quantity,price\n2024-01-01,BUY,AAPL,10,100\n"
        pid = _seed(client, tenant, csv=csv)
        s = _get(client, tenant, pid, "summary").json()
        assert s["n_holdings"] == 1 and s["total_cost_basis"] == 1000


def test_read_models_require_tenant_ownership(client, tenant):
    pid = _seed(client, tenant)
    other = str(uuid.uuid4())
    for path in ("income", "accounts", "summary"):
        assert _get(client, other, pid, path).status_code == 404
