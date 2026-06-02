# -*- coding: utf-8 -*-
"""
Parser del documento Azimut Global View (PDF settimanale).
Estrae le view (NEUTRAL/OVER/UNDER) per asset class e le traduce
in pesi bucket (Azionari / Obbligazionari / Bilanciati/Flessibili).
"""
import re
from pathlib import Path
from datetime import datetime


# ── Allocazione neutrale di riferimento ──────────────────────────────────────
_BASE_WEIGHTS = {
    "Azionari":               35,
    "Obbligazionari":         35,
    "Bilanciati/Flessibili":  30,
}

# Tilts (punti percentuali) per ogni segnale
_TILT = {
    "OVER":           +10,
    "LIEVE_OVER":     +5,
    "NEUTRAL":         0,
    "LIEVE_UNDER":    -5,
    "UNDER":          -10,
}


def _detect_view(text: str, after_kw: str) -> str:
    """
    Trova la view (OVER/NEUTRAL/UNDER) nel testo subito dopo una keyword.
    Gestisce anche 'lieve sovrapeso' / 'lieve sottopeso'.
    """
    t = text.upper()
    idx = t.find(after_kw.upper())
    if idx < 0:
        return "NEUTRAL"
    snippet = t[idx:idx + 400]

    if re.search(r'LEGG\w+\s+SOVRAP|LIEVE\s+SOVRAP|SLIGHT\s+OVER', snippet):
        return "LIEVE_OVER"
    if re.search(r'LEGG\w+\s+SOTTOP|LIEVE\s+SOTTOP|SLIGHT\s+UNDER', snippet):
        return "LIEVE_UNDER"
    if re.search(r'\bOVERWEIGHT\b|\bSOVRAPESO\b|\bOVER\b', snippet):
        return "OVER"
    if re.search(r'\bUNDERWEIGHT\b|\bSOTTOPESO\b|\bUNDER\b', snippet):
        return "UNDER"
    return "NEUTRAL"


def parse_global_view(pdf_path: str) -> dict:
    """
    Parsa il PDF Global View e restituisce:
    {
        "date": "2026-05-27",
        "equity_view": "NEUTRAL",
        "bond_view": "LIEVE_OVER",
        "bond_pref": "IG su HY",
        "equity_em_view": "NEUTRAL",
        "weights": {"Azionari": 35, "Obbligazionari": 42, "Bilanciati/Flessibili": 23},
        "summary": "...",
        "raw_views": {...}
    }
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        full_text = "\n".join(doc[i].get_text() for i in range(len(doc)))
    except Exception as e:
        return {"error": str(e)}

    # ── Estrai data dal testo o filename ─────────────────────────────────────
    date_str = ""
    m = re.search(r'(\d{4})(\d{2})(\d{2})', Path(pdf_path).stem)
    if m:
        date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        m2 = re.search(r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})', full_text)
        if m2:
            date_str = f"{m2.group(3)}-{m2.group(2).zfill(2)}-{m2.group(1).zfill(2)}"

    # ── Estrai view per categoria ─────────────────────────────────────────────
    eq_dev_view  = _detect_view(full_text, "Equity\nDeveloped Markets")
    eq_em_view   = _detect_view(full_text, "Equity\nDeveloped Markets\nEmerging Markets")
    bond_sov_view= _detect_view(full_text, "Fixed Income\nDeveloped Markets Sovereign")
    bond_corp_view=_detect_view(full_text, "Developed Markets Corporate")
    bond_em_view = _detect_view(full_text, "Fixed Income\nDeveloped Markets Sovereign\nDeveloped Markets Corporate\nEmerging Markets")
    comm_view    = _detect_view(full_text, "Commodities")

    # Preferenza IG su HY
    bond_pref = ""
    if re.search(r'prefer\w*.*investment.grade|IG.*rispetto.*HY|IG.*piuttosto.*HY', full_text, re.I):
        bond_pref = "Preferenza IG su HY"

    # ── Calcola pesi dal tilt ─────────────────────────────────────────────────
    # Equity: usa view developed (più rilevante)
    eq_tilt   = _TILT.get(eq_dev_view, 0)
    # Bond: media ponderata dei tre segmenti
    bond_tilt = round(
        _TILT.get(bond_sov_view, 0) * 0.4 +
        _TILT.get(bond_corp_view, 0) * 0.4 +
        _TILT.get(bond_em_view, 0) * 0.2
    )
    # Commodities impatta i bilanciati/alternativi
    comm_tilt = _TILT.get(comm_view, 0) * 0.3

    # Applica tilts
    w_eq   = max(5,  _BASE_WEIGHTS["Azionari"]              + eq_tilt)
    w_bond = max(10, _BASE_WEIGHTS["Obbligazionari"]         + bond_tilt)
    w_bal  = max(5,  _BASE_WEIGHTS["Bilanciati/Flessibili"]  - eq_tilt - bond_tilt + comm_tilt)

    # Normalizza a 100
    total = w_eq + w_bond + w_bal
    weights = {
        "Azionari":              round(w_eq / total * 100),
        "Obbligazionari":        round(w_bond / total * 100),
        "Bilanciati/Flessibili": round(w_bal / total * 100),
    }
    # Aggiusta arrotondamento
    diff = 100 - sum(weights.values())
    weights["Bilanciati/Flessibili"] += diff

    # ── Summary leggibile ─────────────────────────────────────────────────────
    view_labels = {
        "OVER": "Sovrappeso", "LIEVE_OVER": "Lieve sovrappeso",
        "NEUTRAL": "Neutrale", "LIEVE_UNDER": "Lieve sottopeso", "UNDER": "Sottopeso"
    }
    summary = (
        f"Equity: {view_labels.get(eq_dev_view,'Neutrale')} | "
        f"Bond Sov: {view_labels.get(bond_sov_view,'Neutrale')} | "
        f"Bond Corp: {view_labels.get(bond_corp_view,'Neutrale')} | "
        f"Bond EM: {view_labels.get(bond_em_view,'Neutrale')} | "
        f"Commodities: {view_labels.get(comm_view,'Neutrale')}"
        + (f" | {bond_pref}" if bond_pref else "")
    )

    return {
        "date":            date_str,
        "equity_view":     eq_dev_view,
        "equity_em_view":  eq_em_view,
        "bond_sov_view":   bond_sov_view,
        "bond_corp_view":  bond_corp_view,
        "bond_em_view":    bond_em_view,
        "comm_view":       comm_view,
        "bond_pref":       bond_pref,
        "weights":         weights,
        "summary":         summary,
        "raw_views":       {
            "Equity Dev": eq_dev_view, "Equity EM": eq_em_view,
            "Bond Sov": bond_sov_view, "Bond Corp": bond_corp_view,
            "Bond EM": bond_em_view, "Commodities": comm_view,
        }
    }
