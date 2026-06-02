# -*- coding: utf-8 -*-
"""
Gestione portafogli: salvataggio, caricamento, suggerimento automatico
basato su scenari macro (BASE / BEAR / BULL) e rating minimo selezionabile.
"""
import json
import re
from pathlib import Path
from datetime import datetime
import pandas as pd
from .config import COL

# ── Percorso storage portafogli ──────────────────────────────────────────────
_PORTFOLIO_FILE = Path(__file__).parent.parent / "data" / "portfolios.json"
# Nota: su Streamlit Cloud i file non persistono tra deploy. Per ora OK per uso locale.


# ── Definizione scenari (pesi % su quota liquida, esclude Private Markets) ──
SCENARIOS = {
    "🛡️ BEAR — Conflitto lungo": {
        "descrizione": (
            "Scenario recessivo da conflitto prolungato. "
            "Prevalenza obbligazionaria governativa/IG, riduzione equity."
        ),
        "pesi": {"Obbligazionari": 51, "Bilanciati/Flessibili": 31, "Azionari": 18},
        "dettaglio": {"Equity %": 22, "Bond %": 48, "Private Markets %": 30},
    },
    "⚖️ BASE — Incertezza geopolitica": {
        "descrizione": (
            "Scenario di attesa: guerra breve o lunga non ancora definita. "
            "Portafoglio bilanciato con lieve cautela."
        ),
        "pesi": {"Bilanciati/Flessibili": 44, "Obbligazionari": 31, "Azionari": 24},
        "dettaglio": {"Equity %": 32, "Bond %": 38, "Private Markets %": 30},
    },
    "📈 BULL — Conflitto breve": {
        "descrizione": (
            "Scenario ottimistico: cessazione rapida delle ostilità, "
            "riapertura Hormuz, normalizzazione commodity. Sovrappeso azionario."
        ),
        "pesi": {"Azionari": 39, "Obbligazionari": 36, "Bilanciati/Flessibili": 26},
        "dettaglio": {"Equity %": 40, "Bond %": 30, "Private Markets %": 30},
    },
}

# Macro-categorie FIDA per bucket
_BUCKET_MAP = {
    "Azionari":           re.compile(r"^Azionari", re.I),
    "Obbligazionari":     re.compile(r"^Obbligazionari|^Monetari", re.I),
    "Bilanciati/Flessibili": re.compile(r"^Bilanciati|^Flessibili|^Diversificati|^Ritorno|^Capitale|^Altri", re.I),
}


def classify_bucket(classif: str) -> str:
    """Assegna un bucket macro a una classificazione FIDA."""
    if not classif or str(classif).strip().lower() in ("nan", ""):
        return "Altro"
    for bucket, pattern in _BUCKET_MAP.items():
        if pattern.match(str(classif).strip()):
            return bucket
    return "Altro"


def suggest_portfolio(
    df: pd.DataFrame,
    scenario_key: str,
    min_rating: int = 3,
    n_per_bucket: int = 3,
    sort_by: str = "retro",   # "retro" | "rating" | "perf_1y"
) -> list[dict]:
    """
    Suggerisce un portafoglio per lo scenario selezionato.
    Seleziona i migliori n_per_bucket fondi per bucket, filtrati per rating ≥ min_rating.
    Restituisce lista di dict con ISIN, nome, peso_target, bucket, metriche.
    """
    scenario = SCENARIOS[scenario_key]
    pesi_bucket = scenario["pesi"]

    sort_col = {
        "retro":   COL["retro"],
        "rating":  COL["rating"],
        "perf_1y": COL["perf_1y"],
    }.get(sort_by, COL["retro"])

    result = []
    for bucket, peso_tot in pesi_bucket.items():
        # Filtra per bucket e rating minimo
        df_b = df.copy()
        df_b["_bucket"] = df_b[COL["classif"]].apply(classify_bucket)
        df_b = df_b[df_b["_bucket"] == bucket]
        if min_rating > 0:
            df_b = df_b[df_b[COL["rating"]].fillna(0) >= min_rating]

        # Ordina e prendi top N
        if sort_col in df_b.columns:
            df_b = df_b.sort_values(sort_col, ascending=False, na_position="last")
        df_b = df_b.head(n_per_bucket)

        if df_b.empty:
            continue

        peso_singolo = round(peso_tot / len(df_b), 1)
        for _, row in df_b.iterrows():
            result.append({
                "ISIN":        str(row.get(COL["isin"], "")),
                "nome":        str(row.get(COL["nome"], ""))[:70],
                "house":       str(row.get(COL["house"], "")),
                "bucket":      bucket,
                "peso":        peso_singolo,
                "rating":      row.get(COL["rating"]),
                "retro":       row.get(COL["retro"]),
                "perf_1y":     row.get(COL["perf_1y"]),
                "classif":     str(row.get(COL["classif"], "")),
                "url_fondidoc": str(row.get(COL["url_fondidoc"], "") or ""),
                "url_quantalys": str(row.get(COL["url_quantalys"], "") or ""),
            })
    return result


# ── Storage portafogli ────────────────────────────────────────────────────────
def load_portfolios() -> dict:
    if not _PORTFOLIO_FILE.exists():
        return {}
    with open(_PORTFOLIO_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_portfolio(name: str, scenario: str, min_rating: int, funds: list[dict]) -> None:
    portfolios = load_portfolios()
    portfolios[name] = {
        "scenario":   scenario,
        "min_rating": min_rating,
        "funds":      funds,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    _PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolios, f, ensure_ascii=False, indent=2)


def delete_portfolio(name: str) -> None:
    portfolios = load_portfolios()
    portfolios.pop(name, None)
    with open(_PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolios, f, ensure_ascii=False, indent=2)
