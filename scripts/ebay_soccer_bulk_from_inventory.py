#!/usr/bin/env python3
"""
ebay_soccer_bulk_from_inventory.py
- Reads your inventory TSV
- Scrapes SOLD comps from eBay using ScrapingBee (no eBay API)
- Exact-match -> fallback comps tiers
- Labels confidence
- Writes an eBay bulk-upload CSV using your existing template’s header structure

INPUTS (defaults match your uploaded files):
  --inventory "/mnt/data/Full Card Inventory   - Sheet1.tsv"
  --template  "/mnt/data/Ebay Listing w_ IMG,Player,etc. (Final) - Final_Corrected_eBay_Category_Upload.csv.csv"
OUTPUT:
  --out "ebay_bulk_out.csv"

ENV:
  SCRAPINGBEE_API_KEY = your key (rotate yours since it was pasted in chat)
"""

from __future__ import annotations
import argparse
import csv
import os
import re
import time
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

SCRAPINGBEE_ENDPOINT = "https://app.scrapingbee.com/api/v1/"

# -------------------- parsing helpers --------------------
_money_re = re.compile(r"[\$£€]\s*([\d,]+(?:\.\d{2})?)")
_range_re = re.compile(r"([\$£€]\s*[\d,]+(?:\.\d{2})?)\s+to\s+([\$£€]\s*[\d,]+(?:\.\d{2})?)", re.I)

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def parse_money(text: str) -> Optional[float]:
    if not text:
        return None
    text = clean(text)

    mrange = _range_re.search(text)
    if mrange:
        low = mrange.group(1)
        m = _money_re.search(low)
        if not m:
            return None
        return float(m.group(1).replace(",", ""))

    m = _money_re.search(text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))

def robust_median(prices: List[float], take_n: int = 20) -> Optional[float]:
    if not prices:
        return None
    prices = prices[:take_n]
    if len(prices) >= 6:
        sp = sorted(prices)
        k = max(1, int(len(sp) * 0.10))
        core = sp[k:len(sp)-k] if len(sp) - 2*k >= 3 else sp
        return statistics.median(core)
    return statistics.median(prices)

# -------------------- pricing rules --------------------
def grade_multiplier(grade_company: str, grade: str) -> float:
    g = (grade or "").strip()
    if not g:
        return 1.0
    if g == "10":
        return 1.15
    if g == "9":
        return 1.00
    if g == "8":
        return 0.75
    return 0.90

def serial_multiplier(serial: str) -> float:
    try:
        n = int(re.sub(r"[^0-9]", "", serial or ""))
        if n <= 10: return 1.30
        if n <= 25: return 1.18
        if n <= 50: return 1.10
        if n <= 99: return 1.05
    except Exception:
        pass
    return 1.0

def psych_price(x: float) -> float:
    if x <= 1.0:
        return 0.99
    return max(0.99, round(x) - 0.01)

# -------------------- ScrapingBee fetch --------------------
def scrapingbee_get(url: str, *, render_js: bool=False, premium_proxy: bool=False, wait: int=0) -> str:
    api_key = os.getenv("SCRAPINGBEE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing SCRAPINGBEE_API_KEY env var.")

    params = {"api_key": api_key, "url": url}
    if render_js:
        params["render_js"] = "true"
    if premium_proxy:
        params["premium_proxy"] = "true"
    if wait and wait > 0:
        params["wait"] = str(wait)

    r = requests.get(SCRAPINGBEE_ENDPOINT, params=params, timeout=60)
    r.raise_for_status()
    return r.text

# -------------------- eBay SOLD search --------------------
def build_ebay_sold_search_url(query: str, category_id: int) -> str:
    base = "https://www.ebay.com/sch/i.html"
    qs = {
        "_nkw": query,
        "_sacat": str(category_id),
        "LH_Sold": "1",
        "LH_Complete": "1",
    }
    return f"{base}?{urlencode(qs)}"

def extract_sold_prices(html: str) -> List[float]:
    soup = BeautifulSoup(html, "lxml")

    prices: List[float] = []
    # Common eBay selector
    for el in soup.select(".s-item__price"):
        p = parse_money(el.get_text(" ", strip=True))
        if p is not None:
            prices.append(p)

    # fallback if eBay changes classes
    if not prices:
        for el in soup.select("[class*='price']"):
            p = parse_money(el.get_text(" ", strip=True))
            if p is not None:
                prices.append(p)

    seen = set()
    out = []
    for p in prices:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out

# -------------------- inventory model --------------------
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

    # derived / optional
    year: str = ""
    set_short: str = ""
    parallel: str = ""
    auto: str = "No"
    serial: str = ""
    grade_company: str = ""
    grade: str = ""

def infer_year(card_name: str) -> str:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", card_name)
    return m.group(1) if m else ""

def infer_serial(features: str, card_name: str) -> str:
    # looks for /25, /99 etc
    for s in (features or "", card_name or ""):
        m = re.search(r"/\s*(\d{1,4})\b", s)
        if m:
            return m.group(1)
    return ""

def infer_auto(features: str, card_name: str) -> str:
    t = (features or "") + " " + (card_name or "")
    return "Yes" if re.search(r"\b(auto|autograph)\b", t, re.I) else "No"

def infer_parallel(features: str) -> str:
    # treat Features as Parallel/Variety for your template
    return clean(features)

def make_sku(idx: int, player: str, card_number: str) -> str:
    # stable-ish SKU
    base = re.sub(r"[^a-z0-9]+", "_", (player or "").strip().lower()).strip("_")
    num = re.sub(r"[^0-9]+", "", card_number or "")
    return f"SOC_{idx:04d}_{base}_{num or 'x'}"

# -------------------- query tiers (exact -> fallback) --------------------
def build_query_tiers(c: Card) -> List[Tuple[str, str]]:
    """
    Returns list of (tier_name, query_string).
    Tier order goes from strict -> loose.
    """
    year = c.year or infer_year(c.card_name)
    set_name = c.card_set or ""
    player = c.player or ""
    insert_parallel = c.parallel or infer_parallel(c.features)
    serial = c.serial or infer_serial(c.features, c.card_name)
    auto = c.auto or infer_auto(c.features, c.card_name)

    tiers: List[Tuple[str, str]] = []

    # Tier 1: very strict
    q1_parts = [year, set_name, player, insert_parallel]
    if serial:
        q1_parts.append(f"/{serial}")
    if auto.lower() == "yes":
        q1_parts.append("auto")
    # include grading if present
    if c.grade_company and c.grade:
        q1_parts += [c.grade_company, c.grade]
    tiers.append(("exact", clean(" ".join([p for p in q1_parts if p]))))

    # Tier 2: drop grade
    q2_parts = [year, set_name, player, insert_parallel]
    if serial:
        q2_parts.append(f"/{serial}")
    if auto.lower() == "yes":
        q2_parts.append("auto")
    tiers.append(("no_grade", clean(" ".join([p for p in q2_parts if p]))))

    # Tier 3: drop serial
    q3_parts = [year, set_name, player, insert_parallel]
    if auto.lower() == "yes":
        q3_parts.append("auto")
    tiers.append(("no_serial", clean(" ".join([p for p in q3_parts if p]))))

    # Tier 4: drop parallel/features
    q4_parts = [year, set_name, player]
    if auto.lower() == "yes":
        q4_parts.append("auto")
    tiers.append(("player_set", clean(" ".join([p for p in q4_parts if p]))))

    # Tier 5: player + set only (last resort)
    q5_parts = [set_name, player]
    tiers.append(("loose", clean(" ".join([p for p in q5_parts if p]))))

    # remove empty or duplicates while preserving order
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for name, q in tiers:
        if not q or q in seen:
            continue
        seen.add(q)
        uniq.append((name, q))
    return uniq

def confidence_label(tier: str, comp_count: int) -> str:
    if tier == "exact" and comp_count >= 6:
        return "HIGH"
    if tier in ("exact", "no_grade") and comp_count >= 3:
        return "MED"
    if comp_count >= 3:
        return "LOW"
    return "VERY_LOW"

# -------------------- eBay template read/write --------------------
def read_template_header_lines(template_csv: str) -> Tuple[List[str], List[str]]:
    """
    Your template has:
      line1: Info,Version...
      line2: column header row (72 cols)
      line3: another header-ish row (we’ll preserve it)
      line4: blank
    We preserve first 4 lines exactly, then append our data rows.
    """
    lines = Path(template_csv).read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 4:
        raise RuntimeError("Template file is shorter than expected.")
    return lines[:4], next(csv.reader([lines[1]]))

def write_bulk_csv(out_csv: str, header_lines: List[str], columns: List[str], rows: List[List[str]]) -> None:
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        # write preserved header block exactly
        for line in header_lines:
            f.write(line + "\n")
        w = csv.writer(f)
        for r in rows:
            # ensure same column count
            if len(r) < len(columns):
                r = r + [""] * (len(columns) - len(r))
            elif len(r) > len(columns):
                r = r[:len(columns)]
            w.writerow(r)

# -------------------- mapping to template columns --------------------
def build_row_for_template(columns: List[str], *, action: str, sku: str, category: int,
                           title: str, picurl: str, player: str, team: str, league: str,
                           parallel: str, card_number: str, condition_id: str,
                           autographed: str, features: str, year: str, season: str,
                           manufacturer: str, set_short: str, card_name: str,
                           suggested_price: Optional[float], comp_tier: str, comp_conf: str,
                           comp_count: int, comp_median: Optional[float], query_url: str) -> List[str]:
    """
    We fill the key columns from your template header.
    Everything else stays blank.
    """
    col_index = {c: i for i, c in enumerate(columns)}
    row = [""] * len(columns)

    def put(col: str, val: str):
        if col in col_index:
            row[col_index[col]] = val

    # Your template has duplicate *Action columns; the actual "Add" appears in 3rd field in example rows.
    # We follow your file behavior:
    # - col0 empty
    # - col1 CustomLabel
    # - col2 *Action (Add)
    # - col3 *Category
    # Therefore: leave first *Action blank, put SKU in CustomLabel, put action in the second *Action.
    put("CustomLabel", sku)

    # Find the SECOND "*Action(...)" column by scanning prefix match
    action_cols = [c for c in columns if c.startswith("*Action(")]
    if len(action_cols) >= 2:
        row[col_index[action_cols[1]]] = action
    elif len(action_cols) == 1:
        row[col_index[action_cols[0]]] = action

    put("*Category", str(category))
    put("*Title", title)
    put("PicURL", picurl)

    put("C:Player/Athlete", player)
    put("C:Team", team)
    put("C:League", league)
    put("C:Parallel/Variety", parallel)
    put("C:Card Number", card_number)

    put("*ConditionID", condition_id)
    put("C:Autographed", autographed)
    put("C:Features", features)
    put("C:Year Manufactured", year)
    put("C:Season", season)
    put("C:Manufacturer", manufacturer)
    put("C:Set", set_short)
    put("C:Card Name", card_name)

    # If your template includes a price column, try to fill it.
    # Some templates name it "*StartPrice" or "StartPrice" or "Price".
    for price_col in ("*StartPrice", "StartPrice", "Price", "*Price"):
        if price_col in col_index and suggested_price:
            row[col_index[price_col]] = f"{suggested_price:.2f}"
            break

    # Optional: drop diagnostics into unused “Subtitle” if present
    if "Subtitle" in col_index:
        diag = f"comps:{comp_count} med:{(round(comp_median,2) if comp_median is not None else 'na')} tier:{comp_tier} conf:{comp_conf}"
        row[col_index["Subtitle"]] = diag[:80]

    # Optional: if “AdditionalDetails” exists, include query URL
    if "AdditionalDetails" in col_index:
        row[col_index["AdditionalDetails"]] = query_url[:500]

    return row

# -------------------- main flow --------------------
def load_inventory_tsv(path: str) -> List[Card]:
    cards: List[Card] = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            c = Card(
                card_name=clean(row.get("Card Name", "")),
                player=clean(row.get("Player Name", "")),
                sport=clean(row.get("Sport", "")),
                card_number=clean(row.get("Card Number", "")),
                features=clean(row.get("Features", "")),
                image_url=clean(row.get("IMAGE URL", "")),
                league=clean(row.get("League", "")),
                team=clean(row.get("Team ", "")),
                season=clean(row.get("Season", "")),
                condition=clean(row.get("Condition", "")),
                brand=clean(row.get("Brand", "")),
                card_set=clean(row.get("Card Set", "")),
            )
            c.year = infer_year(c.card_name)
            c.parallel = infer_parallel(c.features)
            c.serial = infer_serial(c.features, c.card_name)
            c.auto = infer_auto(c.features, c.card_name)
            # template uses "Topps Finest" (short) in sample; try to infer a shorter set label
            c.set_short = "Topps Finest" if "Finest" in c.card_set else clean(c.card_set)
            cards.append(c)
    return cards

def make_title(c: Card) -> str:
    parts = [c.year, c.card_set, c.card_number, c.player, c.parallel]
    if c.serial:
        parts.append(f"/{c.serial}")
    if c.auto.lower() == "yes":
        parts.append("AUTO")
    return clean(" ".join([p for p in parts if p]))

def fetch_best_comps_for_card(c: Card, *, category_id: int, min_comps: int,
                             render_js: bool, premium_proxy: bool, wait: int,
                             take_n: int) -> Tuple[str, str, int, Optional[float], Optional[float], str]:
    """
    Returns:
      (tier_name, confidence, comp_count, comp_median, suggested_price, query_url)
    """
    tiers = build_query_tiers(c)

    best = None  # (tier, count, median, url)
    for tier_name, q in tiers:
        url = build_ebay_sold_search_url(q, category_id=category_id)
        html = scrapingbee_get(url, render_js=render_js, premium_proxy=premium_proxy, wait=wait)
        prices = extract_sold_prices(html)
        med = robust_median(prices, take_n=take_n)

        if best is None:
            best = (tier_name, len(prices), med, url)

        # stop early if good enough
        if len(prices) >= min_comps and med is not None:
            best = (tier_name, len(prices), med, url)
            break

        # otherwise keep the best count/median seen so far
        if best is not None:
            bt, bc, bm, bu = best
            if len(prices) > bc and med is not None:
                best = (tier_name, len(prices), med, url)

    tier_name, count, med, url = best if best else ("loose", 0, None, "")
    conf = confidence_label(tier_name, count)

    if med is None:
        return tier_name, conf, count, None, None, url

    suggested = med * grade_multiplier(c.grade_company, c.grade) * serial_multiplier(c.serial)
    suggested = psych_price(suggested)
    return tier_name, conf, count, med, suggested, url

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default="/mnt/data/Full Card Inventory   - Sheet1.tsv")
    ap.add_argument("--template", default="/mnt/data/Ebay Listing w_ IMG,Player,etc. (Final) - Final_Corrected_eBay_Category_Upload.csv.csv")
    ap.add_argument("--out", default="ebay_bulk_out.csv")
    ap.add_argument("--category", type=int, default=47140, help="Soccer trading cards category")
    ap.add_argument("--min-comps", type=int, default=5)
    ap.add_argument("--take-n", type=int, default=20)
    ap.add_argument("--sleep", type=float, default=1.4)
    ap.add_argument("--render-js", action="store_true")
    ap.add_argument("--premium-proxy", action="store_true")
    ap.add_argument("--wait", type=int, default=0)
    ap.add_argument("--condition-id", default="4000", help="Template sample uses 4000; keep consistent unless you change it")
    args = ap.parse_args()

    header_lines, columns = read_template_header_lines(args.template)
    cards = load_inventory_tsv(args.inventory)

    out_rows: List[List[str]] = []

    for i, c in enumerate(cards, start=1):
        sku = make_sku(i, c.player, c.card_number)
        title = make_title(c)
        picurl = c.image_url

        tier, conf, comp_count, comp_median, suggested, query_url = fetch_best_comps_for_card(
            c,
            category_id=args.category,
            min_comps=args.min_comps,
            render_js=args.render_js,
            premium_proxy=args.premium_proxy,
            wait=args.wait,
            take_n=args.take_n,
        )

        row = build_row_for_template(
            columns,
            action="Add",
            sku=sku,
            category=args.category,
            title=title,
            picurl=picurl,
            player=c.player,
            team=c.team,
            league=c.league,
            parallel=c.parallel,
            card_number=c.card_number,
            condition_id=args.condition_id,
            autographed="Yes" if c.auto.lower() == "yes" else "No",
            features=c.features,
            year=c.year,
            season=c.season,
            manufacturer=c.brand,
            set_short=c.set_short,
            card_name=c.card_name,
            suggested_price=suggested,
            comp_tier=tier,
            comp_conf=conf,
            comp_count=comp_count,
            comp_median=comp_median,
            query_url=query_url,
        )
        out_rows.append(row)

        print(f"[{i}/{len(cards)}] {sku} comps={comp_count} tier={tier} conf={conf} med={comp_median} -> {suggested} | {c.player}")
        time.sleep(args.sleep)

    write_bulk_csv(args.out, header_lines, columns, out_rows)
    print(f"\nWrote eBay bulk file: {args.out}")

if __name__ == "__main__":
    main()
