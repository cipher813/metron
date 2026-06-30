"use client";

// Column-preset control for the Holdings table (metron-ops#114). The table carries ~35
// analytical columns across 6 bands; showing them all at once is the clutter. SOTA pattern:
// a frozen spine (the position columns, always shown) + a swappable analytical block chosen
// by a preset. "Score" is the always-on headline (the at-a-glance attractiveness), so every
// preset includes it; the preset picks which band(s) sit beside it. "Customize" drops to
// band-level checkboxes for a bespoke set (→ the "Custom" state).

import { METRIC_GROUP_ORDER, type MetricGroup } from "@/components/holdings-table";

export type PresetKey = "overview" | "valuation" | "fundamentals" | "technicals" | "consensus" | "all";

export const COLUMN_PRESETS: { key: PresetKey; label: string; groups: MetricGroup[] }[] = [
  { key: "overview", label: "Overview", groups: ["Score"] },
  { key: "valuation", label: "Valuation", groups: ["Score", "Valuation"] },
  { key: "fundamentals", label: "Fundamentals", groups: ["Score", "Fundamentals", "Balance Sheet"] },
  { key: "technicals", label: "Technicals", groups: ["Score", "Technicals"] },
  { key: "consensus", label: "Consensus", groups: ["Score", "Consensus"] },
  { key: "all", label: "All", groups: [...METRIC_GROUP_ORDER] },
];

/** The lean default — just the headline Score band beside the position spine. */
export const DEFAULT_VISIBLE_GROUPS: MetricGroup[] = COLUMN_PRESETS[0].groups;

// Score is always on (the headline), so it isn't an individually-toggleable band.
const CUSTOMIZABLE_BANDS: MetricGroup[] = METRIC_GROUP_ORDER.filter((g) => g !== "Score");

function sameBands(a: MetricGroup[], b: MetricGroup[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  return b.every((g) => s.has(g));
}

const SEG_BTN = (active: boolean) =>
  `rounded-md px-2.5 py-1 transition ${active ? "bg-surface font-medium text-ink" : "text-muted hover:text-ink"}`;

export function ColumnPresetControl({
  value,
  onChange,
}: {
  value: MetricGroup[];
  onChange: (groups: MetricGroup[]) => void;
}) {
  const activeKey: PresetKey | "custom" =
    COLUMN_PRESETS.find((p) => sameBands(p.groups, value))?.key ?? "custom";

  // Always emit in canonical order with Score pinned on, so downstream rendering + the
  // active-preset match are order-insensitive.
  const emit = (groups: MetricGroup[]) => {
    const withScore = groups.includes("Score") ? groups : [...groups, "Score" as MetricGroup];
    onChange(METRIC_GROUP_ORDER.filter((g) => withScore.includes(g)));
  };

  const toggleBand = (g: MetricGroup, on: boolean) =>
    emit(on ? [...value, g] : value.filter((x) => x !== g));

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10px] uppercase tracking-wide text-muted">Columns</span>
      <div className="inline-flex rounded-lg border border-line p-0.5 text-xs">
        {COLUMN_PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => emit(p.groups)}
            className={SEG_BTN(activeKey === p.key)}
            aria-pressed={activeKey === p.key}
          >
            {p.label}
          </button>
        ))}
      </div>
      {/* Native <details> disclosure — no click-outside wiring, accessible by default. */}
      <details className="relative text-xs">
        <summary
          className={`cursor-pointer list-none rounded-md border border-line px-2.5 py-1 ${
            activeKey === "custom" ? "bg-surface font-medium text-ink" : "text-muted hover:text-ink"
          }`}
        >
          Customize{activeKey === "custom" ? " ·" : ""}
        </summary>
        <div className="absolute right-0 z-30 mt-1 w-44 rounded-lg border border-line bg-paper p-2 shadow-lg">
          <p className="mb-1 px-1 text-[10px] uppercase tracking-wide text-muted">Metric bands</p>
          <label className="flex items-center gap-2 px-1 py-0.5 text-muted" title="Always shown — the headline score">
            <input type="checkbox" checked readOnly disabled /> Score
          </label>
          {CUSTOMIZABLE_BANDS.map((g) => (
            <label key={g} className="flex cursor-pointer items-center gap-2 px-1 py-0.5 hover:text-ink">
              <input
                type="checkbox"
                checked={value.includes(g)}
                onChange={(e) => toggleBand(g, e.target.checked)}
              />
              {g}
            </label>
          ))}
        </div>
      </details>
    </div>
  );
}
