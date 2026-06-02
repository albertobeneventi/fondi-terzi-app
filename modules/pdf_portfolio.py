# -*- coding: utf-8 -*-
"""
PDF portafoglio fondi terze parti — stile Azimut Portfolio Analyzer.
Genera: barra accent, title block, KPI, torta allocazione, tabella fondi,
        scheda dettaglio per fondo con metriche + link.
"""
import io
import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, HRFlowable, KeepTogether, PageBreak
)

from .config import COL

# ── Colori ────────────────────────────────────────────────────────────────────
_DARK    = rl_colors.HexColor("#0D1B2A")
_BLUE    = rl_colors.HexColor("#1F4E79")
_GOLD    = rl_colors.HexColor("#C9A84C")
_LIGHT   = rl_colors.HexColor("#F8FAFC")
_BORDER  = rl_colors.HexColor("#E2E8F0")
_GRAY    = rl_colors.HexColor("#64748B")
_POS     = rl_colors.HexColor("#059669")
_NEG     = rl_colors.HexColor("#DC2626")
_WHITE   = rl_colors.white

_BUCKET_COLORS = {
    "Azionari":             "#1B4FBB",
    "Obbligazionari":       "#2D9D78",
    "Bilanciati/Flessibili":"#C9A84C",
    "Altro":                "#94A3B8",
}

PW = 19 * cm   # larghezza stampabile A4 con margini 1cm


def _pct(v):
    if v is None:
        return "—"
    try:
        return f"{float(v)*100:.2f}%"
    except Exception:
        return "—"


def _perf_color(v):
    try:
        return _POS if float(v) >= 0 else _NEG
    except Exception:
        return _GRAY


def _stars(rating):
    try:
        n = int(float(rating))
        return "★" * n + "☆" * (5 - n)
    except Exception:
        return "—"


def _pie_chart(funds: list[dict]) -> bytes:
    """Genera la torta dell'allocazione per bucket."""
    bucket_totals: dict[str, float] = {}
    for f in funds:
        b = f.get("bucket", "Altro")
        bucket_totals[b] = bucket_totals.get(b, 0) + f.get("peso", 0)

    labels  = list(bucket_totals.keys())
    sizes   = [bucket_totals[b] for b in labels]
    colors  = [_BUCKET_COLORS.get(b, "#94A3B8") for b in labels]

    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, colors=colors,
        autopct="%1.1f%%", startangle=90,
        pctdistance=0.75,
        wedgeprops={"linewidth": 1.5, "edgecolor": "white"}
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color("white")
        at.set_fontweight("bold")
    ax.set_aspect("equal")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor="white", transparent=False)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_portfolio_pdf(
    portfolio_name: str,
    scenario: str,
    funds: list[dict],
    include_fund_cards: bool = True,
) -> bytes:
    """
    Genera il PDF del portafoglio.
    funds: lista di dict da portfolio_manager.suggest_portfolio / save_portfolio.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.0*cm, rightMargin=1.0*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    ss = getSampleStyleSheet()
    def S(name, **kw):
        return ParagraphStyle(name, parent=ss["Normal"], **kw)

    T   = S("T",   fontName="Helvetica-Bold",  fontSize=20, textColor=_DARK,  spaceAfter=4, leading=26)
    EY  = S("EY",  fontName="Helvetica",       fontSize=8,  textColor=_GRAY,  spaceAfter=4, letterSpacing=1.2)
    SU  = S("SU",  fontName="Helvetica",       fontSize=10, textColor=_GRAY,  spaceAfter=4)
    SC  = S("SC",  fontName="Helvetica-Bold",  fontSize=10, textColor=_DARK,  spaceBefore=12, spaceAfter=6)
    SM  = S("SM",  fontName="Helvetica",       fontSize=7.5, textColor=rl_colors.HexColor("#1E293B"), leading=11, alignment=1)
    SML = S("SML", fontName="Helvetica",       fontSize=7.5, textColor=rl_colors.HexColor("#1E293B"), leading=11, alignment=0)
    HDR = S("HDR", fontName="Helvetica-Bold",  fontSize=7.5, textColor=_WHITE, leading=11, alignment=1)
    FS  = S("FS",  fontName="Helvetica-Bold",  fontSize=11, textColor=_DARK,  spaceBefore=4, spaceAfter=2)
    FK  = S("FK",  fontName="Helvetica",       fontSize=7.5, textColor=_GRAY,  spaceAfter=2)
    LK  = S("LK",  fontName="Helvetica",       fontSize=7.5, textColor=rl_colors.HexColor("#1B4FBB"), spaceAfter=2)
    KC  = S("KC",  fontName="Helvetica",       fontSize=8.5, textColor=rl_colors.HexColor("#1E293B"), leading=13, alignment=1)
    FT  = S("FT",  fontName="Helvetica-Oblique", fontSize=7, textColor=_GRAY, leading=10)
    LG  = S("LG",  fontName="Helvetica",       fontSize=8,  textColor=rl_colors.HexColor("#1E293B"), leading=11)

    story = []

    # ── ACCENT BAR ───────────────────────────────────────────────────────────
    story.append(Table([[""]], colWidths=[PW], rowHeights=[10],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _DARK),
            ("LINEBELOW",  (0, 0), (-1, -1), 3, _GOLD),
        ])))
    story.append(Spacer(1, 12))

    # ── TITLE BLOCK ──────────────────────────────────────────────────────────
    story.append(Paragraph("FONDI SOCIETÀ TERZE", EY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(portfolio_name, T))
    story.append(Paragraph(
        f"{scenario}  ·  Dati al {datetime.date.today().strftime('%d %B %Y')}", SU))
    story.append(HRFlowable(width="100%", thickness=0.8, color=_BORDER, spaceAfter=12))

    # ── KPI ──────────────────────────────────────────────────────────────────
    n_fondi = len(funds)
    total_peso = sum(f.get("peso", 0) for f in funds)

    # Medie per bucket
    bucket_totals: dict[str, float] = {}
    for f in funds:
        b = f.get("bucket", "Altro")
        bucket_totals[b] = bucket_totals.get(b, 0) + f.get("peso", 0)

    eq_pct  = bucket_totals.get("Azionari", 0)
    obl_pct = bucket_totals.get("Obbligazionari", 0)
    bal_pct = bucket_totals.get("Bilanciati/Flessibili", 0)

    avg_retro = sum(f["retro"] for f in funds if f.get("retro") and str(f["retro"]) not in ("nan","None")) / max(1, sum(1 for f in funds if f.get("retro") and str(f["retro"]) not in ("nan","None")))

    def kpi_cell(v, l):
        return Paragraph(
            f'<font size="18"><b>{v}</b></font><br/>'
            f'<font size="8" color="#64748B">{l}</font>', KC)

    kpi = Table([[
        kpi_cell(str(n_fondi), "Fondi"),
        kpi_cell(f"{eq_pct:.1f}%", "Azionario"),
        kpi_cell(f"{obl_pct:.1f}%", "Obbligazionario"),
        kpi_cell(f"{avg_retro*100:.2f}%", "Retro. media"),
    ]], colWidths=[PW / 4] * 4, rowHeights=[1.9 * cm])
    kpi.setStyle(TableStyle([
        ("BOX",        (0, 0), (-1, -1), 0.8, _BORDER),
        ("INNERGRID",  (0, 0), (-1, -1), 0.8, _BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), _LIGHT),
        ("PADDING",    (0, 0), (-1, -1), 12),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(kpi)
    story.append(Spacer(1, 10))

    # ── TORTA ALLOCAZIONE ────────────────────────────────────────────────────
    story.append(Paragraph("Allocazione del Portafoglio", SC))
    PIE_W = 6.5 * cm
    LEG_W = PW - PIE_W - 0.5 * cm
    DOT_W = 0.3 * cm

    pie_png = _pie_chart(funds)
    pie_img = RLImage(io.BytesIO(pie_png), width=PIE_W, height=PIE_W)

    # Legenda fondi
    leg_rows = []
    for f in sorted(funds, key=lambda x: -x.get("peso", 0)):
        color = _BUCKET_COLORS.get(f.get("bucket", "Altro"), "#94A3B8")
        dot = Table([[""]], colWidths=[DOT_W], rowHeights=[DOT_W])
        dot.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(color))]))
        nome_short = f.get("nome", "")[:45]
        leg_rows.append([dot,
                         Paragraph(nome_short, LG),
                         Paragraph(f"{f.get('peso', 0):.1f}%", LG)])

    leg_table = Table(leg_rows, colWidths=[DOT_W, LEG_W - 2.0 * cm, 1.8 * cm])
    leg_table.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_LIGHT, _WHITE]),
    ]))

    pie_layout = Table([[pie_img, leg_table]],
                       colWidths=[PIE_W + 0.5 * cm, LEG_W])
    pie_layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(pie_layout)
    story.append(Spacer(1, 10))

    # ── TABELLA RIASSUNTIVA ──────────────────────────────────────────────────
    story.append(Paragraph("Composizione del Portafoglio", SC))

    tbl_header = [
        Paragraph("Fondo", HDR), Paragraph("Bucket", HDR),
        Paragraph("Peso %", HDR), Paragraph("Rating", HDR),
        Paragraph("Retro.", HDR), Paragraph("Perf. 1Y", HDR),
        Paragraph("Perf. 3Y", HDR),
    ]
    tbl_data = [tbl_header]
    for f in sorted(funds, key=lambda x: (x.get("bucket", ""), -x.get("peso", 0))):
        p1 = f.get("perf_1y")
        p3 = f.get("perf_3y")
        r  = f.get("retro")

        def _pc(v):
            if v is None or str(v) in ("nan", "None"): return Paragraph("—", SM)
            try:
                pv = float(v) * 100
                color = "#059669" if pv >= 0 else "#DC2626"
                sign  = "+" if pv >= 0 else ""
                return Paragraph(f'<font color="{color}">{sign}{pv:.1f}%</font>', SM)
            except Exception:
                return Paragraph("—", SM)

        tbl_data.append([
            Paragraph(f.get("nome", "")[:42], SML),
            Paragraph(f.get("bucket", "")[:14], SM),
            Paragraph(f"{f.get('peso', 0):.1f}%", SM),
            Paragraph(_stars(f.get("rating")), SM),
            _pc(r),
            _pc(p1),
            _pc(p3),
        ])

    col_ws = [6.5*cm, 2.8*cm, 1.5*cm, 1.4*cm, 1.6*cm, 1.6*cm, 1.6*cm]
    tbl = Table(tbl_data, colWidths=col_ws, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_LIGHT, _WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, _BORDER),
        ("PADDING",       (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tbl)

    # ── SCHEDE FONDI (opzionale) ─────────────────────────────────────────────
    if include_fund_cards and funds:
        story.append(PageBreak())
        story.append(Paragraph("Dettaglio Fondi", SC))

        for f in funds:
            fd_url  = f.get("url_fondidoc", "")
            qly_url = f.get("url_quantalys", "")

            card = [
                Spacer(1, 6),
                Paragraph(f.get("nome", ""), FS),
                Paragraph(
                    f"Casa: {f.get('house', '—')}  ·  ISIN: {f.get('ISIN', '—')}  ·  "
                    f"Bucket: {f.get('bucket', '—')}  ·  Peso: {f.get('peso', 0):.1f}%", FK),
                Spacer(1, 4),
            ]

            # Metriche in riga
            met_data = [[
                Paragraph("Rating FIDA", HDR), Paragraph("Retro.", HDR),
                Paragraph("Perf. 1Y", HDR), Paragraph("Perf. 3Y", HDR),
                Paragraph("Volatilità", HDR),
            ], [
                Paragraph(_stars(f.get("rating")), SM),
                Paragraph(_pct(f.get("retro")), SM),
                Paragraph(_pct(f.get("perf_1y")), SM),
                Paragraph(_pct(f.get("perf_3y")), SM),
                Paragraph("—", SM),
            ]]
            met_tbl = Table(met_data, colWidths=[PW / 5] * 5)
            met_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), _BLUE),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_LIGHT]),
                ("GRID",          (0, 0), (-1, -1), 0.4, _BORDER),
                ("PADDING",       (0, 0), (-1, -1), 5),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ]))
            card.append(met_tbl)

            # Classificazione
            if f.get("classif") and str(f["classif"]) not in ("nan", "None", ""):
                card.append(Spacer(1, 4))
                card.append(Paragraph(f"Classificazione: {f['classif']}", FK))

            # Link
            links = []
            if fd_url and fd_url.lower() not in ("nan", "none", ""):
                links.append(Paragraph(
                    f'FondiDoc: <link href="{fd_url}" color="#1B4FBB">{fd_url[:70]}</link>', LK))
            if qly_url and qly_url.lower() not in ("nan", "none", ""):
                links.append(Paragraph(
                    f'Quantalys: <link href="{qly_url}" color="#1B4FBB">{qly_url[:70]}</link>', LK))
            if links:
                card.append(Spacer(1, 4))
                card += links

            card.append(HRFlowable(width="100%", thickness=0.4, color=_BORDER, spaceAfter=2))
            story.append(KeepTogether(card))

    # ── FOOTER ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.0 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY))
    story.append(Paragraph(
        "Documento generato automaticamente. Dati da fondidoc.it. "
        "I rendimenti passati non garantiscono risultati futuri. "
        "Portafoglio generato ai soli fini illustrativi.",
        FT))

    doc.build(story)
    return buf.getvalue()
