# -*- coding: utf-8 -*-
"""Caricamento e normalizzazione del file Excel."""
import pandas as pd
import json, os
from pathlib import Path
import streamlit as st
from .config import DATA_FILE, SHEET_NAME, COL, PCT_COLS

# Cache JSON con gli URL reali (relativi alla cartella app)
_DATA_DIR        = Path(__file__).parent.parent / "data"
_FONDIDOC_CACHE  = _DATA_DIR / "fondidoc_cache.json"
_QUANTALYS_CACHE = _DATA_DIR / "quantalys_cache.json"


@st.cache_data(show_spinner=False)
def _load_fondidoc_urls() -> dict:
    if not os.path.exists(_FONDIDOC_CACHE):
        return {}
    with open(_FONDIDOC_CACHE, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if v}


@st.cache_data(show_spinner=False)
def _load_quantalys_urls() -> dict:
    if not os.path.exists(_QUANTALYS_CACHE):
        return {}
    with open(_QUANTALYS_CACHE, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if v}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip spazi dai nomi colonne e normalizza i tipi."""
    df.columns = [str(c).strip() for c in df.columns]
    # Rinomina colonne con spazi / caratteri speciali
    rename = {
        "ASSET MANAGEMENT HOUSE": "ASSET MANAGEMENT HOUSE",
        "DIVISA FONDO": "DIVISA FONDO",
        "COMMISSIONE DI GESTIONE": "COMMISSIONE DI GESTIONE",
        "COMMISSIONE DI DISTRIBUZIONE": "COMMISSIONE DI DISTRIBUZIONE",
        "COMMENTI": "COMMENTI",
        "% BPS *ANNUI CF": "BPS ANNUI CF",
        "BPS ANNUI CF": "BPS ANNUI CF",
    }
    df = df.rename(columns=rename)
    # Converti percentuali in float
    for col in PCT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # RATING come int
    if COL["rating"] in df.columns:
        df[COL["rating"]] = pd.to_numeric(df[COL["rating"]], errors="coerce")
    return df


@st.cache_data(show_spinner="Caricamento fondi...")
def load_data() -> pd.DataFrame:
    df = pd.read_excel(DATA_FILE, sheet_name=SHEET_NAME, dtype=str)
    df = _normalize_columns(df)
    # Converti percentuali
    for col in PCT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if COL["rating"] in df.columns:
        df[COL["rating"]] = pd.to_numeric(df[COL["rating"]], errors="coerce")

    # Carica URL reali dalle cache JSON direttamente (non via funzioni cachate)
    isin_col = COL["isin"]
    if isin_col in df.columns:
        fd_urls, qly_urls = {}, {}
        if os.path.exists(_FONDIDOC_CACHE):
            with open(_FONDIDOC_CACHE, encoding="utf-8") as f:
                fd_urls = {k: v for k, v in json.load(f).items() if v}
        if os.path.exists(_QUANTALYS_CACHE):
            with open(_QUANTALYS_CACHE, encoding="utf-8") as f:
                qly_urls = {k: v for k, v in json.load(f).items() if v}
        df[COL["url_fondidoc"]]  = df[isin_col].astype(str).str.strip().map(fd_urls)
        df[COL["url_quantalys"]] = df[isin_col].astype(str).str.strip().map(qly_urls)

    return df
