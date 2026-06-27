# -*- coding: utf-8 -*-
"""
Aggiorna performance + volatilita 1Y in data/fondi.xlsx scaricando da fondidoc.it.
Pensato per girare in GitHub Actions (il 2 di ogni mese). Streamlit Cloud
ridistribuisce automaticamente l'app al commit del file aggiornato.

Schema file dell'app (header riga 1, dati da riga 2):
  col 3  = ISIN
  col 21 = PERF. 1 ANNO   col 22 = PERF. 3 ANNI   col 23 = PERF. YTD
  col 24 = PERF. 2024     col 25 = PERF. 2023     col 26 = PERF. 2022
  col 27 = VOLATILITA' (1 anno)
  col 30 = SCHEDA FONDIDOC (link)
L'app usa solo la scheda 'tutti quelli trasferibili'; 'quelli gestibili' e' un duplicato.
"""
import re, time, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests
from bs4 import BeautifulSoup
import openpyxl

BASE = Path(__file__).parent
EXCEL = BASE / "data" / "fondi.xlsx"
MAIN_SHEET = "tutti quelli trasferibili"
MIRROR_SHEET = "quelli gestibili"
WORKERS = 12

COL_ISIN = 3
COL_FONDIDOC = 30
# mappa colonna -> chiave dato
MAPPING = {21: 'p1y', 22: 'p3y', 23: 'ytd', 24: 'p2024', 25: 'p2023', 26: 'p2022', 27: 'vol1y'}

PERC_RE = re.compile(r'-?\d+[,.]\d+%')
_tl = threading.local()


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def parse_pct(s):
    try:
        return round(float(s.replace('%', '').replace(',', '.')) / 100, 6)
    except Exception:
        return None


def get_session():
    s = getattr(_tl, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        _tl.s = s
    return s


def fetch(url, timeout=25):
    last = None
    for _ in range(3):
        try:
            return get_session().get(url, timeout=timeout)
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def scrape_fund(fd_url):
    result = {}
    r = fetch(fd_url)
    lines = [l.strip() for l in BeautifulSoup(r.text, "html.parser").get_text(separator="\n").split("\n") if l.strip()]
    for j, line in enumerate(lines):
        nxt = lines[j + 1] if j + 1 < len(lines) else ''
        if 'YTD' in line and ('1 anno' in line or '1Y' in line or 'anno' in nxt):
            vals = PERC_RE.findall(line) or (PERC_RE.findall(lines[j + 1]) if j + 1 < len(lines) else [])
            if vals:
                result['ytd'] = parse_pct(vals[0])
                result['p1y'] = parse_pct(vals[1]) if len(vals) > 1 else None
                result['p3y'] = parse_pct(vals[2]) if len(vals) > 2 else None
            break
    for j, line in enumerate(lines):
        if '2024' in line and '2023' in line and '2022' in line:
            vals = PERC_RE.findall(line) or (PERC_RE.findall(lines[j + 1]) if j + 1 < len(lines) else [])
            if len(vals) >= 3:
                if '2022' in line.split('2023')[0]:
                    result['p2022'], result['p2023'], result['p2024'] = parse_pct(vals[0]), parse_pct(vals[1]), parse_pct(vals[2])
                else:
                    result['p2024'], result['p2023'], result['p2022'] = parse_pct(vals[0]), parse_pct(vals[1]), parse_pct(vals[2])
            break
    try:
        r2 = fetch(fd_url.replace("/d/Index/", "/d/Ana/"))
        lines2 = [l.strip() for l in BeautifulSoup(r2.text, "html.parser").get_text(separator="\n").split("\n") if l.strip()]
        for j, line in enumerate(lines2):
            if 'olatil' in line and 'negativa' not in line:
                for k in range(j + 1, min(j + 8, len(lines2))):
                    if PERC_RE.match(lines2[k]):
                        result['vol1y'] = parse_pct(lines2[k])
                        break
                break
    except Exception:
        pass
    return result


def fondidoc_url(cell):
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target
    v = (cell.value or '')
    return v if isinstance(v, str) and v.startswith('http') else None


def main():
    log(f"Apertura {EXCEL}")
    wb = openpyxl.load_workbook(str(EXCEL))
    ws = wb[MAIN_SHEET]

    # raccogli URL FondiDoc (dedup) e ISIN->righe
    url_by_isin = {}
    for r in range(2, ws.max_row + 1):
        isin = (ws.cell(r, COL_ISIN).value or '')
        isin = str(isin).strip() if isin else ''
        if not isin:
            continue
        u = fondidoc_url(ws.cell(r, COL_FONDIDOC))
        if u and isin not in url_by_isin:
            url_by_isin[isin] = u
    log(f"ISIN con link FondiDoc: {len(url_by_isin)} (con {WORKERS} thread)")

    results = {}
    done = errors = 0
    urls = {u for u in url_by_isin.values()}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(scrape_fund, u): u for u in urls}
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                results[futs[fut]] = fut.result()
                done += 1
            except Exception:
                errors += 1
            if n % 500 == 0:
                log(f"  {n}/{len(urls)} (ok {done}, err {errors})")

    # scrivi nelle due schede (gestibili = duplicato)
    for sheet in (MAIN_SHEET, MIRROR_SHEET):
        if sheet not in wb.sheetnames:
            continue
        w = wb[sheet]
        upd = 0
        for r in range(2, w.max_row + 1):
            isin = (w.cell(r, COL_ISIN).value or '')
            isin = str(isin).strip() if isin else ''
            u = url_by_isin.get(isin)
            d = results.get(u) if u else None
            if not d:
                continue
            for col, key in MAPPING.items():
                v = d.get(key)
                if v is not None:
                    c = w.cell(r, col)
                    c.value = v
                    c.number_format = '0.00%'
            upd += 1
        log(f"  '{sheet}': {upd} righe aggiornate")

    wb.save(str(EXCEL))
    log(f"FINITO. ok {done}, err {errors}. Salvato {EXCEL}.")


if __name__ == "__main__":
    main()
