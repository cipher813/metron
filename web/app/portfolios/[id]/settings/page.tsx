import Link from "next/link";
import { getAccounts, getPortfolio, getPreferences, MetronApiError, type Preferences } from "@/lib/api";
import { Empty, Section, Table } from "@/components/ui";
import { AccountTagRow, BaseCurrencyForm, PreferencesForm } from "@/components/settings-forms";
import { requireTenantId } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function SettingsPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const tenantId = await requireTenantId();

  let portfolio, accounts, preferences: Preferences;
  try {
    [portfolio, accounts, preferences] = await Promise.all([
      getPortfolio(tenantId, id),
      getAccounts(tenantId, id),
      getPreferences(tenantId, id),
    ]);
  } catch (e) {
    if (e instanceof MetronApiError && e.status === 404) {
      return <Empty>Portfolio not found.</Empty>;
    }
    return <Empty>Couldn&apos;t load settings. Is the backend running?</Empty>;
  }

  return (
    <div>
      <Link href={`/portfolios/${id}`} className="text-sm text-muted hover:text-ink">
        ← Portfolio
      </Link>

      <h1 className="mt-3 text-lg font-semibold">Settings</h1>
      <p className="text-sm text-muted">Reporting currency, account tags, and investor preferences for this portfolio.</p>

      <Section title="Base currency" note="reporting currency for all totals">
        <BaseCurrencyForm portfolioId={id} current={portfolio.base_currency} />
      </Section>

      <Section title="Accounts" note="set a nickname, institution, and tax treatment (Auto derives from the broker)">
        {accounts.length === 0 ? (
          <Empty>No connected accounts yet.</Empty>
        ) : (
          <Table head={["Account", "Nickname", "Institution", "Account type", "Tax treatment", "Save"]}>
            {accounts.map((a) => (
              <AccountTagRow key={a.account_id} portfolioId={id} account={a} />
            ))}
          </Table>
        )}
      </Section>

      <Section title="Investor preferences">
        <PreferencesForm portfolioId={id} current={preferences} />
      </Section>
    </div>
  );
}
