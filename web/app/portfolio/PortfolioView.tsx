"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { send, useApi, writeErrorMessage, type Holding, type Portfolio } from "@/lib/api";
import { money, num, shortDate, signedMoney, tone, toneText } from "@/lib/format";
import { buttonCls, Card, CardHeader, ChangePill, Empty, ErrorBox, inputCls, Skeleton, Stat } from "@/components/ui";

export function PortfolioView() {
  const pf = useApi<Portfolio>("/api/hub/portfolio");
  const lots = useApi<{ items: Holding[] }>("/api/hub/holdings");
  const p = pf.data;
  const t = p?.totals;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Portfolio</h1>
        <p className="mt-1 text-sm text-muted">Positions valued at the latest stored quote.</p>
      </div>

      {pf.error && !p ? <ErrorBox error={pf.error} onRetry={() => pf.mutate()} /> : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {t ? (
          <>
            <Card className="px-4 py-3">
              <Stat label="Market value" value={money(t.market_value)} />
            </Card>
            <Card className="px-4 py-3">
              <Stat label="Today" value={<span className={toneText[tone(t.day_change)]}>{signedMoney(t.day_change)}</span>} sub={<ChangePill value={t.day_change_pct} />} />
            </Card>
            <Card className="px-4 py-3">
              <Stat
                label="Unrealized P&L"
                value={<span className={toneText[tone(t.unrealized_pnl)]}>{signedMoney(t.unrealized_pnl)}</span>}
                sub={<ChangePill value={t.unrealized_pnl_pct} />}
              />
            </Card>
            <Card className="px-4 py-3">
              <Stat label="Cost basis" value={money(t.cost_basis)} />
            </Card>
          </>
        ) : (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[84px] rounded-xl" />)
        )}
      </div>

      {p?.unpriced.length ? (
        <p className="rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-sm text-warn">
          No quote yet for {p.unpriced.join(", ")}; {p.unpriced.length === 1 ? "it is" : "they are"} listed but left out of the totals.
        </p>
      ) : null}

      <Card>
        <CardHeader title="Positions" sub={p ? `${p.positions.length} ${p.positions.length === 1 ? "position" : "positions"}` : undefined} />
        {!p ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : !p.positions.length ? (
          <Empty title="No positions yet">Add a lot below to start tracking a position.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted">
                  <th className="px-4 py-2 font-medium">Holding</th>
                  <th className="px-3 py-2 text-right font-medium">Shares</th>
                  <th className="px-3 py-2 text-right font-medium">Avg cost</th>
                  <th className="px-3 py-2 text-right font-medium">Price</th>
                  <th className="px-3 py-2 text-right font-medium">Value</th>
                  <th className="px-3 py-2 text-right font-medium">Today</th>
                  <th className="px-3 py-2 text-right font-medium">Unrealized</th>
                  <th className="w-40 px-4 py-2 font-medium">Weight</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {p.positions.map((pos) => (
                  <tr key={pos.ticker} className="hover:bg-surface-2/60">
                    <td className="px-4 py-2.5">
                      <Link href={`/ticker/${pos.ticker}`} className="num font-semibold hover:text-accent">
                        {pos.ticker}
                      </Link>
                      <div className="max-w-48 truncate text-xs text-muted">
                        {pos.name ?? ""}
                        {pos.lots > 1 ? ` · ${pos.lots} lots` : ""}
                      </div>
                    </td>
                    <td className="num px-3 py-2.5 text-right">{num(pos.shares, 4)}</td>
                    <td className="num px-3 py-2.5 text-right">{money(pos.avg_cost)}</td>
                    <td className="num px-3 py-2.5 text-right">{money(pos.price)}</td>
                    <td className="num px-3 py-2.5 text-right font-medium">{money(pos.market_value)}</td>
                    <td className="px-3 py-2.5 text-right">
                      <div className={`num ${toneText[tone(pos.day_change)]}`}>{signedMoney(pos.day_change)}</div>
                      <ChangePill value={pos.day_change_pct} />
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <div className={`num ${toneText[tone(pos.unrealized_pnl)]}`}>{signedMoney(pos.unrealized_pnl)}</div>
                      <ChangePill value={pos.unrealized_pnl_pct} />
                    </td>
                    <td className="px-4 py-2.5">
                      {pos.weight_pct != null ? (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                            <div className="h-full rounded-full bg-accent" style={{ width: `${pos.weight_pct}%` }} />
                          </div>
                          <span className="num w-12 text-right text-xs text-muted">{num(pos.weight_pct, 1)}%</span>
                        </div>
                      ) : (
                        <span className="text-xs text-faint">unpriced</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Lots" sub="Each purchase you record. Positions above roll these up by ticker." />
          {lots.error && !lots.data ? (
            <ErrorBox error={lots.error} onRetry={() => lots.mutate()} />
          ) : !lots.data ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : !lots.data.items.length ? (
            <Empty title="No lots recorded">Use the form to add your first one.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {lots.data.items.map((h) => (
                <LotRow key={h.id} lot={h} />
              ))}
            </ul>
          )}
        </Card>
        <AddLot />
      </div>
    </div>
  );
}

type Draft = { ticker: string; shares: string; avg_cost: string; opened_at: string; note: string };
const emptyDraft: Draft = { ticker: "", shares: "", avg_cost: "", opened_at: "", note: "" };

function toBody(d: Draft) {
  const shares = Number(d.shares);
  const avg = Number(d.avg_cost);
  if (!(shares > 0)) throw new Error("Shares must be greater than zero.");
  if (!(avg >= 0) || d.avg_cost.trim() === "") throw new Error("Average cost must be zero or more.");
  return { shares, avg_cost: avg, opened_at: d.opened_at || null, note: d.note.trim() || null };
}

function LotFields({ draft, setDraft, withTicker }: { draft: Draft; setDraft: (d: Draft) => void; withTicker?: boolean }) {
  const field = (k: keyof Draft) => ({
    value: draft[k],
    onChange: (e: { target: { value: string } }) => setDraft({ ...draft, [k]: e.target.value }),
  });
  return (
    <>
      {withTicker ? (
        <label className="flex flex-col gap-1 text-xs text-muted">
          Ticker
          <input {...field("ticker")} required placeholder="AAPL" autoCapitalize="characters" className={`${inputCls} num uppercase`} />
        </label>
      ) : null}
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Shares
          <input {...field("shares")} required type="number" step="any" min="0" inputMode="decimal" className={`${inputCls} num`} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Avg cost
          <input {...field("avg_cost")} required type="number" step="any" min="0" inputMode="decimal" className={`${inputCls} num`} />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Opened
        <input {...field("opened_at")} type="date" className={inputCls} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Note
        <input {...field("note")} maxLength={2000} placeholder="Optional" className={inputCls} />
      </label>
    </>
  );
}

function AddLot() {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await send("POST", "/api/hub/holdings", { ticker: draft.ticker.trim().toUpperCase(), ...toBody(draft) });
      setDraft(emptyDraft);
    } catch (err) {
      setError(writeErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="self-start">
      <CardHeader title="Add a lot" />
      <form onSubmit={submit} className="space-y-3 p-4">
        <LotFields draft={draft} setDraft={setDraft} withTicker />
        {error ? (
          <p role="alert" className="text-xs text-down">
            {error}
          </p>
        ) : null}
        <button type="submit" disabled={busy} className={`${buttonCls.primary} w-full`}>
          {busy ? "Adding…" : "Add lot"}
        </button>
      </form>
    </Card>
  );
}

function LotRow({ lot }: { lot: Holding }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError(writeErrorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const startEdit = () => {
    setDraft({
      ticker: lot.ticker,
      shares: String(lot.shares),
      avg_cost: String(lot.avg_cost),
      opened_at: lot.opened_at ?? "",
      note: lot.note ?? "",
    });
    setEditing(true);
    setConfirming(false);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => send("PATCH", `/api/hub/holdings/${lot.id}`, toBody(draft)))) setEditing(false);
  };

  if (editing) {
    return (
      <li className="bg-surface-2/50 px-4 py-3">
        <form onSubmit={save} className="space-y-3">
          <div className="num text-sm font-semibold">{lot.ticker}</div>
          <div className="grid gap-3 sm:grid-cols-2">
            <LotFields draft={draft} setDraft={setDraft} />
          </div>
          {error ? <p className="text-xs text-down">{error}</p> : null}
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className={buttonCls.primary}>
              {busy ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={() => setEditing(false)} className={buttonCls.secondary}>
              Cancel
            </button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <Link href={`/ticker/${lot.ticker}`} className="num w-16 font-semibold hover:text-accent">
          {lot.ticker}
        </Link>
        <span className="num text-sm">
          {num(lot.shares, 4)} @ {money(lot.avg_cost)}
        </span>
        <span className="num text-sm text-muted">{money(lot.shares * lot.avg_cost)} cost</span>
        {lot.opened_at ? <span className="text-xs text-muted">opened {shortDate(lot.opened_at)}</span> : null}
        <span className="ml-auto flex items-center gap-1">
          {confirming ? (
            <>
              <span className="text-xs text-muted">Delete this lot?</span>
              <button
                onClick={() => run(() => send("DELETE", `/api/hub/holdings/${lot.id}`))}
                disabled={busy}
                className="rounded-md bg-down px-2 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Deleting…" : "Delete"}
              </button>
              <button onClick={() => setConfirming(false)} className={buttonCls.ghost}>
                Keep
              </button>
            </>
          ) : (
            <>
              <button onClick={startEdit} className={buttonCls.ghost}>
                Edit
              </button>
              <button onClick={() => setConfirming(true)} className={`${buttonCls.ghost} hover:text-down`}>
                Delete
              </button>
            </>
          )}
        </span>
      </div>
      {lot.note ? <p className="mt-1 text-xs text-muted">{lot.note}</p> : null}
      {error ? <p className="mt-1 text-xs text-down">{error}</p> : null}
    </li>
  );
}
