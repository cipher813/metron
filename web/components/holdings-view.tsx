"use client";

// Holdings grouping switch (Holdings metrics): "By asset class" (the existing cash / bonds /
// equities / … grouping) vs "By sector → country" (the new median-banded view). A thin
// client wrapper that only owns the toggle state; both groupings are presentational.

import { useState } from "react";
import { GroupedByClassification } from "@/components/grouped-by-classification";
import { GroupedHoldings } from "@/components/grouped-holdings";
import type { Holding, ValuationMedians } from "@/lib/api";

type Mode = "asset" | "classification";

const MODES: { key: Mode; label: string }[] = [
  { key: "asset", label: "By asset class" },
  { key: "classification", label: "By sector → country" },
];

export function HoldingsView({
  holdings,
  baseCurrency,
  priced,
  medians,
  portfolioId,
}: {
  holdings: Holding[];
  baseCurrency: string;
  priced: boolean;
  medians: ValuationMedians | null;
  portfolioId?: string;
}) {
  const [mode, setMode] = useState<Mode>("asset");

  return (
    <div className="space-y-3">
      <div className="inline-flex rounded-lg border border-line p-0.5 text-xs">
        {MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => setMode(m.key)}
            className={`rounded-md px-2.5 py-1 transition ${
              mode === m.key ? "bg-surface font-medium text-ink" : "text-muted hover:text-ink"
            }`}
            aria-pressed={mode === m.key}
          >
            {m.label}
          </button>
        ))}
      </div>
      {mode === "asset" ? (
        <GroupedHoldings holdings={holdings} baseCurrency={baseCurrency} priced={priced} portfolioId={portfolioId} />
      ) : (
        <GroupedByClassification
          holdings={holdings}
          baseCurrency={baseCurrency}
          priced={priced}
          medians={medians}
          portfolioId={portfolioId}
        />
      )}
    </div>
  );
}
