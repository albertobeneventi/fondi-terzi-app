# -*- coding: utf-8 -*-
"""Logica filtri: rating, classificazione, retrocessione."""
import re
import streamlit as st
import pandas as pd
from .config import COL, COLOR_PRIMARY, COLOR_STAR_ON, COLOR_STAR_OFF


def _macro(classif: str) -> str:
    """Estrae la macrocategoria dal nome FIDA (primo token alfabetico)."""
    if not classif or str(classif).lower() in ("nan", ""):
        return "Senza categoria"
    return re.split(r"[ (]", str(classif).strip())[0]


def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Renderizza sidebar con tutti i filtri e restituisce il DataFrame filtrato."""
    st.sidebar.markdown(f"""
        <div style='background:{COLOR_PRIMARY};padding:16px 12px;border-radius:8px;margin-bottom:20px;'>
            <span style='color:white;font-size:18px;font-weight:700;'>🔍 Filtri</span>
        </div>
    """, unsafe_allow_html=True)

    mask = pd.Series([True] * len(df), index=df.index)

    # ── 1. RATING FIDA ────────────────────────────────────────────────────────
    st.sidebar.markdown("**⭐ Rating FIDA**")
    rating_opts = {
        "⭐⭐⭐⭐⭐ (5)": 5, "⭐⭐⭐⭐ (4)": 4,
        "⭐⭐⭐ (3)": 3, "⭐⭐ (2)": 2, "⭐ (1)": 1,
    }
    sel_ratings = []
    for label, val in rating_opts.items():
        if st.sidebar.checkbox(label, value=True, key=f"rat_{val}"):
            sel_ratings.append(val)
    include_unrated = st.sidebar.checkbox("Senza rating", value=True, key="rat_none")

    if sel_ratings or include_unrated:
        r_col = COL["rating"]
        if r_col in df.columns:
            r_mask = df[r_col].isin(sel_ratings)
            if include_unrated:
                r_mask = r_mask | df[r_col].isna()
            mask &= r_mask

    st.sidebar.divider()

    # ── 2. CLASSIFICAZIONE (filtro a due livelli) ─────────────────────────────
    st.sidebar.markdown("**📂 Classificazione**")
    cl_col = COL["classif"]
    if cl_col in df.columns:
        # Livello 1: macrocategoria
        df_tmp = df.copy()
        df_tmp["_macro"] = df_tmp[cl_col].fillna("").apply(_macro)
        macros = sorted(df_tmp["_macro"].unique().tolist())
        sel_macro = st.sidebar.multiselect(
            "Macrocategoria", macros,
            placeholder="Tutte",
            key="filter_macro"
        )
        # Livello 2: classificazione specifica (filtrata per macro)
        if sel_macro:
            avail = df_tmp[df_tmp["_macro"].isin(sel_macro)][cl_col].dropna().unique()
        else:
            avail = df_tmp[cl_col].dropna().unique()
        categs = sorted(avail.tolist())
        sel_cat = st.sidebar.multiselect(
            "Categoria specifica", categs,
            placeholder="Tutte le categorie",
            key="filter_classif"
        )
        if sel_cat:
            mask &= df[cl_col].isin(sel_cat)
        elif sel_macro:
            macro_mask = df[cl_col].fillna("").apply(_macro).isin(sel_macro)
            mask &= macro_mask

    st.sidebar.divider()

    # ── 3. ACC. / DISTR. ─────────────────────────────────────────────────────
    st.sidebar.markdown("**🔄 Acc. / Distribuzione**")
    ad_col = COL["acc_dist"]
    if ad_col in df.columns:
        # Mostra solo 2 macro-opzioni: Accumulazione / Distribuzione
        sel_ad = st.sidebar.multiselect(
            "Tipo", ["ACCUMULAZIONE", "DISTRIBUZIONE"],
            placeholder="Tutti",
            key="filter_acc_dist"
        )
        if sel_ad:
            ad_mask = pd.Series([False] * len(df), index=df.index)
            col_vals = df[ad_col].fillna("").str.upper()
            if "ACCUMULAZIONE" in sel_ad:
                ad_mask |= col_vals.str.contains("ACCUM", na=False)
            if "DISTRIBUZIONE" in sel_ad:
                ad_mask |= col_vals.str.contains("DISTRIB", na=False)
            mask &= ad_mask

    st.sidebar.divider()

    # ── 4. RETROCESSIONE BANCA ────────────────────────────────────────────────
    st.sidebar.markdown("**💰 Retrocessione Banca**")
    ret_col = COL["retro"]
    if ret_col in df.columns:
        ret_vals = df[ret_col].dropna()
        if len(ret_vals) > 0:
            ret_min = float(ret_vals.min())
            ret_max = float(ret_vals.max())
            ret_range = st.sidebar.slider(
                "Retrocessione minima (%)",
                min_value=round(ret_min * 100, 2),
                max_value=round(ret_max * 100, 2),
                value=round(ret_min * 100, 2),
                step=0.05,
                format="%.2f%%",
                key="filter_retro"
            )
            mask &= (df[ret_col] >= ret_range / 100) | df[ret_col].isna()

    st.sidebar.divider()

    # ── 5. PERFORMANCE 1 ANNO ─────────────────────────────────────────────────
    st.sidebar.markdown("**📈 Perf. 1 anno (min %)**")
    p1y_col = COL["perf_1y"]
    if p1y_col in df.columns:
        p_vals = df[p1y_col].dropna()
        if len(p_vals) > 0:
            p_min = float(p_vals.min())
            p_max = float(p_vals.max())
            p_range = st.sidebar.slider(
                "Perf. 1 anno ≥",
                min_value=round(p_min * 100, 1),
                max_value=round(p_max * 100, 1),
                value=round(p_min * 100, 1),
                step=0.5,
                format="%.1f%%",
                key="filter_perf1y"
            )
            mask &= (df[p1y_col] >= p_range / 100) | df[p1y_col].isna()

    st.sidebar.divider()

    # ── 6. RICERCA TESTO ──────────────────────────────────────────────────────
    st.sidebar.markdown("**🔎 Cerca per nome / ISIN**")
    search = st.sidebar.text_input("", placeholder="Nome fondo, casa o ISIN...", key="filter_search")
    if search:
        nome_col  = COL["nome"]
        house_col = COL["house"]
        isin_col  = COL["isin"]
        s = search.upper()
        text_mask = (
            df[nome_col].str.upper().str.contains(s, na=False)  |
            df[house_col].str.upper().str.contains(s, na=False) |
            df[isin_col].str.upper().str.contains(s, na=False)
        )
        mask &= text_mask

    return df[mask].copy()
