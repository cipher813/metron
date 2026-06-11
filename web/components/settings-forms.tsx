"use client";

// Settings editors (client) — base currency, per-account tags, and investor
// preferences. Each saves through a Server Action (tenant header stays server-side)
// and the action revalidates so the change paints across the portfolio views.

import { useState, useTransition } from "react";
import {
  savePreferencesAction,
  updateAccountTagsAction,
  updateBaseCurrencyAction,
} from "@/app/portfolios/[id]/actions";
import type { Account, Preferences } from "@/lib/api";

const CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "HKD", "JPY", "SGD", "CHF"];

function Status({ msg }: { msg: { ok: boolean; text: string } | null }) {
  if (!msg) return null;
  return <span className={`text-sm ${msg.ok ? "text-positive" : "text-negative"}`}>{msg.text}</span>;
}

export function BaseCurrencyForm({ portfolioId, current }: { portfolioId: string; current: string }) {
  const [value, setValue] = useState(current);
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function save() {
    setMsg(null);
    start(async () => {
      const r = await updateBaseCurrencyAction(portfolioId, value);
      setMsg({ ok: r.ok, text: r.message });
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        className="rounded border border-line px-2 py-1 text-sm"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      >
        {(CURRENCIES.includes(current) ? CURRENCIES : [current, ...CURRENCIES]).map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={pending || value === current}
        onClick={save}
        className="rounded bg-ink px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
      >
        {pending ? "Saving…" : "Save"}
      </button>
      <Status msg={msg} />
      <span className="text-xs text-muted">All portfolio totals report in this currency.</span>
    </div>
  );
}

type Taxable = "auto" | "taxable" | "advantaged";

export function AccountTagRow({ portfolioId, account }: { portfolioId: string; account: Account }) {
  const [institution, setInstitution] = useState(account.institution ?? "");
  const [accountType, setAccountType] = useState(account.account_type ?? "");
  // null = auto (derive). We start from the *current* derived state but tag edits set
  // an explicit override; "Auto" reverts to null.
  const [taxable, setTaxable] = useState<Taxable>(account.taxable ? "taxable" : "advantaged");
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function save() {
    setMsg(null);
    const taxable_override = taxable === "auto" ? null : taxable === "taxable";
    start(async () => {
      const r = await updateAccountTagsAction(portfolioId, account.account_id, {
        institution: institution.trim() || null,
        account_type: accountType.trim() || null,
        taxable_override,
      });
      setMsg({ ok: r.ok, text: r.message });
    });
  }

  return (
    <tr className="border-b border-line last:border-0 align-top">
      <td className="px-4 py-2 font-medium">{account.name || account.external_id}</td>
      <td className="px-4 py-2">
        <input
          className="w-36 rounded border border-line px-2 py-1 text-sm"
          value={institution}
          placeholder="e.g. Fidelity"
          onChange={(e) => setInstitution(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <input
          className="w-36 rounded border border-line px-2 py-1 text-sm"
          value={accountType}
          placeholder="e.g. Roth IRA"
          onChange={(e) => setAccountType(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <select
          className="rounded border border-line px-2 py-1 text-sm"
          value={taxable}
          onChange={(e) => setTaxable(e.target.value as Taxable)}
        >
          <option value="auto">Auto</option>
          <option value="taxable">Taxable</option>
          <option value="advantaged">Tax-advantaged</option>
        </select>
      </td>
      <td className="px-4 py-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={pending}
            onClick={save}
            className="rounded bg-ink px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "Saving…" : "Save"}
          </button>
          <Status msg={msg} />
        </div>
      </td>
    </tr>
  );
}

export function PreferencesForm({ portfolioId, current }: { portfolioId: string; current: Preferences }) {
  const [risk, setRisk] = useState(current.risk_tolerance ?? "");
  const [objective, setObjective] = useState(current.objective ?? "");
  const [notes, setNotes] = useState(current.notes ?? "");
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function save() {
    setMsg(null);
    start(async () => {
      const r = await savePreferencesAction(portfolioId, {
        risk_tolerance: risk || null,
        objective: objective || null,
        notes: notes.trim() || null,
      });
      setMsg({ ok: r.ok, text: r.message });
    });
  }

  return (
    <div className="max-w-xl space-y-3">
      <label className="block text-sm">
        <span className="text-muted">Risk tolerance</span>
        <select
          className="mt-1 block w-full rounded border border-line px-2 py-1"
          value={risk}
          onChange={(e) => setRisk(e.target.value)}
        >
          <option value="">—</option>
          <option value="conservative">Conservative</option>
          <option value="moderate">Moderate</option>
          <option value="aggressive">Aggressive</option>
        </select>
      </label>
      <label className="block text-sm">
        <span className="text-muted">Objective</span>
        <select
          className="mt-1 block w-full rounded border border-line px-2 py-1"
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
        >
          <option value="">—</option>
          <option value="income">Income</option>
          <option value="growth">Growth</option>
          <option value="balanced">Balanced</option>
        </select>
      </label>
      <label className="block text-sm">
        <span className="text-muted">Notes</span>
        <textarea
          className="mt-1 block w-full rounded border border-line px-2 py-1"
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={save}
          className="rounded bg-ink px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "Saving…" : "Save preferences"}
        </button>
        <Status msg={msg} />
      </div>
    </div>
  );
}
