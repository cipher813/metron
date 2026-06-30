"use client";

// Holdings toolbar + grouping switch. Two controls (metron-ops#114): the GROUPING — "By
// asset class" (cash / bonds / equities / …) vs "By sector → country" (median-banded) — and
// the COLUMN PRESET (which metric bands show, over the always-on position spine). A thin
// client wrapper owning just those two pieces of state; the groupings are presentational.

import { useState } from "react";
import { GroupedByClassification } from "@/components/grouped-by-classification";
import { GroupedHoldings } from "@/components/grouped-holdings";
import { ColumnPresetControl, DEFAULT_VISIBLE_GROUPS } from "@/components/holdings-column-presets";
import type { MetricGroup } from "@/components/holdings-table";
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
  const [visibleGroups, setVisibleGroups] = useState<MetricGroup[]>(DEFAULT_VISIBLE_GROUPS);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
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
        {/* Column presets only matter in the priced view (metric bands are feed-gated). */}
        {priced ? <ColumnPresetControl value={visibleGroups} onChange={setVisibleGroups} /> : null}
      </div>
      {mode === "asset" ? (
        <GroupedHoldings
          holdings={holdings}
          baseCurrency={baseCurrency}
          priced={priced}
          portfolioId={portfolioId}
          visibleMetricGroups={visibleGroups}
        />
      ) : (
        <GroupedByClassification
          holdings={holdings}
          baseCurrency={baseCurrency}
          priced={priced}
          medians={medians}
          portfolioId={portfolioId}
          visibleMetricGroups={visibleGroups}
        />
      )}
    </div>
  );
}
