# -*- coding: utf-8 -*-
"""
App Fondi Società Terze
Motore di ricerca e analisi fondi con filtri per rating, classificazione,
retrocessione. Stampa scheda PDF per fondo con link fondidoc e Quantalys.
"""
import datetime
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from modules.config import (
    COL, PCT_COLS, COLOR_PRIMARY, COLOR_ACCENT,
    COLOR_BG_LIGHT, COLOR_STAR_ON, COLOR_POS, COLOR_NEG, COLOR_NEUTRAL
)
from modules.data_loader import load_data
from modules.filters import render_filters
from modules.pdf_generator import generate_fund_pdf
from modules.portfolio_manager import (
    SCENARIOS, suggest_portfolio, save_portfolio,
    load_portfolios, delete_portfolio, classify_bucket,
    reload_scenarios, MONTHLY_FILES_DIR, _GP_CACHE_FILE
)
from modules.pdf_portfolio import generate_portfolio_pdf

# ── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fondi Società Terze",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── STILE GLOBALE ────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  [data-testid="stSidebar"] {{ background: {COLOR_BG_LIGHT}; }}
  .fund-card {{
      background: white;
      border-radius: 8px;
      border-left: 4px solid {COLOR_PRIMARY};
      padding: 12px 16px;
      margin-bottom: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .metric-chip {{
      display:inline-block;
      padding:2px 8px;
      border-radius:12px;
      font-size:12px;
      font-weight:600;
      margin-right:4px;
  }}
  .pos {{ background:#D1FAE5; color:#065F46; }}
  .neg {{ background:#FEE2E2; color:#991B1B; }}
  .neutral {{ background:#F3F4F6; color:#374151; }}
  .star-on  {{ color:{COLOR_STAR_ON}; }}
  .star-off {{ color:#D1D5DB; }}
  div[data-testid="metric-container"] {{
      background: white;
      border-radius: 8px;
      padding: 10px 14px;
      border: 1px solid #E5E7EB;
  }}
</style>
""", unsafe_allow_html=True)


# ── HELPERS ──────────────────────────────────────────────────────────────────
def fmt_pct(val, decimals=2):
    if pd.isna(val):
        return "—"
    return f"{val*100:.{decimals}f}%"


def stars_html(rating):
    try:
        n = int(float(rating))
    except Exception:
        return '<span style="color:#9CA3AF">—</span>'
    on  = f'<span class="star-on">★</span>'
    off = f'<span class="star-off">☆</span>'
    return on * n + off * (5 - n)


def perf_chip(val):
    if pd.isna(val):
        return '<span class="metric-chip neutral">—</span>'
    pct = val * 100
    cls = "pos" if pct >= 0 else "neg"
    sign = "+" if pct >= 0 else ""
    return f'<span class="metric-chip {cls}">{sign}{pct:.1f}%</span>'


# ── CARICAMENTO DATI ─────────────────────────────────────────────────────────
df_all = load_data()

# ── NAVIGAZIONE TAB ──────────────────────────────────────────────────────────
tab_ricerca, tab_portafogli, tab_update = st.tabs(["🔍 Ricerca", "📁 Portafogli", "⚙️ Aggiornamento"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: PORTAFOGLI
# ══════════════════════════════════════════════════════════════════════════════
with tab_portafogli:
    st.markdown(f"""
        <div style='background:{COLOR_PRIMARY};padding:16px 20px;border-radius:10px;margin-bottom:20px;'>
            <h2 style='color:white;margin:0;font-size:22px;'>📁 Portafogli</h2>
            <p style='color:#CBD5E0;margin:4px 0 0;font-size:13px;'>
                Costruisci e salva portafogli basati sugli scenari Azimut Global Perspectives Q2 2026
            </p>
        </div>
    """, unsafe_allow_html=True)

    ptab1, ptab2 = st.tabs(["🆕 Costruisci portafoglio", "💾 I miei portafogli"])

    # ── TAB: Costruisci ───────────────────────────────────────────────────────
    with ptab1:
        c1, c2, c3 = st.columns([2, 1, 1])

        with c1:
            scenario_sel = st.selectbox(
                "Scenario macro (Global Perspectives Q2 2026)",
                options=list(SCENARIOS.keys()),
                key="ptf_scenario"
            )
        with c2:
            min_rating = st.selectbox(
                "Rating FIDA minimo",
                options=[0, 1, 2, 3, 4, 5],
                index=2,   # default: 3 stelle
                format_func=lambda x: "Tutti" if x == 0 else "★" * x + "☆" * (5 - x),
                key="ptf_min_rating"
            )
        with c3:
            sort_by = st.selectbox(
                "Ordina fondi per",
                options=["retro", "rating", "perf_1y"],
                format_func=lambda x: {
                    "retro": "Retrocessione ↓",
                    "rating": "Rating FIDA ↓",
                    "perf_1y": "Perf. 1 anno ↓"
                }[x],
                key="ptf_sort"
            )

        n_per = st.slider("Fondi per categoria", min_value=1, max_value=6, value=3, key="ptf_n")

        sc = SCENARIOS[scenario_sel]
        st.info(f"**{scenario_sel}** — {sc['descrizione']}")

        # Pesi scenario (compatibile con GP cache e valori hardcoded)
        d = sc.get("dettaglio", {})
        wc = st.columns(3)
        wc[0].metric("Equity %",          f"{d.get('Equity %', '—')}{'%' if d.get('Equity %') else ''}")
        wc[1].metric("Bond %",            f"{d.get('Bond %', '—')}{'%' if d.get('Bond %') else ''}")
        wc[2].metric("Private Markets %", f"{d.get('Private Markets %', '30')}% (esclusi)")

        st.divider()

        if st.button("🎯 Genera portafoglio suggerito", key="btn_gen_ptf", type="primary"):
            funds = suggest_portfolio(df_all, scenario_sel, min_rating, n_per, sort_by)
            if not funds:
                st.warning("Nessun fondo trovato con i criteri selezionati. Abbassa il rating minimo.")
            else:
                st.session_state["ptf_funds"] = funds
                st.session_state["ptf_scenario_name"] = scenario_sel
                st.success(f"Portafoglio generato: {len(funds)} fondi")

        # Mostra portafoglio generato
        if "ptf_funds" in st.session_state and st.session_state["ptf_funds"]:
            funds = st.session_state["ptf_funds"]
            total_peso = sum(f["peso"] for f in funds)
            st.markdown(f"#### Composizione suggerita (totale: {total_peso:.1f}%)")

            # Raggruppa per bucket
            buckets = {}
            for f in funds:
                buckets.setdefault(f["bucket"], []).append(f)

            edited_funds = []
            for bucket, bfunds in buckets.items():
                bucket_peso = sum(f["peso"] for f in bfunds)
                st.markdown(f"**{bucket}** — {bucket_peso:.1f}%")
                for idx, f in enumerate(bfunds):
                    fc1, fc2, fc3, fc4, fc5 = st.columns([4, 1, 1, 1, 1])
                    fc1.write(f['nome'][:55])
                    rating_str = "★" * int(f["rating"]) if f["rating"] and not pd.isna(f["rating"]) else "—"
                    fc2.write(rating_str)
                    fc3.write(f"{f['retro']*100:.2f}%" if f["retro"] and not pd.isna(f["retro"]) else "—")
                    new_peso = fc4.number_input(
                        "Peso%", value=float(f["peso"]), min_value=0.0, max_value=100.0,
                        step=0.5, label_visibility="collapsed",
                        key=f"peso_{f['ISIN']}_{idx}"
                    )
                    if fc5.checkbox("✓", value=True, key=f"chk_{f['ISIN']}_{idx}"):
                        edited_funds.append({**f, "peso": new_peso})

            st.divider()

            # ── Visualizzazione: torta + tabella ────────────────────────────
            if edited_funds:
                # Torta per bucket
                bucket_map: dict = {}
                for f in edited_funds:
                    b = f.get("bucket", "Altro")
                    bucket_map[b] = bucket_map.get(b, 0) + f.get("peso", 0)

                _BCOLORS = {
                    "Azionari": "#1B4FBB", "Obbligazionari": "#2D9D78",
                    "Bilanciati/Flessibili": "#C9A84C", "Altro": "#94A3B8"
                }
                fig_pie = go.Figure(go.Pie(
                    labels=list(bucket_map.keys()),
                    values=list(bucket_map.values()),
                    marker_colors=[_BCOLORS.get(b, "#94A3B8") for b in bucket_map],
                    hole=0.35,
                    textinfo="label+percent",
                ))
                fig_pie.update_layout(
                    height=320, margin=dict(t=20, b=10, l=10, r=10),
                    showlegend=True, legend=dict(orientation="h", y=-0.15)
                )

                vc1, vc2 = st.columns([2, 3])
                vc1.plotly_chart(fig_pie, use_container_width=True)

                # Tabella fondi
                tbl_data = []
                for f in sorted(edited_funds, key=lambda x: (x.get("bucket",""), -x.get("peso",0))):
                    r   = f.get("rating")
                    ret = f.get("retro")
                    p1  = f.get("perf_1y")
                    tbl_data.append({
                        "Fondo": f.get("nome","")[:45],
                        "Bucket": f.get("bucket","")[:15],
                        "Peso %": f"{f.get('peso',0):.1f}%",
                        "Rating": "★" * int(r) if r and str(r) not in ("nan","") else "—",
                        "Retro.": f"{ret*100:.2f}%" if ret and str(ret) not in ("nan","") else "—",
                        "Perf 1Y": f"{p1*100:.1f}%" if p1 and str(p1) not in ("nan","") else "—",
                    })
                vc2.dataframe(tbl_data, use_container_width=True, hide_index=True)

            st.divider()
            rc1, rc2 = st.columns([3, 2])
            nome_ptf = rc1.text_input("💾 Nome del portafoglio", placeholder="es. Mio portafoglio base Q2 2026", key="ptf_nome")
            incl_cards = rc2.checkbox("Includi schede fondo nel PDF", value=True, key="ptf_incl_cards")

            bc1, bc2 = st.columns(2)
            if bc1.button("Salva portafoglio", key="btn_save_ptf") and nome_ptf:
                save_portfolio(nome_ptf, scenario_sel, min_rating, edited_funds)
                st.success(f"Portafoglio '{nome_ptf}' salvato!")
                del st.session_state["ptf_funds"]

            if bc2.button("🖨️ Stampa PDF portafoglio", key="btn_pdf_ptf") and edited_funds:
                with st.spinner("Generazione PDF portafoglio..."):
                    try:
                        pdf_bytes = generate_portfolio_pdf(
                            nome_ptf or "Portafoglio",
                            scenario_sel,
                            edited_funds,
                            include_fund_cards=incl_cards,
                        )
                        bc2.download_button(
                            "⬇️ Scarica PDF",
                            data=pdf_bytes,
                            file_name=f"portafoglio_{datetime.date.today()}.pdf",
                            mime="application/pdf",
                            key="dl_ptf_pdf"
                        )
                    except Exception as e:
                        st.error(f"Errore PDF: {e}")

    # ── TAB: I miei portafogli ────────────────────────────────────────────────
    with ptab2:
        portfolios = load_portfolios()
        if not portfolios:
            st.info("Nessun portafoglio salvato. Costruiscine uno nella tab precedente.")
        else:
            for nome, data in sorted(portfolios.items(), reverse=True):
                with st.expander(f"**{nome}** — {data.get('scenario','')} | {data.get('created_at','')}", expanded=False):
                    funds = data.get("funds", [])
                    total = sum(f.get("peso", 0) for f in funds)
                    st.caption(f"Rating minimo: {'★' * data.get('min_rating',0)} | {len(funds)} fondi | Totale peso: {total:.1f}%")

                    for f in funds:
                        lc1, lc2, lc3, lc4 = st.columns([4, 1, 1, 1])
                        lc1.write(f.get("nome", "")[:55])
                        lc2.write(f.get("bucket", "")[:15])
                        lc3.write(f"{f['peso']:.1f}%")
                        fd_url = f.get("url_fondidoc", "")
                        if fd_url and fd_url.lower() not in ("nan", "none", ""):
                            lc4.markdown(f"[FondiDoc]({fd_url})")

                    if st.button("🗑️ Elimina", key=f"del_{nome}"):
                        delete_portfolio(nome)
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: RICERCA FONDI
# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: AGGIORNAMENTO DATI
# ══════════════════════════════════════════════════════════════════════════════
with tab_update:
    import subprocess as _sp
    from pathlib import Path as _Path

    st.markdown(f"""
        <div style='background:{COLOR_PRIMARY};padding:16px 20px;border-radius:10px;margin-bottom:20px;'>
            <h2 style='color:white;margin:0;font-size:22px;'>⚙️ Aggiornamento Dati</h2>
        </div>
    """, unsafe_allow_html=True)

    # ── Sezione 1: Catalogo PDF ───────────────────────────────────────────────
    st.markdown("### 📄 Catalogo Fondi (PDF mensile)")
    st.info(
        f"Deposita il PDF aggiornato del catalogo nella cartella:\n\n"
        f"**`{MONTHLY_FILES_DIR}`**\n\n"
        "Il file deve contenere 'CATALOGO' nel nome (es. `CATALOGO AFB X INTRANET 31.05.2026.pdf`).\n"
        "Poi clicca **Aggiorna da PDF** per aggiungere i nuovi fondi e rimuovere quelli non più presenti."
    )

    # Lista PDF disponibili nella cartella monthly
    pdf_files = sorted([f for f in MONTHLY_FILES_DIR.glob("*.pdf")
                        if "catalogo" in f.name.lower() or "afb" in f.name.lower()],
                       reverse=True)

    if pdf_files:
        sel_pdf = st.selectbox(
            "PDF disponibili in cartella", [f.name for f in pdf_files], key="sel_catalog_pdf"
        )
        if st.button("🔄 Aggiorna da PDF catalogo", key="btn_update_pdf", type="primary"):
            pdf_path = str(MONTHLY_FILES_DIR / sel_pdf)
            with st.spinner(f"Elaborazione {sel_pdf}..."):
                result = _sp.run(
                    ["C:/Users/benev/AppData/Local/Programs/Python/Python312/python.exe",
                     "C:/Users/benev/update_from_pdf.py"],
                    capture_output=True, text=True, encoding="utf-8",
                    env={**__import__("os").environ, "CATALOG_PDF": pdf_path}
                )
            if result.returncode == 0:
                st.success("Catalogo aggiornato. Riavvia l'app per caricare i nuovi dati.")
                st.code(result.stdout[-1000:])
            else:
                st.error(f"Errore: {result.stderr[-500:]}")
    else:
        st.warning(f"Nessun PDF trovato in `{MONTHLY_FILES_DIR}`. Copia lì il file del catalogo.")

    st.divider()

    # ── Sezione 2: Global Perspectives ──────────────────────────────────────────
    st.markdown("### 📊 Global Perspectives (scenari portafoglio)")
    if _GP_CACHE_FILE.exists():
        import json as _json
        gp_meta = _json.loads(_GP_CACHE_FILE.read_text(encoding="utf-8-sig"))
        st.success(
            f"✅ GP caricato dall'app Azimut: **{gp_meta.get('filename','')}** "
            f"(aggiornato: {gp_meta.get('last_updated','')})"
        )
        if st.button("🔃 Ricarica scenari dal GP", key="btn_reload_gp"):
            new_sc = reload_scenarios()
            st.success(f"Scenari aggiornati: {list(new_sc.keys())}")
            st.rerun()
    else:
        st.warning(
            "Global Perspectives non trovato. Carica il PDF nell'app **Azimut Portfolio Analyzer** — "
            "gli scenari verranno automaticamente sincronizzati qui."
        )

    st.divider()

    # ── Sezione 3: Aggiornamento mensile manuale ─────────────────────────────
    st.markdown("### 🗓️ Aggiornamento performance manuale")
    st.info(
        "L'aggiornamento automatico è pianificato ogni **5 del mese alle 02:00** "
        "tramite Windows Task Scheduler (aggiorna performance, volatilità e rating da fondidoc).\n\n"
        "Puoi forzarlo ora cliccando il pulsante (richiede ~8 ore in background)."
    )
    if st.button("▶️ Avvia aggiornamento performance ora", key="btn_manual_update"):
        _sp.Popen([
            "C:/Users/benev/AppData/Local/Programs/Python/Python312/python.exe",
            "C:/Users/benev/monthly_update.py"
        ])
        st.success("Aggiornamento avviato in background. Controlla `C:\\Users\\benev\\monthly_update.log`.")

# ══════════════════════════════════════════════════════════════════════════════
with tab_ricerca:

# ── SIDEBAR: FILTRI ──────────────────────────────────────────────────────────
    df = render_filters(df_all)

# ── HEADER ───────────────────────────────────────────────────────────────────
    st.markdown(f"""
        <div style='background:{COLOR_PRIMARY};padding:20px 24px;border-radius:10px;margin-bottom:20px;'>
            <h1 style='color:white;margin:0;font-size:26px;'>📊 Fondi Società Terze</h1>
            <p style='color:#CBD5E0;margin:4px 0 0;font-size:14px;'>
                Analisi e selezione fondi — {len(df):,} fondi visualizzati su {len(df_all):,}
            </p>
        </div>
    """, unsafe_allow_html=True)

    # ── KPI SUMMARY ──────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Fondi", f"{len(df):,}")
    with col2:
        avg_retro = df[COL["retro"]].mean()
        st.metric("Retro. media", fmt_pct(avg_retro) if not pd.isna(avg_retro) else "—")
    with col3:
        avg_perf = df[COL["perf_1y"]].mean()
        st.metric("Perf. 1Y media", fmt_pct(avg_perf) if not pd.isna(avg_perf) else "—")
    with col4:
        n_rated = df[COL["rating"]].notna().sum()
        avg_rat = df[COL["rating"]].mean()
        st.metric("Rating medio", f"{avg_rat:.1f}★" if not pd.isna(avg_rat) else "—",
                  f"{n_rated:,} con rating")
    with col5:
        n_fondidoc = df[COL["url_fondidoc"]].notna().sum()
        st.metric("Link FondiDoc", f"{n_fondidoc:,}")

    st.divider()

    # ── TABELLA FONDI ─────────────────────────────────────────────────────────
    st.markdown(f"#### Risultati ({len(df):,} fondi)")

    # Ordina default per retrocessione desc
    sort_col = st.selectbox(
        "Ordina per",
        options=["RETROCESSIONE BANCA", "PERF. 1 ANNO", "PERF. 3 ANNI",
                 "RATING", "VOLATILITA' (1 anno)", "COMMISSIONI DI GESTIONE",
                 "DESCRIZIONE FONDO"],
        index=0, key="sort_col"
    )
    sort_asc = st.checkbox("Ordine crescente", value=False, key="sort_asc")

    sort_c = sort_col.strip()
    if sort_c in df.columns:
        df_sorted = df.sort_values(sort_c, ascending=sort_asc, na_position="last")
    else:
        df_sorted = df

    # Paginazione
    PAGE_SIZE = 50
    total_pages = max(1, (len(df_sorted) - 1) // PAGE_SIZE + 1)
    page = st.number_input("Pagina", min_value=1, max_value=total_pages,
                           value=1, key="page_num")
    start = (page - 1) * PAGE_SIZE
    df_page = df_sorted.iloc[start:start + PAGE_SIZE]

    st.caption(f"Pagina {page}/{total_pages} — righe {start+1}–{min(start+PAGE_SIZE, len(df_sorted))}")

    # ── CARD PER FONDO ────────────────────────────────────────────────────────
    for _, row in df_page.iterrows():
        nome  = str(row.get(COL["nome"], "")).strip()[:80]
        house = str(row.get(COL["house"], "")).strip()
        isin  = str(row.get(COL["isin"], "")).strip()
        classif = str(row.get(COL["classif"], "")).strip()
        acc_dist = str(row.get(COL["acc_dist"], "")).strip()
        retro = row.get(COL["retro"])
        perf1 = row.get(COL["perf_1y"])
        perf3 = row.get(COL["perf_3y"])
        vol   = row.get(COL["volatilita"])
        rating = row.get(COL["rating"])
        fd_url  = str(row.get(COL["url_fondidoc"], "") or "").strip()
        qly_url = str(row.get(COL["url_quantalys"], "") or "").strip()

        with st.expander(f"**{nome}** — {house} | ISIN: {isin}", expanded=False):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])

            with c1:
                st.markdown("**Classificazione**")
                st.write(classif if classif and classif.lower() not in ("nan","") else "—")
                st.markdown("**Acc./Distr.**")
                st.write(acc_dist if acc_dist and acc_dist.lower() not in ("nan","") else "—")

            with c2:
                st.markdown("**Rating FIDA**")
                st.markdown(stars_html(rating), unsafe_allow_html=True)
                st.markdown("**Retrocessione**")
                st.markdown(perf_chip(retro), unsafe_allow_html=True)

            with c3:
                st.markdown("**Perf. 1 anno**")
                st.markdown(perf_chip(perf1), unsafe_allow_html=True)
                st.markdown("**Perf. 3 anni**")
                st.markdown(perf_chip(perf3), unsafe_allow_html=True)

            with c4:
                st.markdown("**Volatilità 1Y**")
                st.write(fmt_pct(vol) if not pd.isna(vol) else "—")
                st.markdown("**Comm. gestione**")
                st.write(fmt_pct(row.get(COL["comm_gest"])))

            # Link
            link_cols = st.columns(3)
            if fd_url and fd_url.lower() not in ("nan",""):
                link_cols[0].markdown(f"[📄 FondiDoc]({fd_url})")
            if qly_url and qly_url.lower() not in ("nan",""):
                link_cols[1].markdown(f"[📊 Quantalys]({qly_url})")

            # PDF
            pdf_row = st.columns([2, 1])
            include_qtl = pdf_row[1].checkbox(
                "📊 Grafico Quantalys", value=False, key=f"qtl_{isin}",
                help="Aggiunge screenshot grafico storico Quantalys (~20s)"
            )
            if pdf_row[0].button("🖨️ Stampa PDF", key=f"pdf_{isin}"):
                spinner_msg = "Generazione PDF (con grafico Quantalys ~20s)..." if include_qtl else "Generazione PDF..."
                with st.spinner(spinner_msg):
                    try:
                        pdf_bytes = generate_fund_pdf(row.to_dict(), include_quantalys=include_qtl)
                        pdf_row[0].download_button(
                            label="⬇️ Scarica PDF",
                            data=pdf_bytes,
                            file_name=f"scheda_{isin}.pdf",
                            mime="application/pdf",
                            key=f"dl_{isin}"
                        )
                    except Exception as e:
                        st.error(f"Errore PDF: {e}")
