// Shared "Portfolio total" bar for the Holdings groupers (metron-ops#118+). Consolidates the
// three near-identical bars the groupers each carried, and adds a `below` slot rendered
// directly under the total — the Holdings page feeds the column-band control into it so the
// column sets read as attached to the table rather than stranded in the top toolbar.

import type { ReactNode } from "react";
import type { Holding } from "@/lib/api";
import { accountingMoneyWhole, accountingPercent, moneyWhole, signClass } from "@/lib/format";

type GrandTotal = { cost: number | null; mv: number | null; unreal: number | null };

/** Whole-portfolio base-currency aggregate. A field stays null when NO holding contributed
 *  it (e.g. unpriced view → no market value), so the bar shows "—" rather than a fake 0. */
export function grandTotal(holdings: Holding[]): GrandTotal {
  let cost = 0;
  let mv = 0;
  let unreal = 0;
  let haveCost = false;
  let haveMv = false;
  let haveUnreal = false;
  for (const h of holdings) {
    if (h.cost_basis_base != null) {
      cost += h.cost_basis_base;
      haveCost = true;
    }
    if (h.market_value != null) {
      mv += h.market_value;
      haveMv = true;
    }
    if (h.unrealized_gain != null) {
      unreal += h.unrealized_gain;
      haveUnreal = true;
    }
  }
  return { cost: haveCost ? cost : null, mv: haveMv ? mv : null, unreal: haveUnreal ? unreal : null };
}

export function PortfolioTotalBar({
  holdings,
  baseCurrency,
  priced,
  below,
}: {
  holdings: Holding[];
  baseCurrency: string;
  priced: boolean;
  /** Rendered directly under the total bar (e.g. the column-band control). */
  below?: ReactNode;
}) {
  const grand = grandTotal(holdings);
  const grandPct = grand.unreal != null && grand.cost ? grand.unreal / grand.cost : null;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
        <span className="text-xs font-medium uppercase tracking-wide text-muted">Portfolio total</span>
        <div className="flex flex-wrap items-baseline gap-x-6 tabular-nums">
          <span>
            <span className="text-[10px] uppercase tracking-wide text-muted">Cost </span>
            {grand.cost != null ? moneyWhole(grand.cost, baseCurrency) : "—"}
          </span>
          {priced ? (
            <>
              <span>
                <span className="text-[10px] uppercase tracking-wide text-muted">Market </span>
                {grand.mv != null ? moneyWhole(grand.mv, baseCurrency) : "—"}
              </span>
              <span className={grand.unreal != null ? signClass(grand.unreal) : "text-muted"}>
                <span className="text-[10px] uppercase tracking-wide text-muted">Unrealized </span>
                {grand.unreal != null ? accountingMoneyWhole(grand.unreal, baseCurrency) : "—"}
                {grandPct != null ? <span className="ml-1 text-xs">{accountingPercent(grandPct)}</span> : null}
              </span>
            </>
          ) : null}
        </div>
      </div>
      {below ? <div>{below}</div> : null}
    </div>
  );
}
