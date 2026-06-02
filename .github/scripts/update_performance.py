# -*- coding: utf-8 -*-
"""
Script per GitHub Actions: aggiorna performance/rating/volatilità da fondidoc.
Legge data/fondi.xlsx, scrappa fondidoc per ogni ISIN, ricostruisce il file.
Ottimizzato per girare entro 6h (1 req/ISIN invece di 3).
"""
import os, re, time, json, io, sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import pandas as pd

ROOT = Path(__file__).parent.parent.parent   # repo root
DATA = ROOT / "data"

print(f"Root: {ROOT}", flush=True)
print(f"Data: {DATA}", flush=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.fondidoc.it/Ricerca",
}
DELAY = 0.5

def pct(s):
    if not s or not isinstance(s, str): return None
    s = s.strip().replace("%","").replace(",",".").strip()
    try: return float(s)/100
    except: return None

def parse_ana(soup):
    data = {}
    tables = soup.find_all("table")
    if tables:
        rows = tables[0].find_all("tr")
        if len(rows) >= 2:
            hdrs = [c.get_text(strip=True) for c in rows[0].find_all(["th","td"])]
            vals = [c.get_text(strip=True) for c in rows[1].find_all(["th","td"])]
            mp = {"Anno corrente":"PERF. YTD","1 anno":"PERF. 1 ANNO","3 anni":"PERF. 3 ANNI"}
            for i,h in enumerate(hdrs):
                if h in mp and i < len(vals):
                    data[mp[h]] = pct(vals[i])
    if len(tables) > 1:
        rows = tables[1].find_all("tr")
        hdrs = [c.get_text(strip=True) for c in rows[0].find_all(["th","td"])] if rows else []
        col1 = next((i for i,h in enumerate(hdrs) if "1" in h), 1)
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th","td"])]
            if cells and "Volatilit" in cells[0] and col1 < len(cells):
                data["VOLATILITA' (1 anno)"] = pct(cells[col1]); break
    if len(tables) > 2:
        rows = tables[2].find_all("tr")
        if len(rows) >= 2:
            hdrs = [c.get_text(strip=True) for c in rows[0].find_all(["th","td"])]
            cells = [c.get_text(strip=True) for c in rows[1].find_all(["th","td"])]
            for i,h in enumerate(hdrs):
                if h in ("2022","2023","2024") and i < len(cells):
                    data[f"PERF. {h}"] = pct(cells[i])
    return data

def scrape_perf(s, isin):
    """Fetch search + Ana per ISIN. Ritorna dict con perf/vol/rating/classif."""
    try:
        r = s.post("https://www.fondidoc.it/Ricerca/Res",
                   data={"txt":isin,"viewMode":"fidaRtg","nview":"5"}, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.find("a", {"fidacode": True})
        if not link: return {}
        fc = link.get("fidacode"); purl = link.get("purl","")
        rating = len(soup.find_all("span", class_="icon-Corona_FIDA"))
        cat = None
        row_el = link.find_parent("tr")
        if row_el:
            for td in row_el.find_all("td", class_="hidden-xs"):
                t = td.get_text(strip=True)
                if t and t != isin and len(t) > 8:
                    cat = t; break
        res = {"RATING": str(rating) if rating > 0 else "", "CLASSIFICAZIONE": cat or ""}
        time.sleep(DELAY)
        r2 = s.get(f"https://www.fondidoc.it/d/Ana/{fc}/{purl}", timeout=12)
        if r2.status_code == 200:
            res.update(parse_ana(BeautifulSoup(r2.text,"html.parser")))
        time.sleep(DELAY)
        return res
    except Exception as e:
        return {"_error": str(e)}

# ── Carica Excel ─────────────────────────────────────────────────────────────
xlsx_path = DATA / "fondi.xlsx"
print(f"Carico {xlsx_path}...", flush=True)
sheets = pd.read_excel(xlsx_path, sheet_name=None, dtype=str)
main = sheets["tutti quelli trasferibili"]
main.columns = [str(c).strip() for c in main.columns]
isins = main["ISIN"].dropna().astype(str).str.strip().unique().tolist()
print(f"ISINs da aggiornare: {len(isins)}", flush=True)

# ── Scraping ──────────────────────────────────────────────────────────────────
s = requests.Session(); s.headers.update(HEADERS)
s.get("https://www.fondidoc.it/Ricerca", timeout=10)

PERF_COLS = ["CLASSIFICAZIONE","RATING","PERF. 1 ANNO","PERF. 3 ANNI","PERF. YTD",
             "PERF. 2024","PERF. 2023","PERF. 2022","VOLATILITA' (1 anno)"]

# Assicura colonne esistano
for col in PERF_COLS:
    if col not in main.columns:
        main[col] = None

results = {}
found = 0
for idx, isin in enumerate(isins):
    data = scrape_perf(s, isin)
    if data and not data.get("_error"):
        results[isin] = data
        if data.get("PERF. 1 ANNO"):
            found += 1
    if (idx+1) % 500 == 0:
        pct_done = (idx+1)/len(isins)*100
        print(f"  [{idx+1}/{len(isins)} {pct_done:.0f}%] trovati={found}", flush=True)

print(f"Scraping completo: {found}/{len(isins)}", flush=True)

# ── Aggiorna DataFrame ────────────────────────────────────────────────────────
main = main.set_index("ISIN")
for isin, data in results.items():
    if isin not in main.index: continue
    for col in PERF_COLS:
        v = data.get(col)
        if v is not None and str(v) not in ("", "nan", "None"):
            main.at[isin, col] = v
main = main.reset_index()
sheets["tutti quelli trasferibili"] = main
if "quelli gestibili" in sheets:
    sheets["quelli gestibili"] = main

# ── Salva Excel ───────────────────────────────────────────────────────────────
print("Salvo Excel...", flush=True)
with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    for sname, df in sheets.items():
        df.to_excel(writer, sheet_name=sname, index=False)

print(f"Salvato: {xlsx_path}", flush=True)
