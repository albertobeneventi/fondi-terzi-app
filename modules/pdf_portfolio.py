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
    include_quantalys: bool = False,
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

    avg_perf_1y = sum(float(f["perf_1y"]) for f in funds
                      if f.get("perf_1y") and str(f["perf_1y"]) not in ("nan","None","")) / \
                  max(1, sum(1 for f in funds if f.get("perf_1y") and str(f["perf_1y"]) not in ("nan","None","")))

    def kpi_cell(v, l):
        return Paragraph(
            f'<font size="18"><b>{v}</b></font><br/>'
            f'<font size="8" color="#64748B">{l}</font>', KC)

    kpi = Table([[
        kpi_cell(str(n_fondi), "Fondi"),
        kpi_cell(f"{eq_pct:.1f}%", "Azionario"),
        kpi_cell(f"{obl_pct:.1f}%", "Obbligazionario"),
        kpi_cell(f"{avg_perf_1y*100:.1f}%", "Perf. 1Y media"),
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
    PIE_W = 6.0 * cm
    LEG_W = PW - PIE_W - 0.5 * cm
    DOT_W = 0.4 * cm

    pie_png = _pie_chart(funds)
    pie_img = RLImage(io.BytesIO(pie_png), width=PIE_W, height=PIE_W)

    # Legenda fondi (senza pallino separato — colorato direttamente nella cella)
    leg_rows = []
    for f in sorted(funds, key=lambda x: -x.get("peso", 0)):
        color = _BUCKET_COLORS.get(f.get("bucket", "Altro"), "#94A3B8")
        dot = Table([[""]], colWidths=[DOT_W], rowHeights=[DOT_W + 0.1*cm])
        dot.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor(color)),
            ("LEFTPADDING",  (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ]))
        nome_short = f.get("nome", "")[:45]
        isin_short = f.get("ISIN", "")
        leg_rows.append([dot,
                         Paragraph(f"{nome_short}<br/><font size='6' color='#94A3B8'>{isin_short}</font>", LG),
                         Paragraph(f"{f.get('peso', 0):.1f}%", LG)])

    leg_table = Table(leg_rows, colWidths=[DOT_W, LEG_W - 1.8*cm, 1.6*cm])
    leg_table.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_LIGHT, _WHITE]),
        ("LEFTPADDING",  (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 0),
    ]))

    pie_layout = Table([[pie_img, leg_table]],
                       colWidths=[PIE_W + 0.5 * cm, LEG_W])
    pie_layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(pie_layout)
    story.append(Spacer(1, 10))

    # ── TABELLA COMPOSIZIONE — stile identico ad Azimut Portfolio Analyzer ────
    story.append(Paragraph("Composizione del Portafoglio", SC))

    # Stili helper
    SMC = ParagraphStyle("SMC", fontName="Helvetica", fontSize=7.5,
                         textColor=rl_colors.HexColor("#1E293B"), leading=11, alignment=1)
    WH  = ParagraphStyle("WH",  fontName="Helvetica-Bold", fontSize=7.5,
                         textColor=_WHITE, leading=11, alignment=0)
    WHC = ParagraphStyle("WHC", fontName="Helvetica-Bold", fontSize=7.5,
                         textColor=_WHITE, leading=11, alignment=1)
    HDRC= ParagraphStyle("HDRC",fontName="Helvetica-Bold", fontSize=7.5,
                         textColor=_WHITE, leading=11, alignment=1)

    # Colori FIDA badge (come app Azimut)
    _FIDA_BG = {"5": "#166534", "4": "#15803d", "3": "#16a34a"}

    def _fida_para(val):
        v = str(val).strip()
        if v in _FIDA_BG:
            return Paragraph(v, ParagraphStyle(f"FP{v}", fontName="Helvetica-Bold",
                fontSize=7.5, textColor=_WHITE, leading=11, alignment=1))
        if v in ("1","2"):
            return Paragraph(v, ParagraphStyle(f"FP{v}", fontName="Helvetica-Bold",
                fontSize=7.5, textColor=_DARK, leading=11, alignment=1))
        return Paragraph("—", SM)

    def _pc(v):
        if v is None or str(v) in ("nan","None",""): return Paragraph("—", SMC)
        try:
            pv = float(v) * 100
            col = "#059669" if pv >= 0 else "#DC2626"
            sgn = "+" if pv >= 0 else ""
            return Paragraph(f'<font color="{col}">{sgn}{pv:.1f}%</font>', SMC)
        except Exception:
            return Paragraph("—", SMC)

    # Calcola % Az/Obb approssimata dal bucket
    _AZ_OBB = {"Azionari":(1.0,0.0),"Obbligazionari":(0.0,1.0),
               "Bilanciati/Flessibili":(0.5,0.5),"Altro":(0.3,0.7)}

    # Righe portafoglio (medie ponderate)
    w_az_ptf = sum(f.get("peso",0)*_AZ_OBB.get(f.get("bucket","Altro"),(0.5,0.5))[0]
                   for f in funds) / max(total_peso, 1)
    w_ob_ptf = sum(f.get("peso",0)*_AZ_OBB.get(f.get("bucket","Altro"),(0.5,0.5))[1]
                   for f in funds) / max(total_peso, 1)

    # Header — colonne: Fondo | ISIN | Peso | %Az | %Obb | Cat.FIDA | FIDArtg | Perf1Y | Perf3Y
    alloc_hdr = [
        Paragraph("<b>Fondo</b>",        HDR),
        Paragraph("<b>ISIN</b>",         HDR),
        Paragraph("<b>Peso</b>",         HDR),
        Paragraph("<b>% Az.</b>",       HDRC),
        Paragraph("<b>% Obb.</b>",      HDRC),
        Paragraph("<b>Cat. FIDA</b>",    HDR),
        Paragraph("<b>FIDArtg</b>",     HDRC),
        Paragraph("<b>Perf. 1Y</b>",    HDRC),
        Paragraph("<b>Perf. 3Y</b>",    HDRC),
    ]
    # Riga portafoglio
    alloc_ptf = [
        Paragraph(f"<b>◆ PORTAFOGLIO {portfolio_name.upper()[:25]}</b>", WH),
        Paragraph("", WH),
        Paragraph("<b>100%</b>", WH),
        Paragraph(f"<b>{w_az_ptf*100:.1f}%</b>", WHC),
        Paragraph(f"<b>{w_ob_ptf*100:.1f}%</b>", WHC),
        Paragraph("", WH), Paragraph("", WH), Paragraph("", WH), Paragraph("", WH),
    ]

    alloc_rows = []
    fida_vals  = []
    for f in sorted(funds, key=lambda x: (x.get("bucket",""), -x.get("peso",0))):
        az_p, ob_p = _AZ_OBB.get(f.get("bucket","Altro"), (0.5, 0.5))
        fida_val   = str(f.get("rating","") or "—").strip().split(".")[0]
        fida_vals.append(fida_val)
        cat = str(f.get("classif","") or "—")[:22]
        alloc_rows.append([
            Paragraph(f.get("nome","")[:42],                    SML),
            Paragraph(f.get("ISIN",""),                         SM),
            Paragraph(f"{f.get('peso',0):.1f}%",               SM),
            Paragraph(f"{az_p*100:.0f}%",                      SMC),
            Paragraph(f"{ob_p*100:.0f}%",                      SMC),
            Paragraph(cat,                                       SM),
            _fida_para(fida_val),
            _pc(f.get("perf_1y")),
            _pc(f.get("perf_3y")),
        ])

    # Fondo(3.3) ISIN(2.4) Peso(1.1) %Az(1.3) %Obb(1.3) Cat(2.2) FIDArtg(1.3) P1Y(1.5) P3Y(1.5) = 15.9cm
    col_ws = [3.3*cm, 2.4*cm, 1.1*cm, 1.3*cm, 1.3*cm, 2.2*cm, 1.3*cm, 1.5*cm, 1.5*cm]

    tbl = Table([alloc_hdr, alloc_ptf] + alloc_rows, colWidths=col_ws, repeatRows=1)

    # Stile base
    tbl_style = [
        ("BACKGROUND",    (0, 0), (-1,  0), _BLUE),
        ("BACKGROUND",    (0, 1), (-1,  1), _DARK),
        ("ROWBACKGROUNDS",(0, 2), (-1, -1), [_LIGHT, _WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, _BORDER),
        ("PADDING",       (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (2, 0), (-1, -1), "CENTER"),
    ]
    # Badge FIDA colorati per riga
    for fi, fv in enumerate(fida_vals):
        bg = _FIDA_BG.get(fv)
        if bg:
            tbl_style.append(("BACKGROUND", (6, fi+2), (6, fi+2), rl_colors.HexColor(bg)))

    tbl.setStyle(TableStyle(tbl_style))
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
                    f"Bucket: {f.get('bucket', '—')}  ·  Peso: {f.get('peso', 0):.1f}%  ·  "
                    f"Acc./Distr.: {f.get('acc_dist','—')}", FK),
                Spacer(1, 4),
            ]

            # Classificazione FIDA
            if f.get("classif") and str(f["classif"]) not in ("nan","None",""):
                card.append(Paragraph(
                    f"Cat. FIDA: {f['classif']}", FK))
                card.append(Spacer(1, 4))

            # Metriche: stile tabella Azimut (senza retro)
            met_data = [[
                Paragraph("Rating FIDA", HDR),
                Paragraph("Perf. YTD", HDR),
                Paragraph("Perf. 1Y", HDR),
                Paragraph("Perf. 3Y", HDR),
                Paragraph("Perf. 2024", HDR),
                Paragraph("Perf. 2023", HDR),
                Paragraph("Volatilità 1Y", HDR),
            ], [
                Paragraph(_stars(f.get("rating")), SM),
                _pc(f.get("perf_ytd")),
                _pc(f.get("perf_1y")),
                _pc(f.get("perf_3y")),
                _pc(f.get("perf_2024")),
                _pc(f.get("perf_2023")),
                Paragraph(_pct(f.get("volatilita")), SM),
            ]]
            met_tbl = Table(met_data, colWidths=[PW / 7] * 7)
            met_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), _BLUE),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_LIGHT]),
                ("GRID",          (0, 0), (-1, -1), 0.4, _BORDER),
                ("PADDING",       (0, 0), (-1, -1), 4),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ]))
            card.append(met_tbl)

            # Grafico Quantalys (come app Azimut) — solo se richiesto esplicitamente
            if include_quantalys:
                card.append(Spacer(1, 6))
                card.append(Paragraph("<b>Analisi Quantalys</b> · Serie Storica & Performance", FK))
                if not qly_url or qly_url.lower() in ("nan","none",""):
                    card.append(Paragraph(
                        '<font color="#94A3B8"><i>URL Quantalys non disponibile per questo fondo.</i></font>', FK))
                else:
                    try:
                        from .quantalys_capture import capture_quantalys_chart, qtl_historique_url
                        from PIL import Image as _PILImage
                        from reportlab.platypus import Image as _RLImg
                        hist_url = qtl_historique_url(qly_url)
                        card.append(Paragraph(
                            f'<link href="{hist_url}" color="#2E86AB">{hist_url[:70]}</link>', FK))
                        png = capture_quantalys_chart(qly_url, force=False)
                        if png and len(png) > 1000:
                            pil = _PILImage.open(io.BytesIO(png))
                            w_px, h_px = pil.size
                            aspect = h_px / w_px if w_px > 0 else 0.5
                            img_w = PW
                            img_h = min(img_w * aspect, 7 * cm)
                            card.append(_RLImg(io.BytesIO(png), width=img_w, height=img_h))
                        else:
                            card.append(Paragraph(
                                f'<font color="#CC0000"><i>Cattura fallita (PNG vuoto). '
                                f'Controlla connessione Playwright.</i></font>', FK))
                    except Exception as e:
                        card.append(Paragraph(
                            f'<font color="#CC0000"><i>Errore cattura: {str(e)[:120]}</i></font>', FK))

            # Link FondiDoc
            if fd_url and fd_url.lower() not in ("nan","none",""):
                card.append(Spacer(1, 4))
                card.append(Paragraph(
                    f'<link href="{fd_url}" color="#1B4FBB">Scheda FondiDoc</link>', LK))

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
