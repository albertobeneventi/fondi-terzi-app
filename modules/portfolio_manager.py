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

# Percorso GP cache dall'app Azimut (aggiornato quando l'utente carica un nuovo GP)
_GP_CACHE_FILE = Path(r"C:\Users\benev\azimut_app\data\gp_cache.json")

# Cartella per file mensili (catalogo PDF, ecc.)
MONTHLY_FILES_DIR = Path(r"C:\Users\benev\monthly_files")
MONTHLY_FILES_DIR.mkdir(exist_ok=True)


def _load_scenarios_from_gp_cache() -> dict:
    """
    Legge gli scenari dal gp_cache.json dell'app Azimut.
    Calcola i pesi bucket (Azionari/Obbligazionari/Bilanciati) aggregando
    i pesi dei singoli fondi per categoria.
    """
    if not _GP_CACHE_FILE.exists():
        return {}
    try:
        with open(_GP_CACHE_FILE, encoding="utf-8-sig") as f:
            cache = json.load(f)
        gp_data = cache.get("gp_data", {})
        edition = str(cache.get("filename", "")) + " — " + str(cache.get("last_updated", ""))
        icons = {"Base": "⚖️", "Bear": "🛡️", "Bull": "📈"}
        result = {}
        for sc_name, sc_data in gp_data.items():
            if not isinstance(sc_data, dict) or "funds" not in sc_data:
                continue
            funds = sc_data["funds"]
            # Aggrega pesi per categoria (Azionari, Obbligazionari, Bilanciati/Flessibili)
            bucket_w: dict[str, float] = {}
            for f in funds:
                cat = f.get("categoria", "Altro")
                w   = float(f.get("weight", 0))
                bucket_w[cat] = bucket_w.get(cat, 0) + w
            # Normalizza a 100%
            total = sum(bucket_w.values())
            pesi = {k: round(v / total * 100) for k, v in bucket_w.items()} if total > 0 else {}

            info = sc_data.get("info", "")
            icon = icons.get(sc_name, "📊")
            result[f"{icon} {sc_name} — {edition}"] = {
                "descrizione": info,
                "pesi": pesi,
                "dettaglio": {"Info": info},
            }
        return result
    except Exception as e:
        print(f"[portfolio_manager] Errore lettura GP cache: {e}")
        return {}


def _default_scenarios() -> dict:
    """Scenari hardcoded come fallback se GP cache non disponibile."""
    return {
        "🛡️ BEAR — Conflitto lungo": {
            "descrizione": "Scenario recessivo. Prevalenza obbligazionaria, riduzione equity.",
            "pesi": {"Obbligazionari": 51, "Bilanciati/Flessibili": 31, "Azionari": 18},
            "dettaglio": {"Equity %": 22, "Bond %": 48, "Private Markets %": 30},
        },
        "⚖️ BASE — Incertezza geopolitica": {
            "descrizione": "Portafoglio bilanciato con lieve cautela.",
            "pesi": {"Bilanciati/Flessibili": 44, "Obbligazionari": 31, "Azionari": 24},
            "dettaglio": {"Equity %": 32, "Bond %": 38, "Private Markets %": 30},
        },
        "📈 BULL — Conflitto breve": {
            "descrizione": "Sovrappeso azionario, normalizzazione commodity.",
            "pesi": {"Azionari": 39, "Obbligazionari": 36, "Bilanciati/Flessibili": 26},
            "dettaglio": {"Equity %": 40, "Bond %": 30, "Private Markets %": 30},
        },
    }


# Carica scenari all'avvio (da GP cache se disponibile, altrimenti default)
_gp_scenarios = _load_scenarios_from_gp_cache()
SCENARIOS = _gp_scenarios if _gp_scenarios else _default_scenarios()


def reload_scenarios():
    """Ricarica gli scenari dal GP cache (chiamare dopo upload nuovo GP)."""
    global SCENARIOS
    _gp_scenarios = _load_scenarios_from_gp_cache()
    SCENARIOS = _gp_scenarios if _gp_scenarios else _default_scenarios()
    return SCENARIOS

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


_GLOBAL_RE = re.compile(
    r'\b(GLOBAL|WORLD|INTERNAZ|INTERNATION|MONDIALE|GLOBALE|GLOBALI|EMERGING|EUROPE|ASIA|AMERICA)\b',
    re.I
)


def _is_global(nome: str, classif: str) -> bool:
    """True se il fondo ha respiro globale/internazionale."""
    return bool(_GLOBAL_RE.search(str(nome)) or _GLOBAL_RE.search(str(classif)))


def _quality_score(row) -> float:
    """Punteggio qualità: rating FIDA (peso 50%) + Sharpe proxy (perf/vol, 30%) + perf 1Y (20%)."""
    try:
        rat = float(row.get(COL["rating"]) or 0)
        p1  = float(row.get(COL["perf_1y"]) or 0)
        vol = float(row.get(COL["volatilita"]) or 1)
        sharpe = p1 / max(abs(vol), 0.01)
        return rat * 2.0 + sharpe * 5.0 + p1 * 2.0
    except Exception:
        return 0.0


def _select_bucket_funds(
    df_b: pd.DataFrame,
    n: int,
    primary_col: str,
    secondary_col: str,
    max_house_pct: float = 0.5,
) -> pd.DataFrame:
    """
    Seleziona n fondi da un bucket applicando i vincoli:
    - Max max_house_pct della selezione dalla stessa casa di gestione
    - Max 1 fondo per sottoclassificazione specifica
    - Priorità a fondi globali/internazionali (almeno 1 se disponibile)
    Ordina per primary_col desc, secondary_col desc a parità.
    """
    df_b = df_b.copy()
    df_b["_primary"]   = pd.to_numeric(df_b[primary_col],   errors="coerce").fillna(0)
    df_b["_secondary"] = pd.to_numeric(df_b[secondary_col], errors="coerce").fillna(0)
    df_b["_global"]    = df_b.apply(
        lambda r: _is_global(str(r.get(COL["nome"],"")), str(r.get(COL["classif"],""))), axis=1
    )
    df_b["_house"]  = df_b[COL["house"]].astype(str).str.strip().str.upper()
    df_b["_subcat"] = df_b[COL["classif"]].astype(str).str.strip().str.upper()

    # Ordina: globali prima, poi primary_col, poi secondary_col
    df_sorted = df_b.sort_values(
        ["_global", "_primary", "_secondary"],
        ascending=[False, False, False]
    )

    selected = []
    house_counts: dict[str, int] = {}
    used_subcats: set[str] = set()

    for _, row in df_sorted.iterrows():
        if len(selected) >= n:
            break
        house   = row["_house"]
        subcat  = row["_subcat"]
        n_total = max(n, 1)

        # Vincolo: max 50% stessa casa
        if house_counts.get(house, 0) >= max(1, round(n_total * max_house_pct)):
            continue
        # Vincolo: 1 fondo per sottoclassificazione (se già coperta salta)
        if subcat in used_subcats and not row["_global"]:
            continue

        selected.append(row)
        house_counts[house] = house_counts.get(house, 0) + 1
        used_subcats.add(subcat)

    # Se non abbiamo trovato abbastanza, aggiungi i rimanenti senza il vincolo subcat
    if len(selected) < n:
        selected_isins = {r[COL["isin"]] for r in selected}
        for _, row in df_sorted.iterrows():
            if len(selected) >= n:
                break
            if row[COL["isin"]] not in selected_isins:
                house = row["_house"]
                if house_counts.get(house, 0) < max(1, round(n_total * max_house_pct)):
                    selected.append(row)
                    house_counts[house] = house_counts.get(house, 0) + 1
                    selected_isins.add(row[COL["isin"]])

    return pd.DataFrame(selected) if selected else pd.DataFrame()


def suggest_portfolio(
    df: pd.DataFrame,
    scenario_key: str,
    min_rating: int = 3,
    n_per_bucket: int = 3,
    sort_by: str = "retro",
) -> list[dict]:
    """Portafoglio singolo (legacy). Usa suggest_portfolio_dual per avere entrambe le varianti."""
    result_q, _ = suggest_portfolio_dual(df, scenario_key, min_rating, n_per_bucket)
    return result_q


def suggest_portfolio_dual(
    df: pd.DataFrame,
    scenario_key: str,
    min_rating: int = 3,
    n_per_bucket: int = 3,
) -> tuple[list[dict], list[dict]]:
    """
    Genera DUE portafogli per lo scenario selezionato, applicando i filtri sidebar già nel df.

    Portafoglio 1 — QUALITÀ:
      Criterio primario: punteggio qualità (FIDA rating + Sharpe proxy)
      Criterio secondario: retrocessione (a parità di qualità vince chi paga di più)

    Portafoglio 2 — RETROCESSIONE:
      Criterio primario: retrocessione banca
      Criterio secondario: punteggio qualità

    Vincoli (entrambi):
      - Solo fondi Collocabile = SI
      - Rating ≥ min_rating
      - Max 50% stessa casa per bucket
      - Max 1 fondo per sottoclassificazione
      - Almeno 1 fondo globale/internazionale per bucket (se disponibile)
    """
    scenario    = SCENARIOS[scenario_key]
    pesi_bucket = scenario["pesi"]

    def _build(primary_col: str, secondary_col: str) -> list[dict]:
        result = []
        for bucket, peso_tot in pesi_bucket.items():
            df_b = df.copy()
            df_b["_bucket"] = df_b[COL["classif"]].apply(classify_bucket)
            df_b = df_b[df_b["_bucket"] == bucket]
            if COL["collocabile"] in df_b.columns:
                df_b = df_b[df_b[COL["collocabile"]].astype(str).str.upper().str.strip() == "SI"]
            if min_rating > 0:
                df_b = df_b[df_b[COL["rating"]].fillna(0) >= min_rating]
            if df_b.empty:
                continue

            # Aggiungi punteggio qualità come colonna
            df_b = df_b.copy()
            df_b["_qscore"] = df_b.apply(_quality_score, axis=1)

            sel = _select_bucket_funds(df_b, n_per_bucket, primary_col, secondary_col)
            if sel.empty:
                continue

            peso_singolo = round(peso_tot / len(sel), 1)
            for _, row in sel.iterrows():
                result.append({
                    "ISIN":         str(row.get(COL["isin"], "")),
                    "nome":         str(row.get(COL["nome"], ""))[:70],
                    "house":        str(row.get(COL["house"], "")),
                    "bucket":       bucket,
                    "peso":         peso_singolo,
                    "rating":       row.get(COL["rating"]),
                    "retro":        row.get(COL["retro"]),
                    "perf_1y":      row.get(COL["perf_1y"]),
                    "perf_3y":      row.get(COL["perf_3y"]),
                    "classif":      str(row.get(COL["classif"], "")),
                    "is_global":    bool(row.get("_global", False)),
                    "url_fondidoc": str(row.get(COL["url_fondidoc"], "") or ""),
                    "url_quantalys":str(row.get(COL["url_quantalys"], "") or ""),
                })
        return result

    ptf_qualita  = _build("_qscore",     COL["retro"])
    ptf_retro    = _build(COL["retro"],  "_qscore")
    return ptf_qualita, ptf_retro


def suggest_portfolio(
    df: pd.DataFrame,
    scenario_key: str,
    min_rating: int = 3,
    n_per_bucket: int = 3,
    sort_by: str = "retro",
) -> list[dict]:
    """Portafoglio singolo (legacy). Usa suggest_portfolio_dual per entrambe le varianti."""
    result_q, _ = suggest_portfolio_dual(df, scenario_key, min_rating, n_per_bucket)
    return result_q


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
