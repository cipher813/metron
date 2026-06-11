"""Account classification — is a connected account *taxable*?

The Tax lens (unrealized P&L, harvestable losses, taxable income) is meaningful only
for taxable accounts: gains inside an IRA / 401(k) / Roth / HSA are never realized for
tax, so folding them into a harvestable-loss or taxable-income figure is misleading.

Classification is **auto-derived from the connector's metadata, with a manual
override**: a Settings-set ``Account.taxable_override`` wins; otherwise we infer from
``tax_treatment`` (the FDX-style tag the connector carries) and, failing that, from
keywords in ``account_type`` / ``name``. Default when nothing is known: **taxable**
(the conservative choice — better to show a lot than to silently hide it).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import models

# tax_treatment values that mean "not taxable" (FDX-style; connector-supplied).
_NON_TAXABLE_TREATMENTS = {"tax_deferred", "tax_exempt", "tax-deferred", "tax-exempt", "retirement"}

# account_type / name keywords that imply a tax-advantaged wrapper. Matched
# case-insensitively as whole-ish tokens against the combined type+name string.
_NON_TAXABLE_KEYWORDS = (
    "ira", "roth", "401k", "401(k)", "403b", "403(b)", "457", "hsa", "529",
    "rrsp", "tfsa", "sep", "simple ira", "pension", "annuity", "retirement",
)


def is_taxable(account: models.Account) -> bool:
    """Whether ``account`` is a taxable brokerage account.

    Precedence: explicit ``taxable_override`` → ``tax_treatment`` → keyword inference on
    ``account_type``/``name`` → default True."""
    if account.taxable_override is not None:
        return bool(account.taxable_override)
    treatment = (account.tax_treatment or "").strip().lower()
    if treatment in _NON_TAXABLE_TREATMENTS:
        return False
    if treatment == "taxable":
        return True
    haystack = f"{account.account_type or ''} {account.name or ''}".lower()
    if any(kw in haystack for kw in _NON_TAXABLE_KEYWORDS):
        return False
    return True


def taxable_account_ids(session: Session, tenant_id: uuid.UUID, portfolio_id: uuid.UUID) -> set[uuid.UUID]:
    """The ids of a portfolio's taxable accounts (per ``is_taxable``)."""
    rows = session.scalars(
        select(models.Account).where(
            models.Account.tenant_id == tenant_id, models.Account.portfolio_id == portfolio_id
        )
    ).all()
    return {a.id for a in rows if is_taxable(a)}
