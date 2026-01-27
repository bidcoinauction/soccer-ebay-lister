// lib/inventory.ts
export type Card = {
  cardName: string;
  playerName: string;
  sport: string;
  cardNumber: string;
  features: string;
  imageUrl: string;
  league: string;
  team: string;
  season: string;
  condition: string;
  brand: string;
  cardSet: string;

  year: string;
  serial: string;
  isAuto: boolean;
};

function clean(s: any) {
  return (s ?? "").toString().trim().replace(/\s+/g, " ");
}

function inferYear(text: string) {
  const m = (text || "").match(/\b(19\d{2}|20\d{2})\b/);
  return m ? m[1] : "";
}

function inferSerial(text: string) {
  const m = (text || "").match(/\/\s*(\d{1,4})\b/);
  return m ? m[1] : "";
}

function inferAuto(text: string) {
  return /\b(auto|autograph)\b/i.test(text || "");
}

function parseTSV(tsv: string): Card[] {
  const lines = tsv.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) return [];

  const header = lines[0].split("\t").map(clean);
  const idx = (name: string) => header.findIndex((h) => h === name);

  const get = (row: string[], names: string[]) => {
    for (const n of names) {
      const i = idx(n);
      if (i >= 0) return clean(row[i] ?? "");
    }
    return "";
  };

  const out: Card[] = [];
  for (let i = 1; i < lines.length; i++) {
    const row = lines[i].split("\t");

    const cardName = get(row, ["Card Name"]);
    const playerName = get(row, ["Player Name"]);
    const team = get(row, ["Team", "Team "]);
    const league = get(row, ["League"]);
    const cardSet = get(row, ["Card Set"]);
    const features = get(row, ["Features"]);
    const imageUrl = get(row, ["IMAGE URL", "Image URL", "IMAGE_URL"]);
    const cardNumber = get(row, ["Card Number"]);

    const year = inferYear(cardName) || inferYear(cardSet);
    const serial = inferSerial(features) || inferSerial(cardName);
    const isAuto = inferAuto(`${features} ${cardName}`);

    out.push({
      cardName,
      playerName,
      sport: get(row, ["Sport"]),
      cardNumber,
      features,
      imageUrl,
      league,
      team,
      season: get(row, ["Season"]),
      condition: get(row, ["Condition"]),
      brand: get(row, ["Brand"]),
      cardSet,
      year,
      serial,
      isAuto,
    });
  }
  return out;
}

export async function fetchInventory(): Promise<Card[]> {
  const res = await fetch("/data/inventory.tsv", { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load /data/inventory.tsv (${res.status})`);
  return parseTSV(await res.text());
}

export function buildEbayTitle(c: Card): string {
  const parts = [c.year, c.cardSet, c.playerName, c.features, c.serial ? `/${c.serial}` : "", c.isAuto ? "AUTO" : ""]
    .map(clean)
    .filter(Boolean);

  // remove duplicate year if set already starts with year
  if (parts.length >= 2 && parts[0] && parts[1].startsWith(parts[0])) parts.shift();

  return clean(parts.join(" ")).slice(0, 80);
}

export function buildEbayDescription(c: Card): string {
  const autoStr = c.isAuto ? "Yes" : "No";
  const serialStr = c.serial ? `/${c.serial}` : "";

  return (
    `<p><b>Player:</b> ${clean(c.playerName)}</p>` +
    `<p><b>Team:</b> ${clean(c.team)}</p>` +
    `<p><b>League:</b> ${clean(c.league)}</p>` +
    `<p><b>Set:</b> ${clean(c.year)} ${clean(c.cardSet)}</p>` +
    `<p><b>Card Number:</b> ${clean(c.cardNumber)}</p>` +
    `<p><b>Insert / Parallel:</b> ${clean(c.features)}</p>` +
    `<p><b>Serial Number:</b> ${clean(serialStr)}</p>` +
    `<p><b>Autograph:</b> ${autoStr}</p>` +
    `<hr>` +
    `<p>Ships next business day. Securely packed (sleeve + top loader + team bag).</p>` +
    `<p>Card shown is the exact card you will receive.</p>`
  );
}
