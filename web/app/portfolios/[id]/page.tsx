import Link from "next/link";
import { acctParams, getAccounts, getHoldings, getIncome, getPlugins, getPortfolio, getSummary, MetronApiError, type Portfolio, type PluginNav } from "@/lib/api";
import { money, percent, quantity, signClass, signedMoney } from "@/lib/format";
import { Empty, Section, StatCard, Table } from "@/components/ui";
import { AccountPanel } from "@/components/account-panel";
import { ImportPanel } from "@/components/import-panel";
import { RefreshPrices } from "@/components/refresh-prices";
import { RenamePortfolio } from "@/components/rename-portfolio";
import { requireTenantId } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function PortfolioPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { account_id?: string | string[] };
}) {
  const { id } = params;
  const tenantId = await requireTenantId();

  // The account-panel selection (repeatable ?account_id=); empty = whole portfolio.
  const raw = searchParams.account_id;
  const accountIds = raw == null ? [] : Array.isArray(raw) ? raw : [raw];
  const scoped = accountIds.length > 0;
  // Carry the selection onto the cross-page nav links so it persists.
  const navQuery = acctParams(accountIds);

  let portfolio: Portfolio, summary, holdings, income, accounts;
  try {
    [portfolio, summary, holdings, income, accounts] = await Promise.all([
      getPortfolio(tenantId, id),
      getSummary(tenantId, id, accountIds),
      getHoldings(tenantId, id, accountIds),
      getIncome(tenantId, id, accountIds),
      getAccounts(tenantId, id),
    ]);
  } catch (e) {
    if (e instanceof MetronApiError && e.status === 404) {
      return <Empty>Portfolio not found.</Empty>;
    }
    return <Empty>Couldn&apos;t load this portfolio. Is the backend running?</Empty>;
  }

  const ccy = summary.base_currency;
  const priced = summary.market_value != null;

  // Premium nav (metron-ops). Best-effort + always empty on the public tier — a
  // failure here must never break the core portfolio view.
  let plugins: PluginNav[] = [];
  try {
    plugins = await getPlugins(tenantId);
  } catch {
    plugins = [];
  }

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <Link href="/" className="text-sm text-muted hover:text-ink">
          ← Portfolios
        </Link>
        <div className="flex gap-4">
          <Link href={`/portfolios/${id}/performance${navQuery}`} className="text-sm text-muted hover:text-ink">
            Performance →
          </Link>
          <Link href={`/portfolios/${id}/risk${navQuery}`} className="text-sm text-muted hover:text-ink">
            Risk →
          </Link>
          <Link href={`/portfolios/${id}/attribution${navQuery}`} className="text-sm text-muted hover:text-ink">
            Attribution →
          </Link>
          <Link href={`/portfolios/${id}/macro`} className="text-sm text-muted hover:text-ink">
            Macro →
          </Link>
          <Link href={`/portfolios/${id}/calendar`} className="text-sm text-muted hover:text-ink">
            Calendar →
          </Link>
          <Link href={`/portfolios/${id}/tax${navQuery}`} className="text-sm text-muted hover:text-ink">
            Tax →
          </Link>
          <Link href={`/portfolios/${id}/transactions${navQuery}`} className="text-sm text-muted hover:text-ink">
            Transactions &amp; realized →
          </Link>
          <Link href={`/portfolios/${id}/settings`} className="text-sm text-muted hover:text-ink">
            Settings →
          </Link>
          {plugins.map((p) => (
            <Link
              key={p.id}
              href={`/portfolios/${id}/${p.href}`}
              className="text-sm font-medium text-ink hover:underline"
            >
              {p.label} →
            </Link>
          ))}
        </div>
      </div>

      <div className="mt-3">
        <RenamePortfolio portfolioId={id} name={portfolio.name} />
      </div>

      <Section title="Accounts">
        <AccountPanel accounts={accounts} baseCurrency={ccy} portfolioId={id} />
        {scoped ? (
          <p className="mt-2 text-xs text-muted">
            Showing {summary.n_accounts} of {accounts.length} account{accounts.length === 1 ? "" : "s"} — totals,
            holdings, income, Risk and Attribution below reflect this selection. (Performance stays whole-portfolio.)
          </p>
        ) : null}
      </Section>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {priced ? (
          <>
            <StatCard
              label="Market value"
              value={money(summary.market_value as number, ccy)}
              hint={`cost ${money(summary.total_cost_basis, ccy)}`}
            />
            <StatCard
              label="Unrealized"
              value={signedMoney(summary.unrealized_gain as number, ccy)}
              valueClass={signClass(summary.unrealized_gain as number)}
              hint="vs cost basis"
            />
          </>
        ) : (
          <StatCard label="Cost basis" value={money(summary.total_cost_basis, ccy)} hint={`${summary.n_holdings} holdings`} />
        )}
        <StatCard
          label="Realized gains"
          value={signedMoney(summary.realized_total, ccy)}
          valueClass={signClass(summary.realized_total)}
          hint="short + long term"
        />
        <StatCard label="Income" value={money(summary.dividends + summary.interest, ccy)} hint="dividends + interest" />
        <StatCard label="Accounts" value={String(summary.n_accounts)} />
      </div>

      {summary.n_unconverted > 0 ? (
        <p className="mt-2 text-xs text-muted">
          {summary.n_unconverted} foreign holding{summary.n_unconverted === 1 ? "" : "s"} excluded from the{" "}
          {ccy} totals — no FX rate cached yet. Refresh prices to fetch it.
        </p>
      ) : null}

      <Section title="Import" note="CSV / OFX / IBKR Flex — $0, no aggregator">
        <ImportPanel portfolioId={id} />
      </Section>

      <Section title="Holdings" note={priced ? "market value from last EOD close" : "cost basis — refresh for market value"}>
        <div className="mb-3">
          <RefreshPrices portfolioId={id} />
        </div>
        {holdings.length === 0 ? (
          <Empty>No open positions.</Empty>
        ) : (
          <Table
            head={
              priced
                ? ["Ticker", "Ccy", "Quantity", "Avg cost", "Cost basis", "Last", "Market value", "Unrealized"]
                : ["Ticker", "Ccy", "Quantity", "Avg cost", "Cost basis"]
            }
          >
            {holdings.map((h) => {
              // Native fields (avg cost / cost basis / last) render in the holding's own
              // currency; market value + unrealized are converted to the base currency.
              const foreign = h.currency !== ccy;
              return (
                <tr key={h.ticker} className="border-b border-line last:border-0">
                  <td className="px-4 py-2 font-medium">{h.ticker}</td>
                  <td className="px-4 py-2 text-muted">{h.currency}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{quantity(h.quantity)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{money(h.avg_cost, h.currency)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{money(h.cost_basis, h.currency)}</td>
                  {priced ? (
                    <>
                      <td className="px-4 py-2 text-right tabular-nums text-muted">
                        {h.last_price != null ? money(h.last_price, h.currency) : "—"}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {h.market_value != null ? (
                          money(h.market_value, ccy)
                        ) : foreign && h.market_value_local != null ? (
                          <span className="text-muted" title={`No ${ccy} FX rate cached`}>
                            {money(h.market_value_local, h.currency)}*
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className={`px-4 py-2 text-right tabular-nums ${signClass(h.unrealized_gain ?? 0)}`}>
                        {h.unrealized_gain != null ? (
                          <>
                            {signedMoney(h.unrealized_gain, ccy)}
                            {h.unrealized_pct != null ? (
                              <span className="ml-1 text-xs">({percent(h.unrealized_pct)})</span>
                            ) : null}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                    </>
                  ) : null}
                </tr>
              );
            })}
          </Table>
        )}
      </Section>

      <Section title="Income by year">
        {income.length === 0 ? (
          <Empty>No realized income yet.</Empty>
        ) : (
          <Table head={["Year", "Short-term", "Long-term", "Dividends", "Interest", "Taxable income"]}>
            {income.map((y) => (
              <tr key={y.year} className="border-b border-line last:border-0">
                <td className="px-4 py-2 font-medium">{y.year}</td>
                <td className={`px-4 py-2 text-right tabular-nums ${signClass(y.realized_st)}`}>
                  {signedMoney(y.realized_st, ccy)}
                </td>
                <td className={`px-4 py-2 text-right tabular-nums ${signClass(y.realized_lt)}`}>
                  {signedMoney(y.realized_lt, ccy)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">{money(y.dividends, ccy)}</td>
                <td className="px-4 py-2 text-right tabular-nums">{money(y.interest, ccy)}</td>
                <td className="px-4 py-2 text-right font-medium tabular-nums">{money(y.taxable_income, ccy)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>
    </div>
  );
}
