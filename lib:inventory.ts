import fs from "fs";
import path from "path";

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

  // derived
  year: string;
  serial: string;
  isAuto: boolean;
};

function clean(s: string) {
  return (s ?? "").toString().trim().replace(/\s+/g, " ");
}

function inferYear(text: string) {
  const m = text.match(/\b(19\d{2}|20\d{2})\b/);
  return m ? m[1] : "";
}

function inferSerial(text: string) {
  const m = text.match(/\/\s*(\d{1,4})\b/);
  return m ? m[1] : "";
}

function inferAuto(text: string) {
  return /\b(auto|autograph)\b/i.test(text);
}

export function loadInventory(): Card[] {
  const p = path.join(process.cwd(), "public", "data", "inventory.tsv");
  const raw = fs.readFileSync(p, "utf8");
  const lines = raw.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];

  const header = lines[0].split("\t").map(clean);
  const idx = (name: string) => header.findIndex(h => h === name);

  const get = (cols: string[], row: string[]) => {
    for (const c of cols) {
      const i = idx(c);
      if (i >= 0) return clean(row[i] ?? "");
    }
    return "";
  };

  const cards: Card[] = [];
  for (let i = 1; i < lines.length; i++) {
    const row = lines[i].split("\t");
    const cardName = get(["Card Name"], row);
    const playerName = get(["Player Name"], row);
    const team = get(["Team", "Team "], row); // your file sometimes has trailing space
    const league = get(["League"], row);
    const cardSet = get(["Card Set"], row);
    const features = get(["Features"], row);
    const imageUrl = get(["IMAGE URL", "Image URL", "IMAGE_URL"], row);
    const cardNumber = get(["Card Number"], row);

    const year = inferYear(cardName) || inferYear(cardSet);
    const serial = inferSerial(features) || inferSerial(cardName);
    const isAuto = inferAuto(`${features} ${cardName}`);

    cards.push({
      cardName,
      playerName,
      sport: get(["Sport"], row),
      cardNumber,
      features,
      imageUrl,
      league,
      team,
      season: get(["Season"], row),
      condition: get(["Condition"], row),
      brand: get(["Brand"], row),
      cardSet,
      year,
      serial,
      isAuto
    });
  }
  return cards;
}
