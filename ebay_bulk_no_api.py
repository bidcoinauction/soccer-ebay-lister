#!/usr/bin/env python3
"""
ebay_bulk_no_api.py
No-API pipeline: read your inventory TSV -> normalize fields -> generate SKU + SEO Title + HTML Description
-> export eBay bulk-upload CSV using YOUR existing template header/columns.

✅ What this does (no scraping / no APIs):
- Reads:  "Full Card Inventory   - Sheet1.tsv" (tab-separated)
- Uses:   your eBay template CSV header + columns (keeps the first 4 lines exactly)
- Outputs: "ebay_bulk_out.csv" ready to import into eBay bulk uploader

How to run (from your "soccer script" folder):
  python3 ebay_bulk_no_api.py \
    --inventory "Full Card Inventory   - Sheet1.tsv" \
    --template "Ebay Listing w_ IMG,Player,etc. (Final) - Final_Corrected_eBay_Category_Upload.csv.csv" \
    --out "ebay_bulk_out.csv"

Optional:
  --default-price 9.99
  --price-column "MyPrice"          (if your TSV has a column with price)
  --title-mode A|B                  (default A)
  --condition-id 4000               (default 4000)
  --category 47140                  (default 47140 - soccer trading cards)
"""

from __future__ import annotations
import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict


# ------------------------- helpers -------------------------

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def slug(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "x"

def infer_year(text: str) -> str:
    t = text or ""
    m = re.search(r"\b(19\d{2}|20\d{2})\b", t)
    return m.group(1) if m else ""

def infer_serial(*texts: str) -> str:
    for t in texts:
        if not t:
            continue
        m = re.search(r"/\s*(\d{1,4})\b", t)
        if m:
            return m.group(1)
    return ""

def infer_auto(*texts: str) -> str:
    t = " ".join([x for x in texts if x])
    return "Yes" if re.search(r"\b(auto|autograph)\b", t, re.I) else "No"

def safe_float(s: str) -> Optional[float]:
    try:
        return float(str(s).strip())
    except Exception:
        return None

def psych_price(x: float) -> float:
    if x <= 1.0:
        return 0.99
    # $xx.99 style
    return max(0.99, round(x) - 0.01)

# ------------------------- data model -------------------------

@dataclass
class Card:
    card_name: str
    player: str
    sport: str
    card_number: str
    features: str
    image_url: str
    league: str
    team: str
    season: str
    condition: str
    brand: str
    card_set: str

    year: str = ""
    parallel: str = ""
    serial: str = ""
    auto: str = "No"
    grade_company: str = ""
    grade: str = ""

    # computed
    sku: str = ""
    title: str = ""
    description_html: str = ""
    price: Optional[float] = None

# ------------------------- template IO -------------------------

def read_template_header_lines(template_csv: str) -> Tuple[List[str], List[str]]:
    """
    Your template appears to have:
      line1: #INFO...
      line2: header columns row
      line3: #INFO explanatory row
      line4: blank row (or another info row)
    We preserve first 4 lines exactly, then append our data rows using the column header.
    """
    lines = Path(template_csv).read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        raise RuntimeError("Template file seems too short.")
    header_block = lines[:4] if len(lines) >= 4 else lines[:2]
    columns = next(csv.reader([lines[1]]))
    return header_block, columns

def write_bulk_csv(out_csv: str, header_lines: List[str], columns: List[str], rows: List[List[str]]) -> None:
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        for line in header_lines:
            f.write(line + "\n")
        w = csv.writer(f)
        for r in rows:
            if len(r) < len(columns):
                r = r + [""] * (len(columns) - len(r))
            elif len(r) > len(columns):
                r = r[:len(columns)]
            w.writerow(r)

# ------------------------- inventory IO -------------------------

def load_inventory_tsv(path: str) -> Tuple[List[Card], List[str]]:
    """
    Returns (cards, raw_fieldnames) so we can optionally use a user-provided price column.
    Expected TSV headers from your file include:
      Card Name, Player Name, Sport, Card Number, Features, IMAGE URL, League, Team , Season, Condition, Brand, Card Set
    """
    cards: List[Card] = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter="\t")
        fieldnames = r.fieldnames or []
        for row in r:
            c = Card(
                card_name=clean(row.get("Card Name", "")),
                player=clean(row.get("Player Name", "")),
                sport=clean(row.get("Sport", "")),
                card_number=clean(row.get("Card Number", "")),
                features=clean(row.get("Features", "")),
                image_url=clean(row.get("IMAGE URL", "")),
                league=clean(row.get("League", "")),
                team=clean(row.get("Team ", "")),      # note: your TSV uses "Team " with a trailing space
                season=clean(row.get("Season", "")),
                condition=clean(row.get("Condition", "")),
                brand=clean(row.get("Brand", "")),
                card_set=clean(row.get("Card Set", "")),
            )
            # infer extras
            c.year = infer_year(c.card_name) or infer_year(c.card_set)
            c.serial = infer_serial(c.features, c.card_name)
            c.auto = infer_auto(c.features, c.card_name)
            c.parallel = clean(c.features)  # you store parallels/insert info in Features
            cards.append(c)
    return cards, fieldnames

# ------------------------- content builders -------------------------

def make_sku(i: int, c: Card) -> str:
    # Stable-ish SKU: SOC_0001_player_cardnum
    num = re.sub(r"[^0-9A-Za-z]+", "", c.card_number or "")
    return f"SOC_{i:04d}_{slug(c.player)}_{slug(num)}"

def make_title(c: Card, mode: str = "A") -> str:
    """
    mode A: YEAR SET PLAYER INSERT/PARALLEL /SERIAL AUTO
    mode B: YEAR SET CARD# PLAYER INSERT/PARALLEL /SERIAL AUTO
    """
    year = c.year
    set_name = c.card_set
    parts: List[str] = []

    if mode.upper() == "B":
        parts = [year, set_name, c.card_number, c.player, c.parallel]
    else:
        parts = [year, set_name, c.player, c.parallel]

    if c.serial:
        parts.append(f"/{c.serial}")
    if (c.auto or "").lower() == "yes":
        parts.append("AUTO")

    # remove empty + de-dupe exact adjacent duplicates
    cleaned = []
    for p in [clean(x) for x in parts if clean(x)]:
        if cleaned and cleaned[-1] == p:
            continue
        cleaned.append(p)

    # common issue: year duplicated (e.g., year + set includes year). Remove if repeats.
    if len(cleaned) >= 2 and cleaned[0] == cleaned[1]:
        cleaned = cleaned[1:]

    return clean(" ".join(cleaned))[:80]  # keep title under ~80 chars

def make_description_html(c: Card) -> str:
    # Short, consistent, safe for eBay HTML
    auto = "Yes" if (c.auto or "").lower() == "yes" else "No"
    serial = f"/{c.serial}" if c.serial else ""
    parallel = c.parallel or ""
    return (
        f"<p><b>Player:</b> {c.player}</p>"
        f"<p><b>Team:</b> {c.team}</p>"
        f"<p><b>League:</b> {c.league}</p>"
        f"<p><b>Set:</b> {c.card_set}</p>"
        f"<p><b>Card Number:</b> {c.card_number}</p>"
        f"<p><b>Insert / Parallel:</b> {parallel}</p>"
        f"<p><b>Serial Number:</b> {serial}</p>"
        f"<p><b>Autograph:</b> {auto}</p>"
        f"<hr>"
        f"<p>Ships next business day. Securely packed (sleeve + top loader + team bag).</p>"
        f"<p>Card shown is the exact card you will receive.</p>"
    )

# ------------------------- map into template columns -------------------------

def build_row_for_template(
    columns: List[str],
    *,
    action: str,
    sku: str,
    category: int,
    title: str,
    picurl: str,
    condition_id: str,
    description_html: str,
    price: Optional[float],
    # item specifics
    player: str,
    team: str,
    league: str,
    parallel: str,
    card_number: str,
    autographed: str,
    features: str,
    year: str,
    season: str,
    manufacturer: str,
    set_short: str,
    card_name: str,
) -> List[str]:
    col_index = {c: i for i, c in enumerate(columns)}
    row = [""] * len(columns)

    def put(col: str, val: str):
        if col in col_index:
            row[col_index[col]] = val

    # Your template has multiple action columns; in your earlier examples, action is the 2nd "*Action(" column.
    action_cols = [c for c in columns if c.startswith("*Action(")]
    if len(action_cols) >= 2:
        row[col_index[action_cols[1]]] = action
    elif len(action_cols) == 1:
        row[col_index[action_cols[0]]] = action

    put("CustomLabel", sku)
    put("*Category", str(category))
    put("*Title", title)
    put("PicURL", picurl)
    put("*ConditionID", condition_id)

    # price column name varies by template; try common ones
    if price is not None:
        for price_col in ("*StartPrice", "StartPrice", "Price", "*Price"):
            if price_col in col_index:
                row[col_index[price_col]] = f"{price:.2f}"
                break

    # description column also varies; try common
    for desc_col in ("*Description", "Description"):
        if desc_col in col_index:
            row[col_index[desc_col]] = description_html
            break

    # item specifics (your template columns use "C:...")
    put("C:Player/Athlete", player)
    put("C:Team", team)
    put("C:League", league)
    put("C:Parallel/Variety", parallel)
    put("C:Card Number", card_number)
    put("C:Autographed", autographed)
    put("C:Features", features)
    put("C:Year Manufactured", year)
    put("C:Season", season)
    put("C:Manufacturer", manufacturer)
    put("C:Set", set_short)
    put("C:Card Name", card_name)

    return row

def infer_set_short(card_set: str) -> str:
    # Optional: shorten set name slightly for item specifics
    s = clean(card_set)
    # example: "2024 Topps Finest MLS" -> "Topps Finest MLS"
    s = re.sub(r"^(19\d{2}|20\d{2})\s+", "", s)
    return s

# ------------------------- main -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default="Full Card Inventory   - Sheet1.tsv")
    ap.add_argument("--template", default="Ebay Listing w_ IMG,Player,etc. (Final) - Final_Corrected_eBay_Category_Upload.csv.csv")
    ap.add_argument("--out", default="ebay_bulk_out.csv")

    ap.add_argument("--category", type=int, default=47140)
    ap.add_argument("--condition-id", default="4000")

    ap.add_argument("--title-mode", choices=["A", "B"], default="A")
    ap.add_argument("--default-price", type=float, default=None, help="Set a flat price for all rows (optional).")
    ap.add_argument("--price-column", default=None, help="If your TSV contains a numeric price column, use it.")
    ap.add_argument("--psych-price", action="store_true", help="Convert prices to .99 style.")

    args = ap.parse_args()

    header_lines, columns = read_template_header_lines(args.template)
    cards, inv_cols = load_inventory_tsv(args.inventory)

    # If user wants price from column, confirm it exists; otherwise silently ignore
    use_price_col = args.price_column if (args.price_column in (inv_cols or [])) else None

    out_rows: List[List[str]] = []

    # reload TSV rows again only if we need price col values
    price_map: Dict[int, Optional[float]] = {}
    if use_price_col:
        with open(args.inventory, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f, delimiter="\t")
            for idx, row in enumerate(r, start=1):
                price_map[idx] = safe_float(row.get(use_price_col, ""))

    for i, c in enumerate(cards, start=1):
        c.sku = make_sku(i, c)
        c.title = make_title(c, mode=args.title_mode)
        c.description_html = make_description_html(c)

        # price: explicit default overrides column
        price = None
        if args.default_price is not None:
            price = float(args.default_price)
        elif use_price_col:
            price = price_map.get(i)

        if price is not None and args.psych_price:
            price = psych_price(price)

        autographed = "Yes" if (c.auto or "").lower() == "yes" else "No"
        set_short = infer_set_short(c.card_set)

        row = build_row_for_template(
            columns,
            action="Add",
            sku=c.sku,
            category=args.category,
            title=c.title,
            picurl=c.image_url,
            condition_id=args.condition_id,
            description_html=c.description_html,
            price=price,
            player=c.player,
            team=c.team,
            league=c.league,
            parallel=c.parallel,
            card_number=c.card_number,
            autographed=autographed,
            features=c.features,
            year=c.year,
            season=c.season,
            manufacturer=c.brand,
            set_short=set_short,
            card_name=c.card_name,
        )
        out_rows.append(row)

    write_bulk_csv(args.out, header_lines, columns, out_rows)
    print(f"Wrote eBay bulk file: {args.out}")
    print(f"Rows exported: {len(out_rows)}")
    if use_price_col:
        print(f"Pricing source: TSV column '{use_price_col}'")
    elif args.default_price is not None:
        print(f"Pricing source: default-price {args.default_price}")
    else:
        print("Pricing source: none (blank prices)")

if __name__ == "__main__":
    main()
