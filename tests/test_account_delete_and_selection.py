"""Account deletion (+ persistent exclusion) and the saved accounts-panel selection.

Delete must remove the account AND its data, and record a ``broker:external_id``
exclusion key on the portfolio's preferences — enforced at the ``persist_snapshot``
chokepoint so no later sync/re-import resurrects the account (the live motivation:
a SnapTrade connection carries sibling accounts the user doesn't track). Restore
drops the key, after which a re-import recreates the account.

The saved selection backs the panel's sticky checkboxes: PUT validates ownership,
GET filters out ids whose accounts have since been deleted.
"""

from __future__ import annotations

import io
import uuid

import pytest

CSV = """date,type,symbol,quantity,price,amount,account
2024-01-01,BUY,AAPL,10,100,1000,Keep
2024-01-01,BUY,MSFT,5,200,1000,Drop
"""


@pytest.fixture()
def tenant():
    return str(uuid.uuid4())


def _hdr(tenant):
    return {"X-Tenant-Id": tenant}


def _seed(client, tenant, csv=CSV):
    pid = client.post("/portfolios", json={"name": "P"}, headers=_hdr(tenant)).json()["id"]
    r = client.post(
        f"/portfolios/{pid}/import/csv",
        files={"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")},
        headers=_hdr(tenant),
    )
    assert r.status_code == 200
    return pid


def _accounts(client, tenant, pid):
    return client.get(f"/portfolios/{pid}/accounts", headers=_hdr(tenant)).json()


def _acct_id(client, tenant, pid, external_id):
    return next(a["account_id"] for a in _accounts(client, tenant, pid) if a["external_id"] == external_id)


def _reimport(client, tenant, pid, csv=CSV):
    r = client.post(
        f"/portfolios/{pid}/import/csv",
        files={"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")},
        headers=_hdr(tenant),
    )
    assert r.status_code == 200
    return r.json()


class TestDeleteAccount:
    def test_delete_removes_account_and_data(self, client, tenant):
        pid = _seed(client, tenant)
        drop = _acct_id(client, tenant, pid, "Drop")
        r = client.delete(f"/portfolios/{pid}/accounts/{drop}", headers=_hdr(tenant))
        assert r.status_code == 200
        assert r.json()["excluded_key"] == "csv:Drop"
        # Account gone from the panel; its holdings gone from the portfolio.
        assert {a["external_id"] for a in _accounts(client, tenant, pid)} == {"Keep"}
        held = client.get(f"/portfolios/{pid}/holdings", headers=_hdr(tenant)).json()
        assert [h["ticker"] for h in held] == ["AAPL"]
        # And its transactions are gone too (not orphaned).
        txns = client.get(f"/portfolios/{pid}/transactions", headers=_hdr(tenant)).json()
        assert {t["ticker"] for t in txns} == {"AAPL"}

    def test_reimport_skips_deleted_account(self, client, tenant):
        """The reason exclusion exists: without it, the very next sync/re-import
        silently resurrects the deleted account."""
        pid = _seed(client, tenant)
        drop = _acct_id(client, tenant, pid, "Drop")
        client.delete(f"/portfolios/{pid}/accounts/{drop}", headers=_hdr(tenant))
        result = _reimport(client, tenant, pid)
        assert result["accounts_created"] == 0
        assert {a["external_id"] for a in _accounts(client, tenant, pid)} == {"Keep"}

    def test_restore_then_reimport_recreates(self, client, tenant):
        pid = _seed(client, tenant)
        drop = _acct_id(client, tenant, pid, "Drop")
        client.delete(f"/portfolios/{pid}/accounts/{drop}", headers=_hdr(tenant))
        excluded = client.get(f"/portfolios/{pid}/accounts/excluded", headers=_hdr(tenant)).json()["excluded"]
        assert excluded == [{"key": "csv:Drop", "broker": "csv", "external_id": "Drop"}]
        r = client.post(
            f"/portfolios/{pid}/accounts/excluded/restore", json={"key": "csv:Drop"}, headers=_hdr(tenant)
        )
        assert r.status_code == 200
        assert r.json()["excluded"] == []
        _reimport(client, tenant, pid)
        assert {a["external_id"] for a in _accounts(client, tenant, pid)} == {"Keep", "Drop"}

    def test_restore_unknown_key_404(self, client, tenant):
        pid = _seed(client, tenant)
        r = client.post(
            f"/portfolios/{pid}/accounts/excluded/restore", json={"key": "csv:Nope"}, headers=_hdr(tenant)
        )
        assert r.status_code == 404

    def test_delete_foreign_account_404(self, client, tenant):
        pid = _seed(client, tenant)
        other_tenant = str(uuid.uuid4())
        other_pid = _seed(client, other_tenant)
        foreign = _acct_id(client, other_tenant, other_pid, "Keep")
        r = client.delete(f"/portfolios/{pid}/accounts/{foreign}", headers=_hdr(tenant))
        assert r.status_code == 404


class TestAccountSelection:
    def test_selection_roundtrip(self, client, tenant):
        pid = _seed(client, tenant)
        keep = _acct_id(client, tenant, pid, "Keep")
        r = client.put(
            f"/portfolios/{pid}/accounts/selection", json={"account_ids": [keep]}, headers=_hdr(tenant)
        )
        assert r.status_code == 200
        got = client.get(f"/portfolios/{pid}/accounts/selection", headers=_hdr(tenant)).json()
        assert got["account_ids"] == [keep]

    def test_empty_selection_clears(self, client, tenant):
        pid = _seed(client, tenant)
        keep = _acct_id(client, tenant, pid, "Keep")
        client.put(f"/portfolios/{pid}/accounts/selection", json={"account_ids": [keep]}, headers=_hdr(tenant))
        client.put(f"/portfolios/{pid}/accounts/selection", json={"account_ids": []}, headers=_hdr(tenant))
        got = client.get(f"/portfolios/{pid}/accounts/selection", headers=_hdr(tenant)).json()
        assert got["account_ids"] == []

    def test_foreign_id_404(self, client, tenant):
        pid = _seed(client, tenant)
        r = client.put(
            f"/portfolios/{pid}/accounts/selection",
            json={"account_ids": [str(uuid.uuid4())]},
            headers=_hdr(tenant),
        )
        assert r.status_code == 404

    def test_delete_prunes_saved_selection(self, client, tenant):
        """A deleted account must drop out of the saved filter — both eagerly (on
        delete) and defensively (GET filters dead ids) — so pages applying the saved
        selection never scope to a gone account and 404."""
        pid = _seed(client, tenant)
        keep = _acct_id(client, tenant, pid, "Keep")
        drop = _acct_id(client, tenant, pid, "Drop")
        client.put(
            f"/portfolios/{pid}/accounts/selection", json={"account_ids": [keep, drop]}, headers=_hdr(tenant)
        )
        client.delete(f"/portfolios/{pid}/accounts/{drop}", headers=_hdr(tenant))
        got = client.get(f"/portfolios/{pid}/accounts/selection", headers=_hdr(tenant)).json()
        assert got["account_ids"] == [keep]
