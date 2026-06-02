# -*- coding: utf-8 -*-
"""Export portafoglio nel formato Excel model-portfolios_compositions-template."""
import io
import datetime
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

_TEMPLATE = Path(__file__).parent.parent / "data" / "model_portfolio_template.xlsx"
_BLUE = "1F4E79"


def export_portfolio_excel(funds: list[dict], portfolio_name: str = "") -> bytes:
    """
    Genera un file Excel nel formato model-portfolios_compositions-template.
    Colonne: Composition date | ISIN | Instrument name | Weight
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Compositions"

    today = datetime.date.today().strftime("%d/%m/%Y")

    # ── Header riga 0 (descrizioni formato) ────────────────────────────────────
    fmt_headers = [
        "\n\n\n\n\nDate input DD/MM/AAAA",
        "Free entry input (Mandatory)",
        "Not completable input",
        "Numeric input (Mandatory)\n     Values admitted: from 0 to 100\n     Max. 4 decimals admitted",
    ]
    col_widths = [22, 20, 55, 18]

    for col, (hdr, w) in enumerate(zip(fmt_headers, col_widths), 1):
        c = ws.cell(row=1, column=col, value=hdr)
        c.font = Font(bold=True, color="FFFFFF", name="Calibri", size=9)
        c.fill = PatternFill("solid", fgColor=_BLUE)
        c.alignment = Alignment(wrap_text=True, vertical="bottom", horizontal="center")
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.row_dimensions[1].height = 80

    # ── Header riga 1 (nomi colonne) ───────────────────────────────────────────
    col_names = ["Composition date", "ISIN", "", "Weight"]
    for col, name in enumerate(col_names, 1):
        c = ws.cell(row=2, column=col, value=name)
        c.font = Font(bold=True, name="Calibri", size=10)
        c.fill = PatternFill("solid", fgColor="D9E1F2")
        c.alignment = Alignment(horizontal="center", vertical="center")
        bd = Side(style="thin", color="4472C4")
        c.border = Border(bottom=bd, top=bd, left=bd, right=bd)
    ws.row_dimensions[2].height = 18

    # ── Dati fondi ─────────────────────────────────────────────────────────────
    # Ordina per bucket poi peso decrescente
    funds_sorted = sorted(funds, key=lambda x: (x.get("bucket",""), -x.get("peso", 0)))

    # Normalizza pesi a 100 con 4 decimali
    total_raw = sum(float(f.get("peso", 0)) for f in funds_sorted)
    scale = 100.0 / total_raw if total_raw > 0 else 1.0

    for i, f in enumerate(funds_sorted):
        row = i + 3
        isin  = str(f.get("ISIN", "")).strip()
        nome  = str(f.get("nome", "")).strip()[:100]
        peso  = round(float(f.get("peso", 0)) * scale, 2)

        # Colonne: Data | ISIN | (vuota) | Peso — righe bianche senza colore
        cells_data = [today, isin, "", peso]
        for col, val in enumerate(cells_data, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.font = Font(name="Calibri", size=10)
            c.alignment = Alignment(vertical="center",
                                    horizontal="center" if col in (1, 2, 4) else "left")
            if col == 4:
                c.number_format = '0.00'
        ws.row_dimensions[row].height = 16

    # Nessuna riga totale

    # ── Foglio Datos (date disponibili) ────────────────────────────────────────
    ws2 = wb.create_sheet("Datos")
    ws2["A1"] = "Composition date"
    ws2["A1"].font = Font(bold=True)
    ws2["A2"] = today

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
