# -*- coding: utf-8 -*-
"""Generazione PDF scheda fondo con ReportLab."""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from .config import COL, COLOR_PRIMARY, COLOR_ACCENT


def _pct(val):
    if val is None or (hasattr(val, '__class__') and val.__class__.__name__ == 'float' and str(val) == 'nan'):
        return "—"
    try:
        return f"{float(val)*100:.2f}%"
    except Exception:
        return str(val) if val else "—"


def _val(val):
    if val is None or (isinstance(val, float) and str(val) == 'nan'):
        return "—"
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "") else "—"


def _stars(rating):
    try:
        n = int(float(rating))
        return "★" * n + "☆" * (5 - n)
    except Exception:
        return "—"


_PRIMARY  = rl_colors.HexColor(COLOR_PRIMARY)
_ACCENT   = rl_colors.HexColor(COLOR_ACCENT)
_LIGHT    = rl_colors.HexColor("#EBF2FA")
_WHITE    = rl_colors.white
_DARK     = rl_colors.HexColor("#1A202C")
_GRAY     = rl_colors.HexColor("#718096")
_POS      = rl_colors.HexColor("#059669")
_NEG      = rl_colors.HexColor("#DC2626")


def generate_fund_pdf(row: dict, include_quantalys: bool = False) -> bytes:
    """Genera il PDF per un singolo fondo. row = dict con i dati."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm
    )
    styles = getSampleStyleSheet()

    S_TITLE  = ParagraphStyle("title",  fontSize=14, fontName="Helvetica-Bold",
                               textColor=_WHITE, spaceAfter=4, leading=18)
    S_SUB    = ParagraphStyle("sub",    fontSize=9,  fontName="Helvetica",
                               textColor=_WHITE, spaceAfter=0)
    S_LABEL  = ParagraphStyle("label",  fontSize=7.5, fontName="Helvetica-Bold",
                               textColor=_GRAY, spaceBefore=2)
    S_VALUE  = ParagraphStyle("value",  fontSize=9,  fontName="Helvetica",
                               textColor=_DARK)
    S_LINK   = ParagraphStyle("link",   fontSize=9,  fontName="Helvetica",
                               textColor=_ACCENT)
    S_SECTION= ParagraphStyle("section",fontSize=9,  fontName="Helvetica-Bold",
                               textColor=_WHITE, spaceAfter=0)

    story = []

    # ── HEADER ────────────────────────────────────────────────────────────────
    nome  = _val(row.get(COL["nome"]))
    house = _val(row.get(COL["house"]))
    isin  = _val(row.get(COL["isin"]))

    header_data = [[
        Paragraph(nome, S_TITLE),
        ""
    ], [
        Paragraph(f"{house}  |  ISIN: {isin}", S_SUB),
        Paragraph(_stars(row.get(COL["rating"])), ParagraphStyle(
            "stars", fontSize=16, textColor=rl_colors.HexColor("#F59E0B"),
            alignment=2))
    ]]
    header_table = Table(header_data, colWidths=["80%", "20%"])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _PRIMARY),
        ("PADDING",    (0, 0), (-1, -1), 8),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("SPAN",       (0, 0), (1, 0)),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3*cm))

    # ── SEZIONE: Caratteristiche ──────────────────────────────────────────────
    def section_header(title):
        t = Table([[Paragraph(title, S_SECTION)]], colWidths=["100%"])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
            ("PADDING",    (0, 0), (-1, -1), 5),
        ]))
        return t

    def info_row(pairs):
        """pairs = list of (label, value) tuples, displayed in a grid."""
        cells = []
        for label, value in pairs:
            cells.append([
                Paragraph(label, S_LABEL),
                Paragraph(str(value), S_VALUE)
            ])
        # Affianca in colonne da 2
        rows = []
        for i in range(0, len(cells), 2):
            row_pair = cells[i:i+2]
            if len(row_pair) == 1:
                row_pair.append(["", ""])
            rows.append([row_pair[0][0], row_pair[0][1], row_pair[1][0], row_pair[1][1]])
        t = Table(rows, colWidths=["22%", "28%", "22%", "28%"])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _LIGHT),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_LIGHT, _WHITE]),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN",  (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#CBD5E0")),
        ]))
        return t

    story.append(section_header("📋  CARATTERISTICHE"))
    story.append(info_row([
        ("Classificazione",    _val(row.get(COL["classif"]))),
        ("Acc. / Distr.",      _val(row.get(COL["acc_dist"]))),
        ("Classe",             _val(row.get(COL["classe"]))),
        ("Divisa",             _val(row.get(COL["divisa"]))),
        ("Trasferibile",       _val(row.get(COL["trasfx"]))),
        ("Collocabile",        _val(row.get(COL["collocabile"]))),
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ── SEZIONE: Commissioni ──────────────────────────────────────────────────
    story.append(section_header("💶  COMMISSIONI"))
    story.append(info_row([
        ("Ingresso",            _pct(row.get(COL["comm_ingresso"]))),
        ("Uscita",              _pct(row.get(COL["comm_uscita"]))),
        ("Gestione",            _pct(row.get(COL["comm_gest"]))),
        ("Retrocessione Banca", _pct(row.get(COL["retro"]))),
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ── SEZIONE: Performance ──────────────────────────────────────────────────
    story.append(section_header("📈  PERFORMANCE"))

    def perf_color(val):
        try:
            return _POS if float(val) >= 0 else _NEG
        except Exception:
            return _DARK

    perf_data = [
        [Paragraph("YTD", S_LABEL), Paragraph("1 Anno", S_LABEL),
         Paragraph("3 Anni", S_LABEL), Paragraph("2024", S_LABEL),
         Paragraph("2023", S_LABEL), Paragraph("2022", S_LABEL)],
        [
            Paragraph(_pct(row.get(COL["perf_ytd"])),
                      ParagraphStyle("pv", fontSize=10, fontName="Helvetica-Bold",
                                     textColor=perf_color(row.get(COL["perf_ytd"])))),
            Paragraph(_pct(row.get(COL["perf_1y"])),
                      ParagraphStyle("pv", fontSize=10, fontName="Helvetica-Bold",
                                     textColor=perf_color(row.get(COL["perf_1y"])))),
            Paragraph(_pct(row.get(COL["perf_3y"])),
                      ParagraphStyle("pv", fontSize=10, fontName="Helvetica-Bold",
                                     textColor=perf_color(row.get(COL["perf_3y"])))),
            Paragraph(_pct(row.get(COL["perf_2024"])),
                      ParagraphStyle("pv", fontSize=10, fontName="Helvetica-Bold",
                                     textColor=perf_color(row.get(COL["perf_2024"])))),
            Paragraph(_pct(row.get(COL["perf_2023"])),
                      ParagraphStyle("pv", fontSize=10, fontName="Helvetica-Bold",
                                     textColor=perf_color(row.get(COL["perf_2023"])))),
            Paragraph(_pct(row.get(COL["perf_2022"])),
                      ParagraphStyle("pv", fontSize=10, fontName="Helvetica-Bold",
                                     textColor=perf_color(row.get(COL["perf_2022"])))),
        ]
    ]
    perf_table = Table(perf_data, colWidths=["16.66%"]*6)
    perf_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _LIGHT),
        ("BACKGROUND", (0, 1), (-1, 1), _WHITE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#CBD5E0")),
    ]))
    story.append(perf_table)
    story.append(Spacer(1, 0.3*cm))

    # ── SEZIONE: Rischio ──────────────────────────────────────────────────────
    story.append(section_header("⚡  RISCHIO"))
    story.append(info_row([
        ("Volatilità 1 anno", _pct(row.get(COL["volatilita"]))),
        ("Rating FIDA",       _stars(row.get(COL["rating"]))),
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ── SEZIONE: Link ─────────────────────────────────────────────────────────
    fd_url = _val(row.get(COL["url_fondidoc"]))
    qly_url = _val(row.get(COL["url_quantalys"]))

    if fd_url != "—" or qly_url != "—":
        story.append(section_header("🔗  SCHEDE DI APPROFONDIMENTO"))
        link_rows = []
        if fd_url != "—":
            link_rows.append([
                Paragraph("FondiDoc (scheda, rendimenti, rating FIDA):", S_LABEL),
                Paragraph(f'<link href="{fd_url}" color="#2E86AB">{fd_url[:80]}</link>', S_LINK)
            ])
        if qly_url != "—":
            link_rows.append([
                Paragraph("Quantalys (analisi, categoria):", S_LABEL),
                Paragraph(f'<link href="{qly_url}" color="#2E86AB">{qly_url[:80]}</link>', S_LINK)
            ])
        link_table = Table(link_rows, colWidths=["30%", "70%"])
        link_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _LIGHT),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#CBD5E0")),
        ]))
        story.append(link_table)

    # ── SEZIONE: Grafico Quantalys ────────────────────────────────────────────
    if include_quantalys and qly_url != "—":
        from .quantalys_capture import capture_quantalys_chart
        from reportlab.platypus import Image as _RLImage
        import io as _io
        png_bytes = capture_quantalys_chart(qly_url)
        if png_bytes:
            from PIL import Image as _PILImage
            pil_img = _PILImage.open(_io.BytesIO(png_bytes))
            w_px, h_px = pil_img.size
            aspect = h_px / w_px if w_px > 0 else 0.5
            page_w = A4[0] - 3.6*cm
            img_w  = page_w
            img_h  = img_w * aspect
            img_io = _io.BytesIO(png_bytes)
            story.append(section_header("📊  ANALISI QUANTALYS · Serie Storica & Performance"))
            story.append(_RLImage(img_io, width=img_w, height=img_h))
            story.append(Spacer(1, 0.3*cm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY))
    story.append(Paragraph(
        "Documento generato automaticamente. Dati da fondidoc.it e file BPER. "
        "I rendimenti passati non garantiscono risultati futuri.",
        ParagraphStyle("footer", fontSize=7, textColor=_GRAY, alignment=1)
    ))

    doc.build(story)
    return buf.getvalue()
