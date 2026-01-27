import Image from "next/image";
import { loadInventory, Card } from "@/lib/inventory";

function uniq(arr: string[]) {
  return Array.from(new Set(arr.filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

export default function Page() {
  const cards = loadInventory();

  const sets = uniq(cards.map(c => c.cardSet));
  const teams = uniq(cards.map(c => c.team));
  const leagues = uniq(cards.map(c => c.league));

  // This page is server-rendered; filtering will be client-side in v2.
  // For v1: just show the gallery + basic grouping.
  return (
    <div style={{ minHeight: "100vh", background: "#0b1220", color: "#e5e7eb" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 28 }}>⚽ Soccer eBay Lister</h1>
            <p style={{ margin: "8px 0 0", opacity: 0.85 }}>
              Inventory gallery powered by your repo TSV. ({cards.length} cards)
            </p>
          </div>

          <a
            href="/data/inventory.tsv"
            style={{
              color: "#93c5fd",
              textDecoration: "none",
              border: "1px solid #1e293b",
              padding: "10px 12px",
              borderRadius: 10
            }}
          >
            Download TSV
          </a>
        </div>

        <div style={{ marginTop: 18, display: "flex", gap: 10, flexWrap: "wrap", opacity: 0.85, fontSize: 13 }}>
          <span>Sets: {sets.length}</span>
          <span>Teams: {teams.length}</span>
          <span>Leagues: {leagues.length}</span>
        </div>

        <div
          style={{
            marginTop: 22,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
            gap: 14
          }}
        >
          {cards.map((c, i) => (
            <CardTile key={`${c.playerName}-${c.cardNumber}-${i}`} card={c} />
          ))}
        </div>
      </div>
    </div>
  );
}

function CardTile({ card }: { card: Card }) {
  const title = `${card.year} ${card.cardSet} ${card.playerName} ${card.features}${card.serial ? ` /${card.serial}` : ""}${card.isAuto ? " AUTO" : ""}`
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 90);

  return (
    <div
      style={{
        background: "rgba(2, 6, 23, 0.85)",
        border: "1px solid #1e293b",
        borderRadius: 14,
        overflow: "hidden"
      }}
      title={title}
    >
      <div style={{ position: "relative", width: "100%", paddingTop: "100%", background: "#020617" }}>
        {card.imageUrl ? (
          <Image
            src={card.imageUrl}
            alt={title}
            fill
            sizes="300px"
            style={{ objectFit: "cover" }}
          />
        ) : null}
      </div>

      <div style={{ padding: 12 }}>
        <div style={{ fontWeight: 700, fontSize: 14, lineHeight: 1.2 }}>{card.playerName || "—"}</div>
        <div style={{ fontSize: 12, opacity: 0.8, marginTop: 6 }}>
          {card.team ? `${card.team} • ` : ""}{card.league || ""}
        </div>
        <div style={{ fontSize: 12, opacity: 0.9, marginTop: 8 }}>
          {card.year} {card.cardSet}
        </div>
        <div style={{ fontSize: 12, opacity: 0.75, marginTop: 8 }}>
          {card.features || "—"}
          {card.serial ? ` • /${card.serial}` : ""}
          {card.isAuto ? " • AUTO" : ""}
        </div>
      </div>
    </div>
  );
}
