# -*- coding: utf-8 -*-
"""
Screenshot della pagina Quantalys Historique tramite Playwright.
Stessa logica dell'app Azimut Portfolio Analyzer.
"""
import re
import hashlib
from pathlib import Path


_CACHE_DIR = Path(__file__).parent.parent / "data" / "qtl_chart_cache"


def qtl_historique_url(url: str) -> str:
    """Converte URL Quantalys fondo → URL pagina Historique."""
    m = re.search(r'quantalys\.it/[Ff]onds(?:/[A-Za-z]+)?/(\d+)', url)
    if m:
        return f"https://www.quantalys.it/Fonds/Historique/{m.group(1)}"
    return url


def capture_quantalys_chart(qtl_url: str, force: bool = False) -> object:
    """
    Cattura screenshot del grafico storico Quantalys.
    Cache su file — se esiste già restituisce quello cached.
    """
    if not qtl_url:
        return None

    hist_url = qtl_historique_url(qtl_url)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key      = hashlib.md5(hist_url.encode()).hexdigest()[:14]
    cache_fp = _CACHE_DIR / f"{key}.png"

    if not force and cache_fp.exists() and cache_fp.stat().st_size > 1000:
        return cache_fp.read_bytes()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            # Lancia con args anti-bot detection (come browser reale)
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                ]
            )
            # Contesto con user-agent realistico e lingua italiana
            ctx = browser.new_context(
                viewport={"width": 1400, "height": 780},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="it-IT",
                timezone_id="Europe/Rome",
                extra_http_headers={
                    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
                }
            )
            page = ctx.new_page()

            # Prima visita alla home per acquisire cookie di sessione
            try:
                page.goto("https://www.quantalys.it/", wait_until="domcontentloaded", timeout=15_000)
                page.wait_for_timeout(1_500)
                # Chiudi eventuale cookie banner
                for txt in ["Ok, accetta tutto", "Accetta tutto", "Accetta", "Accept all"]:
                    cb = page.locator(f"button:has-text('{txt}')")
                    if cb.count() > 0:
                        cb.first.click()
                        page.wait_for_timeout(500)
                        break
            except Exception:
                pass

            # Naviga alla pagina Historique
            page.goto(hist_url, wait_until="domcontentloaded", timeout=45_000)

            # Attende rendering amCharts
            try:
                page.wait_for_selector(".qtjs-panel-reloaded-graph svg", timeout=20_000)
            except Exception:
                pass
            page.wait_for_timeout(4_000)

            # Rimuovi overlay/banner se presenti
            try:
                for txt in ["Ok, accetta tutto", "Accetta tutto", "Accept all"]:
                    cb = page.locator(f"button:has-text('{txt}')")
                    if cb.count() > 0:
                        cb.first.click()
                        page.wait_for_timeout(700)
                        break
            except Exception:
                pass

            # Scrolla al pannello principale
            page.evaluate("""() => {
                const el = document.querySelector('.qtjs-panel-reloaded-graph')
                        || document.querySelector('[class*="qtjs-panel"]');
                if (el) el.scrollIntoView({behavior:'instant', block:'start'});
            }""")
            page.wait_for_timeout(500)
            page.mouse.move(10, 10)
            page.wait_for_timeout(800)

            # Calcola bounds del pannello
            clip = page.evaluate("""() => {
                const panel = document.querySelector('.qtjs-panel-reloaded-graph')
                           || document.querySelector('[class*="qtjs-panel"]');
                if (!panel) return null;
                const pr = panel.getBoundingClientRect();
                let toolbarY = null;
                const ctrl = panel.querySelector('select') || panel.querySelector('input[type="text"]');
                if (ctrl) {
                    let el = ctrl;
                    while (el.parentElement && el.parentElement !== panel) el = el.parentElement;
                    toolbarY = Math.round(el.getBoundingClientRect().top);
                }
                return {
                    x: Math.max(0, Math.round(pr.left)),
                    y: Math.max(0, Math.round(pr.top)),
                    width:  Math.round(pr.width),
                    height: toolbarY !== null ? (toolbarY - Math.round(pr.top)) : Math.round(pr.height)
                };
            }""")

            if clip and clip.get("width", 0) > 100 and clip.get("height", 0) > 50:
                png = page.screenshot(clip=clip)
            else:
                # Fallback: screenshot dell'intera viewport
                png = page.screenshot(full_page=False)

            browser.close()

            if png and len(png) > 2000:
                cache_fp.write_bytes(png)
                return png
            return None

    except Exception as e:
        print(f"[QTL capture] Errore per {hist_url}: {e}")
        return None
