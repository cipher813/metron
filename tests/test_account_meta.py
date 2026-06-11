"""Account taxable classification — auto-derive from connector metadata, manual override."""

from __future__ import annotations

from api.db import models
from api.services.account_meta import is_taxable


def _acct(**kw) -> models.Account:
    return models.Account(broker="ibkr_flex", external_id="U1", **kw)


class TestIsTaxable:
    def test_default_taxable_when_unknown(self):
        assert is_taxable(_acct()) is True

    def test_tax_treatment_drives_it(self):
        assert is_taxable(_acct(tax_treatment="tax_deferred")) is False
        assert is_taxable(_acct(tax_treatment="tax_exempt")) is False
        assert is_taxable(_acct(tax_treatment="taxable")) is True

    def test_account_type_keywords(self):
        assert is_taxable(_acct(account_type="Roth IRA")) is False
        assert is_taxable(_acct(account_type="Traditional IRA")) is False
        assert is_taxable(_acct(account_type="401(k)")) is False
        assert is_taxable(_acct(account_type="HSA")) is False
        assert is_taxable(_acct(account_type="Individual Brokerage")) is True

    def test_name_keywords(self):
        assert is_taxable(_acct(name="My Roth")) is False
        assert is_taxable(_acct(name="Joint Taxable")) is True

    def test_override_wins(self):
        # Override beats every inference, in both directions.
        assert is_taxable(_acct(account_type="Roth IRA", taxable_override=True)) is True
        assert is_taxable(_acct(tax_treatment="taxable", taxable_override=False)) is False
