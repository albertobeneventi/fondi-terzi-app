# -*- coding: utf-8 -*-
"""
Rendering tabella analisi portafoglio — stile Azimut Portfolio Analyzer.
Colonne: Fondo | Peso | % Az. | % Obb. | Cat. FIDA | FIDArating | Quantalys
"""
import re
import streamlit as st
import pandas as pd
from .config import COL

# ── CSS costanti ──────────────────────────────────────────────────────────────
_TH = ("background:#0D1B2A;color:white;font-size:12px;font-weight:600;"
       "padding:8px 10px;border:none;")
_TC = ("font-size:12px;padding:7px 10px;border-bottom:1px solid #F1F5F9;"
       "vertical-align:middle;")

_FIDA_COL = {5: "#166534", 4: "#166534", 3: "#166534", 2: "#64748B", 1: "#64748B"}
_FIDA_BG  = {5: "#166534", 4: "#15803d", 3: "#16a34a"}

# Approssimazione % azionario/obbligazionario per bucket
_BUCKET_AZ = {
    "Azionari":             (1.00, 0.00),
    "Obbligazionari":       (0.00, 1.00),
    "Bilanciati/Flessibili":(0.50, 0.50),
    "Altro":                (0.30, 0.70),
}


def _fida_badge(rating) -> str:
    try:
        fr = int(float(rating))
        bg = _FIDA_BG.get(fr)
        col = _FIDA_COL.get(fr, "#64748B")
        return (f"<span style='background:{bg};color:#fff;padding:2px 8px;"
                f"border-radius:4px;font-weight:700;'>{fr}</span>"
                if bg else
                f"<span style='color:{col};font-weight:700;'>{fr}</span>")
    except Exception:
        return "<span style='color:#94A3B8;'>—</span>"


def _qtl_stars(url: str) -> str:
    """Link Quantalys come piccolo badge cliccabile."""
    if not url or str(url).lower() in ("nan", "none", ""):
        return "<span style='color:#94A3B8;'>—</span>"
    return (f"<a href='{url}' target='_blank' style='color:#2E86AB;"
            f"font-size:11px;text-decoration:none;'>📊 Quantalys</a>")


def _fund_link(nome: str, fd_url: str) -> str:
    """Nome fondo come hyperlink fondidoc (o solo testo se URL mancante)."""
    display = nome[:55] + ("…" if len(nome) > 55 else "")
    if fd_url and str(fd_url).lower() not in ("nan", "none", ""):
        return (f"<a href='{fd_url}' target='_blank' "
                f"style='color:#1B4FBB;text-decoration:none;font-weight:500;'>"
                f"{display}</a>")
    return f"<span style='font-weight:500;'>{display}</span>"


def _pct_cell(v, color="#1E293B") -> str:
    if v is None or (isinstance(v, float) and str(v) == "nan"):
        return "—"
    try:
        return f"{float(v)*100:.1f}%"
    except Exception:
        return "—"


def _perf_cell(v) -> str:
    if v is None or (isinstance(v, float) and str(v) == "nan"):
        return "<span style='color:#94A3B8;'>—</span>"
    try:
        pv = float(v) * 100
        color = "#059669" if pv >= 0 else "#DC2626"
        sign  = "+" if pv >= 0 else ""
        return f"<span style='color:{color};font-weight:600;'>{sign}{pv:.1f}%</span>"
    except Exception:
        return "—"


def render_portfolio_analysis(funds: list[dict]):
    """
    Renderizza l'analisi del portafoglio con 4 tab:
      Scomposizione Az/Obb | Rendimenti | Rischio | Link
    """
    if not funds:
        st.info("Genera prima un portafoglio.")
        return

    tab_scomp, tab_rend, tab_risk, tab_links = st.tabs([
        "📊 Scomposizione Az/Obb",
        "📈 Rendimenti",
        "⚡ Rischio",
        "🔗 FondiDoc · Quantalys",
    ])

    # ── Prepara dati ──────────────────────────────────────────────────────────
    total_peso = sum(f.get("peso", 0) for f in funds) or 1

    # Medie portafoglio ponderate
    def _wtd(key):
        vals = [(f.get(key), f.get("peso", 0)) for f in funds
                if f.get(key) and str(f.get(key, "")) not in ("nan","None","")]
        tot_w = sum(w for _, w in vals)
        if tot_w == 0: return None
        try:
            return sum(float(v) * w for v, w in vals) / tot_w
        except Exception:
            return None

    w_az  = sum(f.get("peso",0) * _BUCKET_AZ.get(f.get("bucket","Altro"),(0.5,0.5))[0]
                for f in funds) / total_peso
    w_ob  = sum(f.get("peso",0) * _BUCKET_AZ.get(f.get("bucket","Altro"),(0.5,0.5))[1]
                for f in funds) / total_peso

    # ── TAB 1: SCOMPOSIZIONE ──────────────────────────────────────────────────
    with tab_scomp:
        hdr = (
            f"<tr>"
            f"<th style='{_TH}text-align:left;'>Fondo / ISIN</th>"
            f"<th style='{_TH}text-align:center;'>Peso</th>"
            f"<th style='{_TH}text-align:center;'>% Az.</th>"
            f"<th style='{_TH}text-align:center;'>% Obb.</th>"
            f"<th style='{_TH}text-align:left;'>Cat. FIDA</th>"
            f"<th style='{_TH}text-align:center;'>FIDArating</th>"
            f"<th style='{_TH}text-align:center;'>Quantalys</th>"
            f"</tr>"
        )
        body = ""
        for i, f in enumerate(funds):
            az_p, ob_p = _BUCKET_AZ.get(f.get("bucket","Altro"), (0.5, 0.5))
            globe = "🌍 " if f.get("is_global") else ""
            bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
            isin = f.get("ISIN","")
            nome_cell = (f"{globe}{_fund_link(f.get('nome',''), f.get('url_fondidoc',''))}"
                        f"<br/><span style='font-size:10px;color:#94A3B8;'>{isin}</span>")
            body += (
                f"<tr style='background:{bg};'>"
                f"<td style='{_TC}'>{nome_cell}</td>"
                f"<td style='{_TC}text-align:center;color:#1B4FBB;font-weight:600;'>{f.get('peso',0):.1f}%</td>"
                f"<td style='{_TC}text-align:center;'>{az_p*100:.0f}%</td>"
                f"<td style='{_TC}text-align:center;'>{ob_p*100:.0f}%</td>"
                f"<td style='{_TC}color:#64748B;font-size:11px;'>{f.get('classif','—')[:40]}</td>"
                f"<td style='{_TC}text-align:center;'>{_fida_badge(f.get('rating'))}</td>"
                f"<td style='{_TC}text-align:center;'>{_qtl_stars(f.get('url_quantalys',''))}</td>"
                f"</tr>"
            )
        # Riga portafoglio
        body = (
            f"<tr style='background:#0D1B2A;color:white;font-weight:700;'>"
            f"<td style='padding:8px 10px;'>◆ PORTAFOGLIO</td>"
            f"<td style='padding:8px 10px;text-align:center;'>100%</td>"
            f"<td style='padding:8px 10px;text-align:center;'>{w_az*100:.1f}%</td>"
            f"<td style='padding:8px 10px;text-align:center;'>{w_ob*100:.1f}%</td>"
            f"<td style='padding:8px 10px;'></td><td style='padding:8px 10px;'></td><td></td>"
            f"</tr>"
        ) + body

        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-family:Arial,sans-serif;'>"
            f"<thead>{hdr}</thead><tbody>{body}</tbody></table>",
            unsafe_allow_html=True
        )

    # ── TAB 2: RENDIMENTI ─────────────────────────────────────────────────────
    with tab_rend:
        hdr2 = (
            f"<tr>"
            f"<th style='{_TH}text-align:left;'>Fondo</th>"
            f"<th style='{_TH}text-align:center;'>Peso</th>"
            f"<th style='{_TH}text-align:center;'>YTD</th>"
            f"<th style='{_TH}text-align:center;'>1 Anno</th>"
            f"<th style='{_TH}text-align:center;'>3 Anni</th>"
            f"<th style='{_TH}text-align:center;'>2024</th>"
            f"<th style='{_TH}text-align:center;'>2023</th>"
            f"<th style='{_TH}text-align:center;'>2022</th>"
            f"</tr>"
        )
        body2 = ""
        for i, f in enumerate(funds):
            bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
            body2 += (
                f"<tr style='background:{bg};'>"
                f"<td style='{_TC}'>{_fund_link(f.get('nome',''), f.get('url_fondidoc',''))}</td>"
                f"<td style='{_TC}text-align:center;color:#1B4FBB;font-weight:600;'>{f.get('peso',0):.1f}%</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('perf_ytd'))}</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('perf_1y'))}</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('perf_3y'))}</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('perf_2024'))}</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('perf_2023'))}</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('perf_2022'))}</td>"
                f"</tr>"
            )
        # Medie portafoglio
        avgs = [_wtd(k) for k in ["perf_ytd","perf_1y","perf_3y","perf_2024","perf_2023","perf_2022"]]
        avg_row = "".join(f"<td style='padding:8px 10px;text-align:center;'>{_perf_cell(v)}</td>"
                          for v in avgs)
        body2 = (
            f"<tr style='background:#0D1B2A;color:white;font-weight:700;'>"
            f"<td style='padding:8px 10px;'>◆ PORTAFOGLIO</td>"
            f"<td style='padding:8px 10px;text-align:center;'>100%</td>"
            f"{avg_row}</tr>"
        ) + body2
        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-family:Arial,sans-serif;'>"
            f"<thead>{hdr2}</thead><tbody>{body2}</tbody></table>",
            unsafe_allow_html=True
        )

    # ── TAB 3: RISCHIO ────────────────────────────────────────────────────────
    with tab_risk:
        hdr3 = (
            f"<tr>"
            f"<th style='{_TH}text-align:left;'>Fondo</th>"
            f"<th style='{_TH}text-align:center;'>Peso</th>"
            f"<th style='{_TH}text-align:center;'>Volatilità 1Y</th>"
            f"<th style='{_TH}text-align:center;'>FIDArating</th>"
            f"<th style='{_TH}text-align:center;'>Acc./Distr.</th>"
            f"<th style='{_TH}text-align:center;'>Retrocessione</th>"
            f"</tr>"
        )
        body3 = ""
        for i, f in enumerate(funds):
            bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
            body3 += (
                f"<tr style='background:{bg};'>"
                f"<td style='{_TC}'>{_fund_link(f.get('nome',''), f.get('url_fondidoc',''))}</td>"
                f"<td style='{_TC}text-align:center;color:#1B4FBB;font-weight:600;'>{f.get('peso',0):.1f}%</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('volatilita'))}</td>"
                f"<td style='{_TC}text-align:center;'>{_fida_badge(f.get('rating'))}</td>"
                f"<td style='{_TC}text-align:center;color:#64748B;font-size:11px;'>{f.get('acc_dist','—')}</td>"
                f"<td style='{_TC}text-align:center;'>{_perf_cell(f.get('retro'))}</td>"
                f"</tr>"
            )
        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-family:Arial,sans-serif;'>"
            f"<thead>{hdr3}</thead><tbody>{body3}</tbody></table>",
            unsafe_allow_html=True
        )

    # ── TAB 4: LINK ───────────────────────────────────────────────────────────
    with tab_links:
        for f in funds:
            fd  = f.get("url_fondidoc", "")
            qly = f.get("url_quantalys", "")
            c1, c2, c3 = st.columns([4, 2, 2])
            c1.write(f.get("nome","")[:60])
            if fd and str(fd).lower() not in ("nan","none",""):
                c2.markdown(f"[📄 FondiDoc]({fd})")
            else:
                c2.write("—")
            if qly and str(qly).lower() not in ("nan","none",""):
                c3.markdown(f"[📊 Quantalys]({qly})")
            else:
                c3.write("—")
