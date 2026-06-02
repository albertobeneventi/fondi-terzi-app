# -*- coding: utf-8 -*-
"""Costanti e configurazione centralizzata."""
from pathlib import Path

# ── Percorsi file dati (relativi alla cartella app — funziona sia in locale che su Streamlit Cloud) ──
_APP_DIR   = Path(__file__).parent.parent
DATA_FILE  = _APP_DIR / "data" / "fondi.xlsx"
SHEET_NAME = "tutti quelli trasferibili"

# ── Nomi colonne normalizzati (dopo strip) ──────────────────────────────────
COL = {
    "house":        "ASSET MANAGEMENT HOUSE",
    "sicav":        "FONDO/SICAV",
    "isin":         "ISIN",
    "nome":         "DESCRIZIONE FONDO",
    "classe":       "CLASSE",
    "divisa":       "DIVISA FONDO",
    "comm_gest_az": "COMMISSIONE DI GESTIONE",     # fonte Azimut
    "comm_distr":   "COMMISSIONE DI DISTRIBUZIONE",
    "commenti":     "COMMENTI",
    "bps_raw":      "BPS ANNUI CF",               # % BPS *ANNUI CF (raw)
    "trasfx":       "Traferibile",
    "collocabile":  "Collocabile",
    "classif":      "CLASSIFICAZIONE",
    "comm_ingresso":"COMMISSIONI INGRESSO",
    "comm_uscita":  "COMMISSIONI DI USCITA",
    "comm_gest":    "COMMISSIONI DI GESTIONE",     # fonte BPER/fondidoc
    "comm_totale":  "COMMISSIONE TOTALE",
    "retro":        "RETROCESSIONE BANCA",
    "perf_1y":      "PERF. 1 ANNO",
    "perf_3y":      "PERF. 3 ANNI",
    "perf_ytd":     "PERF. YTD",
    "perf_2024":    "PERF. 2024",
    "perf_2023":    "PERF. 2023",
    "perf_2022":    "PERF. 2022",
    "volatilita":   "VOLATILITA' (1 anno)",
    "rating":       "RATING",
    "acc_dist":     "ACC. / DISTR.",
    "url_fondidoc": "SCHEDA FONDIDOC",
    "url_quantalys":"SCHEDA QUANTALYS",
}

# ── Colonne percentuali (da formattare come %) ──────────────────────────────
PCT_COLS = {
    COL["comm_ingresso"], COL["comm_uscita"], COL["comm_gest"],
    COL["retro"],
    COL["perf_1y"], COL["perf_3y"], COL["perf_ytd"],
    COL["perf_2024"], COL["perf_2023"], COL["perf_2022"],
    COL["volatilita"],
}

# ── Colori brand ─────────────────────────────────────────────────────────────
COLOR_PRIMARY   = "#1F4E79"
COLOR_ACCENT    = "#2E86AB"
COLOR_BG_LIGHT  = "#F0F4F8"
COLOR_STAR_ON   = "#F59E0B"
COLOR_STAR_OFF  = "#D1D5DB"
COLOR_POS       = "#059669"
COLOR_NEG       = "#DC2626"
COLOR_NEUTRAL   = "#6B7280"
