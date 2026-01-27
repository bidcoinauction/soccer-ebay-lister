"use client";

import React, { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { Card, fetchInventory, buildEbayDescription, buildEbayTitle } from "@/lib/inventory";

function uniq(values: string[]) {
  return Array.from(new Set(values.filter((v) => v && v.trim().length > 0))).sort((a, b) =>
    a.localeCompare(b)
  );
}

function cn(...s: Array<string | false | undefined | null>) {
  return s.filter(Boolean).join(" ");
}

export default function Page() {
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>("");

  // Sidebar state
  const [q, setQ] = useState("");
  const [setFilter, setSetFilter] = useState<string>("ALL");
  const [teamFilter, setTeamFilter] = useState<string>("ALL");
  const [leagueFilter, setLeagueFilter] = useState<string>("ALL");
  const [autoOnly, setAutoOnly] = useState(false);
  const [numberedOnly, setNumberedOnly] = useState(false);

  // Modal
  const [selected, setSelected] = useState<Card | null>(null);
  const [toast, setToast] = useState<string>("");

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const inv = await fetchInventory();
        setCards(inv);
      } catch (e: any) {
        setErr(e?.message || "Failed to load inventory");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const sets = useMemo(() => uniq(cards.map((c) => c.cardSet)), [cards]);
  const teams = useMemo(() => uniq(cards.map((c) => c.team)), [cards]);
  const leagues = useMemo(() => uniq(cards.map((c) => c.league)), [cards]);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return cards.filter((c) => {
      if (setFilter !== "ALL" && c.cardSet !== setFilter) return false;
      if (teamFilter !== "ALL" && c.team !== teamFilter) return false;
      if (leagueFilter !== "ALL" && c.league !== leagueFilter) return false;

      if (autoOnly && !c.isAuto) return false;
      if (numberedOnly && !c.serial) return false;

      if (!qq) return true;
      const hay = `${c.playerName} ${c.team} ${c.league} ${c.cardSet} ${c.features} ${c.cardNumber}`.toLowerCase();
      return hay.includes(qq);
    });
  }, [cards, q, setFilter, teamFilter, leagueFilter, autoOnly, numberedOnly]);

  function copy(text: string, msg: string) {
    navigator.clipboard.writeText(text).then(() => {
      setToast(msg);
      setTimeout(() => setToast(""), 1500);
    });
  }

  return (
    <div className="min-h-screen bg-[#0b1220] text-slate-100">
      <div className="mx-auto max-w-[1400px] px-4 py-5">
        {/* Top bar */}
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-bold">⚽ Soccer eBay Lister</h1>
            <p className="mt-1 text-sm text-slate-300">
              Showcase + filter your inventory and copy clean eBay listing text.{" "}
              <span className="text-slate-400">({filtered.length} shown / {cards.length} total)</span>
            </p>
          </div>

          <div className="flex gap-2">
            <a
              href="/data/inventory.tsv"
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900"
            >
              Download TSV
            </a>
            <a
              href="/data/ebay_bulk_out.csv"
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900"
            >
              Download eBay CSV
            </a>
          </div>
        </div>

        {/* Layout */}
        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-[320px_1fr]">
          {/* Sidebar */}
          <aside className="rounded-2xl border border-slate-800 bg-[#020617]/80 p-4">
            <div className="text-sm font-semibold text-slate-200">Search</div>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Player, team, set..."
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
            />

            <div className="mt-4 grid gap-3">
              <FilterSelect label="Set" value={setFilter} onChange={setSetFilter} options={sets} />
              <FilterSelect label="Team" value={teamFilter} onChange={setTeamFilter} options={teams} />
              <FilterSelect label="League" value={leagueFilter} onChange={setLeagueFilter} options={leagues} />
            </div>

            <div className="mt-4 grid gap-2">
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input type="checkbox" checked={autoOnly} onChange={(e) => setAutoOnly(e.target.checked)} />
                Auto only
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={numberedOnly}
                  onChange={(e) => setNumberedOnly(e.target.checked)}
                />
                Numbered only (/xx)
              </label>
            </div>

            <div className="mt-4">
              <button
                onClick={() => {
                  setQ("");
                  setSetFilter("ALL");
                  setTeamFilter("ALL");
                  setLeagueFilter("ALL");
                  setAutoOnly(false);
                  setNumberedOnly(false);
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900"
              >
                Clear filters
              </button>
            </div>

            <div className="mt-6 text-xs text-slate-400">
              Tip: click a card to open details, copy title/description, and verify fields.
            </div>
          </aside>

          {/* Main */}
          <main className="rounded-2xl border border-slate-800 bg-[#020617]/40 p-4">
            {loading ? (
              <div className="text-sm text-slate-300">Loading inventory…</div>
            ) : err ? (
              <div className="text-sm text-red-300">
                {err}
                <div className="mt-2 text-xs text-slate-400">
                  Make sure <code>/public/data/inventory.tsv</code> exists in the repo and deployed.
                </div>
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-sm text-slate-300">No cards match your filters.</div>
            ) : (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {filtered.map((c, i) => (
                  <CardTile key={`${c.playerName}-${c.cardNumber}-${i}`} c={c} onClick={() => setSelected(c)} />
                ))}
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Modal drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/60 p-3">
          <div className="w-full max-w-3xl rounded-2xl border border-slate-700 bg-[#020617] shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 p-4">
              <div>
                <div className="text-sm text-slate-400">Selected</div>
                <div className="text-lg font-semibold">{selected.playerName || "—"}</div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900"
              >
                Close
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-[280px_1fr]">
              <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                <div className="relative aspect-square w-full">
                  {selected.imageUrl ? (
                    <Image src={selected.imageUrl} alt="card" fill sizes="400px" style={{ objectFit: "cover" }} />
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-slate-500">No image</div>
                  )}
                </div>
              </div>

              <div>
                <div className="flex flex-wrap gap-2">
                  {selected.isAuto && <Pill>Auto</Pill>}
                  {selected.serial && <Pill>/{selected.serial}</Pill>}
                  {selected.team && <Pill>{selected.team}</Pill>}
                  {selected.league && <Pill>{selected.league}</Pill>}
                </div>

                <div className="mt-3 grid gap-2 text-sm text-slate-200">
                  <Meta label="Set" value={`${selected.year} ${selected.cardSet}`} />
                  <Meta label="Card #" value={selected.cardNumber} />
                  <Meta label="Features" value={selected.features} />
                  <Meta label="Season" value={selected.season} />
                  <Meta label="Brand" value={selected.brand} />
                  <Meta label="Condition" value={selected.condition} />
                </div>

                <div className="mt-4 grid gap-2">
                  <button
                    onClick={() => copy(buildEbayTitle(selected), "Copied title")}
                    className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700"
                  >
                    Copy eBay Title
                  </button>
                  <button
                    onClick={() => copy(buildEbayDescription(selected), "Copied description")}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900"
                  >
                    Copy eBay Description (HTML)
                  </button>
                </div>

                <div className="mt-3 text-xs text-slate-500">
                  Card Name: <span className="text-slate-400">{selected.cardName || "—"}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-200 shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <div>
      <div className="text-sm font-semibold text-slate-200">{label}</div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
      >
        <option value="ALL">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
      {children}
    </span>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <div className="w-24 shrink-0 text-slate-400">{label}</div>
      <div className="text-slate-200">{value || "—"}</div>
    </div>
  );
}

function CardTile({ c, onClick }: { c: Card; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group overflow-hidden rounded-2xl border border-slate-800 bg-[#020617]/70 text-left",
        "hover:border-slate-600 hover:bg-[#020617] transition"
      )}
    >
      <div className="relative aspect-square w-full bg-slate-950">
        {c.imageUrl ? (
          <Image src={c.imageUrl} alt="card" fill sizes="260px" style={{ objectFit: "cover" }} />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-500">No image</div>
        )}
        <div className="absolute left-2 top-2 flex gap-1">
          {c.isAuto && <span className="rounded-md bg-blue-600/90 px-2 py-1 text-[10px] font-semibold">AUTO</span>}
          {c.serial && (
            <span className="rounded-md bg-slate-950/80 px-2 py-1 text-[10px] font-semibold border border-slate-700">
              /{c.serial}
            </span>
          )}
        </div>
      </div>

      <div className="p-3">
        <div className="text-sm font-semibold text-slate-100 line-clamp-1">{c.playerName || "—"}</div>
        <div className="mt-1 text-xs text-slate-400 line-clamp-1">
          {c.team ? `${c.team} • ` : ""}
          {c.league || ""}
        </div>
        <div className="mt-2 text-xs text-slate-200 line-clamp-2">
          {c.year} {c.cardSet}
        </div>
        <div className="mt-2 text-xs text-slate-400 line-clamp-2">{c.features || "—"}</div>
      </div>
    </button>
  );
}
