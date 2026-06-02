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

# Percorso GP cache dall'app Azimut — solo su Windows locale
_GP_CACHE_FILE = Path(r"C:\Users\benev\azimut_app\data\gp_cache.json")

# Cartella per file mensili — relativa alla cartella app (funziona su cloud e locale)
MONTHLY_FILES_DIR = Path(__file__).parent.parent / "data" / "monthly_files"
try:
    MONTHLY_FILES_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


def load_scenarios_from_global_view(pdf_path: str) -> dict | None:
    """
    Carica scenari da un PDF Global View (settimanale).
    Restituisce un dict scenario compatibile con SCENARIOS, oppure None in caso di errore.
    """
    try:
        from .global_view_parser import parse_global_view
        gv = parse_global_view(pdf_path)
        if "error" in gv:
            return None
        date_label = gv.get("date", "")
        weights    = gv["weights"]
        summary    = gv["summary"]
        bond_pref  = gv.get("bond_pref", "")
        desc = (
            f"Scenario basato su Azimut Global View {date_label}. "
            f"{summary}. "
            f"Pesi derivati dalle view: Equity {weights['Azionari']}% | "
            f"Bond {weights['Obbligazionari']}% | "
            f"Bilanciati {weights['Bilanciati/Flessibili']}%."
        )
        return {
            f"📡 Global View {date_label}": {
                "descrizione": desc,
                "pesi": weights,
                "dettaglio": {
                    "Equity %":    weights["Azionari"],
                    "Bond %":      weights["Obbligazionari"],
                    "Bilanciati %":weights["Bilanciati/Flessibili"],
                },
                "bond_pref": bond_pref,
                "raw_views": gv.get("raw_views", {}),
            }
        }
    except Exception as e:
        print(f"[GlobalView parser] {e}")
        return None


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
    """
    Scenari indipendenti da GP: combinazione di profilo di rischio × outlook macro.
    Usati quando il GP cache non è disponibile.
    Basati su framework standard: Equity/Bond/Balanced con pesi calibrati sul profilo.
    """
    return {
        # ── Profili per outlook CAUTO (scenario di incertezza / bear) ────────
        "🛡️ PRUDENTE — Outlook Cauto": {
            "descrizione": (
                "Profilo difensivo. Prevalenza obbligazionaria di qualità, "
                "esposizione azionaria limitata a titoli globali difensivi. "
                "Adatto a scenari di rallentamento o alta volatilità."
            ),
            "pesi": {"Obbligazionari": 55, "Bilanciati/Flessibili": 30, "Azionari": 15},
            "dettaglio": {"Equity %": 15, "Bond %": 55, "Bilanciati %": 30},
        },
        # ── Profilo BILANCIATO (scenario neutro / base) ───────────────────────
        "⚖️ BILANCIATO — Outlook Neutro": {
            "descrizione": (
                "Profilo bilanciato classico. Mix equilibrato tra azionario globale, "
                "obbligazionario diversificato e strategie flessibili. "
                "Adatto a scenari di crescita moderata con incertezze."
            ),
            "pesi": {"Azionari": 35, "Obbligazionari": 35, "Bilanciati/Flessibili": 30},
            "dettaglio": {"Equity %": 35, "Bond %": 35, "Bilanciati %": 30},
        },
        # ── Profilo DINAMICO (scenario costruttivo / bull) ────────────────────
        "📈 DINAMICO — Outlook Costruttivo": {
            "descrizione": (
                "Profilo orientato alla crescita. Sovrappeso azionario globale e tematico, "
                "obbligazionario ridotto a componente diversificante. "
                "Adatto a scenari di espansione economica."
            ),
            "pesi": {"Azionari": 55, "Bilanciati/Flessibili": 25, "Obbligazionari": 20},
            "dettaglio": {"Equity %": 55, "Bond %": 20, "Bilanciati %": 25},
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

# Macro-aree geografiche per diversificazione
_GEO_MAP = [
    ("US",       re.compile(r'\b(US|USA|AMERICA|AMERICAN|STATES|S&P|DOW)\b', re.I)),
    ("EUROPE",   re.compile(r'\b(EUROPE|EURO|EUR|EUROPEAN)\b', re.I)),
    ("EMERGING", re.compile(r'\b(EMERG|EM |DEVELOP|FRONTIER|ASIA|CHINA|INDIA|BRAZIL|LATIN)\b', re.I)),
    ("JAPAN",    re.compile(r'\b(JAPAN|JAPANES|NIKKEI)\b', re.I)),
    ("GLOBAL",   re.compile(r'\b(GLOBAL|WORLD|INTERNAZ|INTERNATION|MONDIALE)\b', re.I)),
]

def _geo_area(nome: str, classif: str) -> str:
    """Estrae la macro-area geografica principale del fondo."""
    text = (str(nome) + " " + str(classif)).upper()
    for area, pattern in _GEO_MAP:
        if pattern.search(text):
            return area
    return "OTHER"


def _is_global(nome: str, classif: str) -> bool:
    """True se il fondo ha respiro globale/internazionale."""
    return bool(_GLOBAL_RE.search(str(nome)) or _GLOBAL_RE.search(str(classif)))


def _consistency_bonus(row) -> float:
    """
    Bonus consistenza: premia chi non ha avuto anni fortemente negativi.
    Penalizza ogni anno < -10%.
    """
    bonus = 0.0
    for col in [COL["perf_2022"], COL["perf_2023"], COL["perf_2024"]]:
        v = row.get(col)
        if v is None or str(v) in ("nan", "None"):
            continue
        try:
            pv = float(v)
            if pv < -0.10:
                bonus -= 0.5  # penalità anno molto negativo
            elif pv > 0.05:
                bonus += 0.1  # piccolo bonus anno positivo
        except Exception:
            pass
    return bonus


def _quality_score(row) -> float:
    """
    Punteggio qualità professionale:
    - FIDA rating (filtro duro, ma pesa anche nel ranking)
    - Performance 3Y annualizzata (50%): più predittiva di 1Y
    - Sortino proxy: perf_3Y / volatilità (downside-adjusted, 30%)
    - Performance 1Y recente (20%)
    - Bonus consistenza annuale (non avere anni molto negativi)
    - Floor: se perf_3Y < 0 → punteggio dimezzato (non idealmente scelto)
    """
    try:
        rat = float(row.get(COL["rating"]) or 0)
        p1  = float(row.get(COL["perf_1y"]) or 0)
        p3  = float(row.get(COL["perf_3y"]) or 0)
        vol = max(float(row.get(COL["volatilita"]) or 0.10), 0.01)
        sortino = p3 / vol   # Sortino proxy: perf_3Y / vol

        # Pesi: 3Y (50%) + Sortino (30%) + 1Y (20%)
        score = p3 * 5.0 + sortino * 3.0 + p1 * 2.0

        # Bonus rating FIDA (amplificatore)
        score *= (1 + rat * 0.15)

        # Bonus consistenza anni precedenti
        score += _consistency_bonus(row)

        # Floor: perf_3Y negativa dimezza il punteggio
        if p3 < 0:
            score *= 0.5

        return score
    except Exception:
        return 0.0


def _fund_root(nome: str) -> str:
    """Radice del nome fondo: rimuove classe/divisa/acc/inc dal fondo per detectare stessa strategia."""
    n = re.sub(r'\b(ACC|INC|DIST|DIS|A|B|C|D|E|EUR|USD|GBP|HDG|EURHDG|USDHDG|'
               r'CHFHDG|GBPHDG|CAP|RETAIL|INSTIT|R|I|W|N|P|Q|VTA|MINC)\b', '', nome.upper())
    return re.sub(r'\s+', ' ', n).strip()


def _select_bucket_funds(
    df_b: pd.DataFrame,
    n: int,
    primary_col: str,
    secondary_col: str,
    max_house_pct: float = 0.34,   # max 1/3 = max 1 fondo su 3 per casa
    max_dist_pct: float = 1.0,
    max_geo_pct: float = 0.67,     # max 2/3 dalla stessa area geografica
) -> pd.DataFrame:
    """
    Seleziona n fondi da un bucket con tutti i vincoli professionali:
    - Max 1 fondo per casa (max_house_pct ≈ 1/n)
    - Max 1 per sottoclassificazione FIDA
    - Max 1 per radice strategia (ACC e MINC = stesso fondo)
    - Max 2/3 dalla stessa macro-area geografica
    - Almeno 1 fondo globale/internazionale
    - Quota massima distribuzione
    - Preferenza per fondi con perf_3Y ≥ 0 (floor qualità)
    """
    df_b = df_b.copy()
    df_b["_primary"]   = pd.to_numeric(df_b[primary_col],   errors="coerce").fillna(0)
    df_b["_secondary"] = pd.to_numeric(df_b[secondary_col], errors="coerce").fillna(0)
    df_b["_global"]  = df_b.apply(
        lambda r: _is_global(str(r.get(COL["nome"],"")), str(r.get(COL["classif"],""))), axis=1
    )
    df_b["_house"]   = df_b[COL["house"]].astype(str).str.strip().str.upper()
    df_b["_subcat"]  = df_b[COL["classif"]].astype(str).str.strip().str.upper()
    df_b["_root"]    = df_b[COL["nome"]].astype(str).apply(_fund_root)
    df_b["_is_dist"] = df_b[COL["acc_dist"]].astype(str).str.upper().str.contains("DISTRIB", na=False)
    df_b["_geo"]     = df_b.apply(
        lambda r: _geo_area(str(r.get(COL["nome"],"")), str(r.get(COL["classif"],""))), axis=1
    )
    df_b["_p3_ok"]   = pd.to_numeric(df_b[COL["perf_3y"]], errors="coerce").fillna(0) >= 0

    # Ordina: globali prima, poi primary_col, poi secondary_col
    df_sorted = df_b.sort_values(
        ["_global", "_primary", "_secondary"],
        ascending=[False, False, False]
    )

    # Ordina: prima i fondi con perf_3Y ≥ 0, poi per primary, poi secondary
    df_sorted = df_b.sort_values(
        ["_global", "_p3_ok", "_primary", "_secondary"],
        ascending=[False, False, False, False]
    )

    selected = []
    house_counts: dict[str, int] = {}
    geo_counts:   dict[str, int] = {}
    used_subcats: set[str] = set()
    used_roots:   set[str] = set()
    dist_count = 0
    n_total = max(n, 1)
    max_house = max(1, round(n_total * max_house_pct))
    max_geo   = max(1, round(n_total * max_geo_pct))

    for _, row in df_sorted.iterrows():
        if len(selected) >= n:
            break
        house   = row["_house"]
        subcat  = row["_subcat"]
        root    = row["_root"]
        geo     = row["_geo"]
        is_dist = bool(row["_is_dist"])

        if house_counts.get(house, 0)  >= max_house:  continue
        if subcat in used_subcats:                     continue
        if root   in used_roots:                       continue
        if geo_counts.get(geo, 0) >= max_geo:          continue
        if is_dist and max_dist_pct < 1.0:
            if len(selected) > 0 and (dist_count + 1) / n_total > max_dist_pct:
                continue

        selected.append(row)
        house_counts[house]  = house_counts.get(house, 0) + 1
        geo_counts[geo]      = geo_counts.get(geo, 0) + 1
        used_subcats.add(subcat)
        used_roots.add(root)
        if is_dist:
            dist_count += 1

    # Fallback progressivo: allenta vincoli uno per volta se non abbiamo N fondi
    if len(selected) < n:
        selected_isins = {r[COL["isin"]] for r in selected}
        for _, row in df_sorted.iterrows():
            if len(selected) >= n: break
            if row[COL["isin"]] in selected_isins: continue
            if row["_root"] in used_roots: continue
            h = row["_house"]
            if house_counts.get(h, 0) < max_house:
                selected.append(row)
                house_counts[h] = house_counts.get(h, 0) + 1
                used_roots.add(row["_root"])
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
    max_dist_pct: float = 1.0,
) -> tuple[list[dict], list[dict]]:
    """
    Genera DUE portafogli per lo scenario selezionato, applicando i filtri sidebar già nel df.

    Portafoglio 1 — QUALITÀ:
      Primary: quality score multi-periodo (3Y 50% + Sortino 30% + 1Y 20% + consistenza)
               amplificato da FIDA rating; floor: perf_3Y < 0 dimezza il punteggio
      Secondary: retrocessione (a parità di qualità vince chi paga di più)

    Portafoglio 2 — RETROCESSIONE:
      Primary: retrocessione banca (massimizza l'interesse del distributore)
      Secondary: quality score (garantisce un minimo di qualità)

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

            sel = _select_bucket_funds(df_b, n_per_bucket, primary_col, secondary_col,
                                       max_dist_pct=max_dist_pct)
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
