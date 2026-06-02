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
    SCENARIOS, suggest_portfolio, suggest_portfolio_dual, save_portfolio,
    load_portfolios, delete_portfolio, classify_bucket,
    reload_scenarios, MONTHLY_FILES_DIR, _GP_CACHE_FILE,
    load_scenarios_from_global_view
)
from modules.portfolio_analysis import render_portfolio_analysis
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

# ── FILTRI SIDEBAR (disponibili in tutti i tab) ──────────────────────────────
df = render_filters(df_all)

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

        # ── Nota editoriale ──────────────────────────────────────────────────
        with st.expander("📋 Nota metodologica — Criteri di selezione", expanded=False):
            st.markdown(f"""
**Nota redazionale** · Aggiornamento {datetime.date.today().strftime('%B %Y')}

---

**Universo eleggibile**
- Fondi con **Collocabile = SI** e **Rating FIDA ≥ minimo** selezionato
- Solo fondi che rispettano i filtri attivi nella sidebar

**Score qualità (Portafoglio 1)**

Il punteggio qualità è costruito su tre componenti con pesi differenziati:
- **Performance 3Y annualizzata (50%)** — più predittiva del breve periodo
- **Sortino proxy: Perf3Y / Volatilità (30%)** — premia chi gestisce bene il downside
- **Performance 1Y recente (20%)** — segnale di momentum

Il punteggio viene *amplificato* dal Rating FIDA (ogni stella aggiunge un moltiplicatore) e *dimezzato* per fondi con performance 3Y negativa (floor di qualità).

**Bonus/malus di consistenza**: premia i fondi senza anni fortemente negativi (< -10%), penalizza chi ne ha avuti.

**A parità di score qualità**: vince il fondo con retrocessione più alta (interesse del distributore compatibile con la qualità).

---

**Vincoli di diversificazione**
- **Max 1 fondo per casa di gestione** per bucket (evita concentrazione)
- **Max 1 fondo per sottoclassificazione FIDA** (evita duplicati tematici)
- **Max 1 fondo per radice strategia** (evita ACC e MINC della stessa strategia)
- **Max 2/3 dalla stessa macro-area geografica** (US / Europe / Emerging / Japan / Global)
- **Almeno 1 fondo globale/internazionale** per bucket

---

**Quota distribuzione**: configurabile con slider (default 50% max)

---

**Portafoglio 2 — Retrocessione**: stessi vincoli, criterio primario = retrocessione banca, qualità come tiebreaker.

---

**Fonte scenari**: derivati da Azimut Global View / Global Perspectives o da profili di rischio standard (PRUDENTE / BILANCIATO / DINAMICO).
            """)

        # ── Upload Global View PDF ────────────────────────────────────────────
        with st.expander("📡 Carica Global View per aggiornare lo scenario", expanded=False):
            gv_upload = st.file_uploader("Carica PDF Global View (settimanale)",
                                         type=["pdf"], key="gv_upload")
            if gv_upload:
                import tempfile, os as _os
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(gv_upload.read())
                    tmp_path = tmp.name
                try:
                    gv_scenario = load_scenarios_from_global_view(tmp_path)
                    if gv_scenario:
                        st.session_state["gv_scenario"] = gv_scenario
                        sc_name = list(gv_scenario.keys())[0]
                        sc_data = gv_scenario[sc_name]
                        st.success(f"✅ Scenario caricato: **{sc_name}**")
                        st.caption(sc_data["descrizione"])
                        # Mostra view
                        rv = sc_data.get("raw_views", {})
                        if rv:
                            cols = st.columns(len(rv))
                            _vcolor = {"OVER":"🟢","LIEVE_OVER":"🟡","NEUTRAL":"⚪","LIEVE_UNDER":"🟡","UNDER":"🔴"}
                            for (k, v), col in zip(rv.items(), cols):
                                col.metric(k, _vcolor.get(v,"⚪") + " " + v.replace("_"," ").title())
                    else:
                        st.error("Impossibile parsare il PDF. Assicurati che sia un Global View Azimut.")
                except Exception as e:
                    st.error(f"Errore: {e}")
                finally:
                    try: _os.unlink(tmp_path)
                    except: pass

        # Merge scenari: GP / Global View / default
        _all_scenarios = dict(SCENARIOS)
        if "gv_scenario" in st.session_state:
            _all_scenarios = {**st.session_state["gv_scenario"], **_all_scenarios}

        c1, c2, c3 = st.columns([2, 1, 1])

        with c1:
            _sc_label = "Scenario / Profilo di allocazione"
            scenario_sel = st.selectbox(
                _sc_label,
                options=list(_all_scenarios.keys()),
                key="ptf_scenario"
            )
            # Aggiorna SCENARIOS usato per la generazione
            _active_scenarios = _all_scenarios
        with c2:
            min_rating = st.selectbox(
                "Rating FIDA minimo",
                options=[0, 1, 2, 3, 4, 5],
                index=3,   # default: ★★★
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
        st.caption(
            "ℹ️ **Criteri di selezione**: per ogni categoria (Azionari/Obbligazionari/Bilanciati) "
            "vengono scelti i fondi **collocabili** con rating ≥ minimo, ordinati per il criterio selezionato. "
            "I pesi sono distribuiti equamente tra i fondi della stessa categoria. "
            "Puoi modificare i pesi manualmente prima di salvare."
        )

        # Pesi scenario (compatibile con GP cache e valori hardcoded)
        d = sc.get("dettaglio", {})
        wc = st.columns(3)
        wc[0].metric("Equity %",          f"{d.get('Equity %', '—')}{'%' if d.get('Equity %') else ''}")
        wc[1].metric("Bond %",            f"{d.get('Bond %', '—')}{'%' if d.get('Bond %') else ''}")
        wc[2].metric("Private Markets %", f"{d.get('Private Markets %', '30')}% (esclusi)")

        st.divider()

        sl1, sl2 = st.columns(2)
        dist_pct = sl1.slider(
            "% fondi a distribuzione",
            min_value=0, max_value=100, value=0, step=10,
            format="%d%%",
            help="0% = solo accumulazione | 50% = metà | 100% = solo distribuzione.",
            key="ptf_dist_pct"
        )
        hedge_pct = sl2.slider(
            "% massima fondi hedged (EURHDG/USDHDG...)",
            min_value=0, max_value=100, value=50, step=10,
            format="%d%%",
            help="50% = default (max metà dei fondi può avere copertura valutaria). "
                 "0% = nessun hedged, 100% = nessun limite.",
            key="ptf_hedge_pct"
        )

        if st.button("🎯 Genera portafogli", key="btn_gen_ptf", type="primary"):
            # Usa scenario da _all_scenarios (include Global View se caricato)
            import modules.portfolio_manager as _pm
            _pm.SCENARIOS = _active_scenarios
            ptf_q, ptf_r = suggest_portfolio_dual(df, scenario_sel, min_rating, n_per,
                                                   target_dist_pct=dist_pct/100,
                                                   max_hedge_pct=hedge_pct/100)
            if not ptf_q and not ptf_r:
                st.warning("Nessun fondo trovato. Abbassa il rating minimo o modifica i filtri.")
            else:
                st.session_state["ptf_q"] = ptf_q
                st.session_state["ptf_r"] = ptf_r
                st.session_state["ptf_scenario_name"] = scenario_sel

        def _render_variant(funds: list, suffix: str):
            """Renderizza una variante portafoglio: modifica + analisi + salva + PDF."""
            if not funds:
                st.info("Nessun fondo trovato con i criteri selezionati.")
                return

            # ── Arricchisci fondi ─────────────────────────────────────────────
            isin_to_row = {str(r.get(COL["isin"],"")).strip(): r for _, r in df_all.iterrows()}
            def _enrich(f):
                row = isin_to_row.get(f["ISIN"], {})
                out = dict(f)
                for k, col in [("perf_ytd",COL["perf_ytd"]),("perf_3y",COL["perf_3y"]),
                                ("perf_2024",COL["perf_2024"]),("perf_2023",COL["perf_2023"]),
                                ("perf_2022",COL["perf_2022"]),("volatilita",COL["volatilita"]),
                                ("acc_dist",COL["acc_dist"])]:
                    out[k] = row.get(col)
                return out

            # ── Modifica pesi e sostituzione fondi ────────────────────────────
            with st.expander("✏️ Modifica pesi e sostituisci fondi", expanded=False):
                st.caption("Modifica i pesi, deseleziona fondi da escludere, o sostituisci con un altro fondo dal catalogo.")
                # Indice fondi del catalogo per bucket
                edited = list(st.session_state.get(f"edited_{suffix}", funds))
                new_funds = []
                for idx, f in enumerate(edited):
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 3])
                    isin_disp = f.get("ISIN","")
                    c1.markdown(f"**{f['nome'][:40]}**  \n`{isin_disp}`")
                    new_p = c2.number_input("Peso%", value=float(f.get("peso",0)),
                                            min_value=0.0, max_value=100.0, step=0.5,
                                            label_visibility="collapsed",
                                            key=f"ep_{suffix}_{isin_disp}_{idx}")
                    incl_f = c3.checkbox("✓", value=True, key=f"ei_{suffix}_{isin_disp}_{idx}")
                    # Sostituzione: top 10 per qualità, max 2 per casa, escluso fondo corrente
                    same_bucket = df[
                        df[COL["classif"]].apply(lambda x: classify_bucket(str(x)) == f.get("bucket","")) &
                        (df[COL["collocabile"]].astype(str).str.upper().str.strip() == "SI") &
                        (df[COL["isin"]].astype(str).str.strip() != f["ISIN"])
                    ].copy()
                    # Escludi ISIN già presenti nel portafoglio corrente
                    current_isins = {ff["ISIN"] for ff in edited}
                    same_bucket = same_bucket[~same_bucket[COL["isin"]].astype(str).str.strip().isin(current_isins)]
                    # Calcola quality score e ordina
                    from modules.portfolio_manager import _quality_score as _qs
                    same_bucket["_qscore"] = same_bucket.apply(_qs, axis=1)
                    same_bucket["_house"]  = same_bucket[COL["house"]].astype(str).str.strip().str.upper()
                    same_bucket = same_bucket.sort_values("_qscore", ascending=False)
                    # Prendi top 10 con max 2 per casa
                    top10, house_cnt = [], {}
                    for _, r in same_bucket.iterrows():
                        if len(top10) >= 10: break
                        h = r["_house"]
                        if house_cnt.get(h, 0) >= 2: continue
                        top10.append(r)
                        house_cnt[h] = house_cnt.get(h, 0) + 1
                    opts = ["— nessuna sostituzione —"] + [
                        f"{'★'*int(float(r[COL['rating']])) if r[COL['rating']] and str(r[COL['rating']]) not in ('nan','') else '—'} "
                        f"{str(r[COL['nome']])[:45]} | {r[COL['isin']]}"
                        for r in top10
                    ]
                    sub = c4.selectbox("Sostituisci con", opts, index=0,
                                       key=f"sub_{suffix}_{isin_disp}_{idx}",
                                       label_visibility="collapsed")
                    if incl_f:
                        if sub != "— nessuna sostituzione —":
                            new_isin = sub.split(" | ")[-1].strip()
                            new_row = isin_to_row.get(new_isin, {})
                            repl = {
                                "ISIN": new_isin,
                                "nome": str(new_row.get(COL["nome"],"")),
                                "house": str(new_row.get(COL["house"],"")),
                                "bucket": f.get("bucket",""),
                                "peso": new_p,
                                "rating": new_row.get(COL["rating"]),
                                "retro": new_row.get(COL["retro"]),
                                "perf_1y": new_row.get(COL["perf_1y"]),
                                "classif": str(new_row.get(COL["classif"],"")),
                                "url_fondidoc": str(new_row.get(COL["url_fondidoc"],"") or ""),
                                "url_quantalys": str(new_row.get(COL["url_quantalys"],"") or ""),
                            }
                            new_funds.append(repl)
                        else:
                            new_funds.append({**f, "peso": new_p})
                st.session_state[f"edited_{suffix}"] = new_funds if new_funds else funds
                funds = new_funds if new_funds else funds

            # ── Analisi stile Azimut ──────────────────────────────────────────
            funds_rich = [_enrich(f) for f in funds]
            render_portfolio_analysis(funds_rich)

            st.divider()
            r1, r2 = st.columns([3, 2])
            nome = r1.text_input("💾 Nome portafoglio",
                                 placeholder="es. BASE qualità Q2 2026",
                                 key=f"nome_{suffix}")
            incl = r2.checkbox("Schede fondo nel PDF", value=True, key=f"incl_{suffix}")
            b1, b2 = st.columns(2)
            if b1.button("Salva portafoglio", key=f"save_{suffix}") and nome:
                save_portfolio(nome, scenario_sel, min_rating, funds)
                st.success(f"✅ Salvato: '{nome}'")
            if b2.button("🖨️ Stampa PDF", key=f"pdf_{suffix}") and funds:
                with st.spinner("Generazione PDF..."):
                    try:
                        pdf_bytes = generate_portfolio_pdf(
                            nome or "Portafoglio", scenario_sel, funds_rich,
                            include_fund_cards=incl,
                        )
                        b2.download_button("⬇️ Scarica PDF", data=pdf_bytes,
                                           file_name=f"portafoglio_{datetime.date.today()}.pdf",
                                           mime="application/pdf", key=f"dl_{suffix}")
                    except Exception as e:
                        st.error(f"Errore PDF: {e}")

        # ── Mostra i due portafogli in sotto-tab ─────────────────────────────
        if st.session_state.get("ptf_q") or st.session_state.get("ptf_r"):
            st.divider()
            vtab_q, vtab_r = st.tabs(["🏆 Portafoglio Qualità", "💰 Portafoglio Retrocessione"])
            with vtab_q:
                st.caption("**Criterio**: Rating FIDA + Sharpe → Retrocessione a parità di qualità")
                _render_variant(st.session_state.get("ptf_q", []), "q")
            with vtab_r:
                st.caption("**Criterio**: Retrocessione massima → Qualità come tiebreaker")
                _render_variant(st.session_state.get("ptf_r", []), "r")

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

                    render_portfolio_analysis(funds)

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

    uploaded_pdf = st.file_uploader(
        "Carica il PDF aggiornato del catalogo",
        type=["pdf"],
        help="Il PDF del catalogo AFB mensile (es. CATALOGO AFB X INTRANET 31.05.2026.pdf)",
        key="upload_catalog_pdf"
    )

    if uploaded_pdf:
        import tempfile, os as _os
        st.success(f"File caricato: **{uploaded_pdf.name}** ({uploaded_pdf.size/1024:.0f} KB)")

        if st.button("🔄 Aggiorna fondi dal PDF", key="btn_update_pdf", type="primary"):
            # Salva PDF in temp file e lancia lo script di aggiornamento
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_pdf.read())
                tmp_path = tmp.name

            with st.spinner("Analisi PDF e aggiornamento fondi... (~1 minuto)"):
                # Import diretto per evitare dipendenza da percorsi locali
                try:
                    import fitz, re
                    from modules.data_loader import load_data

                    ISIN_RE   = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')
                    NOT_HOUSE = re.compile(r'^(SI|NO|\d[\d,\.]*|-|$)', re.I)
                    SKIP = {"ASSET MANAGEMENT HOUSE","FONDO/SICAV","ISIN","DESCRIZIONE FONDO",
                            "CLASSE","DIVISA FONDO","COMMISSIONE DI GESTIONE",
                            "COMMISSIONE DI DISTRIBUZIONE","COMMISSIONE TOTALE",
                            "COMMENTI","% BPS *ANNUI CF","Trasferibile","Collocabile",
                            "Azimut Capital Management SGR"}

                    doc = fitz.open(tmp_path)
                    rows = []
                    for pg in range(len(doc)):
                        lines = [l.strip() for l in doc[pg].get_text().split('\n')
                                 if l.strip() and l.strip() not in SKIP]
                        i = 0
                        while i < len(lines):
                            if ISIN_RE.match(lines[i]):
                                isin = lines[i]
                                cands = []
                                j = i-1
                                while j >= max(0,i-6) and len(cands) < 2:
                                    if not NOT_HOUSE.match(lines[j]) and not ISIN_RE.match(lines[j]):
                                        cands.insert(0, lines[j])
                                    j -= 1
                                house = cands[-2] if len(cands)>=2 else (cands[0] if cands else "")
                                sicav = cands[-1] if cands else ""
                                desc   = lines[i+1] if i+1<len(lines) else ""
                                classe = lines[i+2] if i+2<len(lines) else ""
                                divisa = lines[i+3] if i+3<len(lines) else ""
                                bps, trasf, colloc = None,"",""
                                for k in range(i+4, min(i+14,len(lines))):
                                    v = lines[k].strip()
                                    if bps is None and re.match(r'^\d+[,\.]?\d*$',v):
                                        try: bps=float(v.replace(',','.'))
                                        except: pass
                                    if v in ("SI","NO") and not trasf: trasf=v
                                    elif v in ("SI","NO") and trasf and not colloc: colloc=v
                                rows.append({"ISIN":isin,"ASSET MANAGEMENT HOUSE ":house,
                                             "FONDO/SICAV":sicav,"DESCRIZIONE FONDO":desc,
                                             "CLASSE":classe,"DIVISA FONDO         ":divisa,
                                             " % BPS *ANNUI CF ":bps,
                                             "Traferibile":trasf,"Collocabile":colloc})
                            i+=1

                    pdf_df = pd.DataFrame(rows).drop_duplicates(subset="ISIN")
                    pdf_isins = set(pdf_df["ISIN"].astype(str).str.strip())

                    # Leggi Excel corrente
                    xls_path = _Path(__file__).parent / "data" / "fondi.xlsx"
                    sheets   = pd.read_excel(xls_path, sheet_name=None, dtype=str)
                    main     = sheets["tutti quelli trasferibili"]
                    main.columns = [str(c).strip() for c in main.columns]
                    xls_isins = set(main["ISIN"].astype(str).str.strip())

                    rimossi = xls_isins - pdf_isins
                    nuovi   = pdf_isins - xls_isins

                    # Rimuovi vecchi, aggiungi nuovi
                    main = main[main["ISIN"].astype(str).str.strip().isin(pdf_isins)]
                    if nuovi:
                        pdf_new = pdf_df[pdf_df["ISIN"].isin(nuovi)].copy()
                        for col in main.columns:
                            if col not in pdf_new.columns: pdf_new[col] = None
                        pdf_new = pdf_new[[c for c in main.columns if c in pdf_new.columns]]
                        main = pd.concat([main, pdf_new], ignore_index=True)

                    sheets["tutti quelli trasferibili"] = main
                    if "quelli gestibili" in sheets:
                        sheets["quelli gestibili"] = main

                    with pd.ExcelWriter(xls_path, engine="openpyxl") as writer:
                        for sn, df in sheets.items():
                            df.to_excel(writer, sheet_name=sn, index=False)

                    # Salva anche in monthly_files con nome originale
                    dest = MONTHLY_FILES_DIR / uploaded_pdf.name
                    dest.write_bytes(_Path(tmp_path).read_bytes())

                    st.success(f"✅ Aggiornato: **{len(rimossi)} rimossi**, **{len(nuovi)} aggiunti**. "
                               f"Totale: {len(main):,} fondi.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Errore: {e}")
                finally:
                    try: _os.unlink(tmp_path)
                    except: pass

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
