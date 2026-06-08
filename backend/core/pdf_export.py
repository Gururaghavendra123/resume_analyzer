"""
PDF Export Engine.

Generates a professional match report PDF using ReportLab.
Uses a PRINT-FRIENDLY color scheme (dark text on white background)
so the report is readable when printed or viewed in any PDF reader.
"""

import io
from datetime import datetime
from typing import List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Print-Friendly Color Palette ──────────────────────────────
WHITE        = colors.white
NEAR_WHITE   = colors.HexColor("#f8fafc")
LIGHT_GRAY   = colors.HexColor("#f1f5f9")
MID_GRAY     = colors.HexColor("#e2e8f0")
DARK_GRAY    = colors.HexColor("#475569")
TEXT_DARK    = colors.HexColor("#0f172a")  # near-black for readability
TEXT_BODY    = colors.HexColor("#334155")  # body text
TEXT_MUTED   = colors.HexColor("#64748b")  # secondary text
ACCENT       = colors.HexColor("#4f46e5")  # indigo
ACCENT_LIGHT = colors.HexColor("#6366f1")
GREEN        = colors.HexColor("#059669")
YELLOW       = colors.HexColor("#d97706")
RED          = colors.HexColor("#dc2626")
BLUE         = colors.HexColor("#2563eb")
ORANGE       = colors.HexColor("#ea580c")

GRADE_COLORS = {
    "A": GREEN,
    "B": BLUE,
    "C": YELLOW,
    "D": ORANGE,
    "F": RED,
}


def _score_color(score_pct: float) -> colors.Color:
    if score_pct >= 70:
        return GREEN
    if score_pct >= 40:
        return YELLOW
    return RED


def generate_match_report_pdf(
    results: List[dict],
    jd_title: str = "Job Description",
    job_id: str = "",
) -> bytes:
    """
    Generate a PDF match report from a list of MatchResult dicts.

    Returns raw PDF bytes.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Match Report — {jd_title}",
        author="Resume & JD Analyzer",
    )

    styles = getSampleStyleSheet()

    # ── Custom Styles (dark text on white) ─────────────────────
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=TEXT_DARK,
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=TEXT_MUTED,
        spaceAfter=2,
        alignment=TA_CENTER,
    )
    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=ACCENT,
        spaceBefore=14,
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    candidate_title_style = ParagraphStyle(
        "CandidateTitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontSize=9,
        textColor=TEXT_MUTED,
        spaceAfter=4,
        leading=13,
    )
    rec_style = ParagraphStyle(
        "Recommendation",
        parent=styles["Normal"],
        fontSize=9,
        textColor=TEXT_BODY,
        spaceAfter=6,
        leading=14,
        leftIndent=8,
        borderPad=4,
    )

    story = []

    # ── Cover Header ───────────────────────────────────────────
    story.append(Paragraph("Match Analysis Report", title_style))
    story.append(Paragraph(f"Job: {jd_title}", subtitle_style))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')} | {len(results)} candidate(s) analyzed",
        subtitle_style,
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=6 * mm))

    # ── Summary Table ──────────────────────────────────────────
    story.append(Paragraph("Executive Summary", section_heading_style))

    summary_data = [["#", "Candidate ID", "Score", "Grade", "Skills", "Exp.", "Edu.", "Projects"]]
    for i, r in enumerate(results, 1):
        ss = r.get("skills_score", {})
        es = r.get("experience_score", {})
        edu = r.get("education_score", {})
        ps = r.get("projects_score", {})
        summary_data.append([
            str(i),
            r.get("resume_id", "")[:12] + "...",
            f"{r.get('overall_score', 0):.0f}/100",
            r.get("grade", "?"),
            f"{ss.get('score', 0) * 100:.0f}%",
            f"{es.get('score', 0) * 100:.0f}%",
            f"{edu.get('score', 0) * 100:.0f}%",
            f"{ps.get('score', 0) * 100:.0f}%",
        ])

    summary_table = Table(summary_data, colWidths=[12*mm, 38*mm, 22*mm, 16*mm, 20*mm, 20*mm, 20*mm, 22*mm])
    summary_table.setStyle(TableStyle([
        # Header row — dark accent background
        ("BACKGROUND",  (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        # Data rows — light alternating backgrounds with DARK text
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("TEXTCOLOR",   (0, 1), (-1, -1), TEXT_DARK),
        ("FONTSIZE",    (0, 1), (-1, -1), 8),
        ("GRID",        (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    # Color-code the grade column
    for i, r in enumerate(results, 1):
        grade = r.get("grade", "F")
        summary_table.setStyle(TableStyle([
            ("TEXTCOLOR", (3, i), (3, i), GRADE_COLORS.get(grade, RED)),
            ("FONTNAME",  (3, i), (3, i), "Helvetica-Bold"),
        ]))

    story.append(summary_table)
    story.append(Spacer(1, 8 * mm))

    # ── Per-Candidate Detail ────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=4 * mm))
    story.append(Paragraph("Detailed Candidate Analysis", section_heading_style))

    for i, r in enumerate(results, 1):
        grade = r.get("grade", "F")
        overall = r.get("overall_score", 0)
        grade_color = GRADE_COLORS.get(grade, RED)

        # ── Candidate Header (accent bg, white text) ───────────
        candidate_id = r.get("resume_id", "unknown")
        header_data = [[
            Paragraph(f"#{i}  Candidate", candidate_title_style),
            Paragraph(
                f"<font color='white' size='14'><b>Grade {grade}</b></font>",
                ParagraphStyle("g", fontSize=14, textColor=colors.white, alignment=TA_CENTER),
            ),
            Paragraph(
                f"<font size='16'><b>{overall:.0f}</b></font><font size='8'> /100</font>",
                ParagraphStyle("s", fontSize=10, textColor=colors.white, alignment=TA_CENTER),
            ),
        ]]
        header_table = Table(header_data, colWidths=[80*mm, 40*mm, 40*mm])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
            ("ALIGN",      (0, 0), (0, 0), "LEFT"),
            ("ALIGN",      (1, 0), (-1, 0), "CENTER"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (0, 0), 12),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"Resume ID: {candidate_id}",
            ParagraphStyle("rid", fontSize=8, textColor=TEXT_MUTED),
        ))

        # ── Section Score Bars ──────────────────────────────────
        sections = [
            ("Skills",     r.get("skills_score", {})),
            ("Experience", r.get("experience_score", {})),
            ("Education",  r.get("education_score", {})),
            ("Projects",   r.get("projects_score", {})),
        ]
        for sec_name, sec_data in sections:
            pct = sec_data.get("score", 0) * 100
            bar_filled = max(1, int(pct))
            col = _score_color(pct)

            bar_data = [[
                Paragraph(
                    sec_name,
                    ParagraphStyle("bn", fontSize=8, textColor=TEXT_DARK, fontName="Helvetica-Bold"),
                ),
                Table(
                    [[""]],
                    colWidths=[bar_filled * 0.85 * mm],
                    rowHeights=[4 * mm],
                ),
                Paragraph(
                    f"{pct:.0f}%",
                    ParagraphStyle("bp", fontSize=8, textColor=col, fontName="Helvetica-Bold", alignment=TA_CENTER),
                ),
                Paragraph(sec_data.get("notes", ""), body_style),
            ]]
            bar_table = Table(bar_data, colWidths=[28*mm, 85*mm, 14*mm, 43*mm])
            bar_table.setStyle(TableStyle([
                ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND",   (1, 0), (1, 0), col),
                ("TOPPADDING",   (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
                ("LEFTPADDING",  (0, 0), (0, 0), 0),
            ]))
            story.append(bar_table)

        # ── Skills Detail ──────────────────────────────────────
        ss = r.get("skills_score", {})
        matched = ss.get("matched", [])
        partial  = ss.get("partial",  [])
        missing  = ss.get("missing",  [])

        if matched or partial or missing:
            story.append(Spacer(1, 2 * mm))
            skills_rows = []
            if matched:
                skills_rows.append([
                    Paragraph("Matched", ParagraphStyle("ml", fontSize=8, textColor=GREEN, fontName="Helvetica-Bold")),
                    Paragraph(", ".join(matched[:12]), ParagraphStyle("mv", fontSize=8, textColor=TEXT_DARK)),
                ])
            if partial:
                skills_rows.append([
                    Paragraph("Partial", ParagraphStyle("pl", fontSize=8, textColor=YELLOW, fontName="Helvetica-Bold")),
                    Paragraph(", ".join(partial[:8]), ParagraphStyle("pv", fontSize=8, textColor=TEXT_DARK)),
                ])
            if missing:
                skills_rows.append([
                    Paragraph("Missing", ParagraphStyle("rl", fontSize=8, textColor=RED, fontName="Helvetica-Bold")),
                    Paragraph(", ".join(missing[:8]), ParagraphStyle("rv", fontSize=8, textColor=TEXT_DARK)),
                ])
            skills_table = Table(skills_rows, colWidths=[28*mm, 142*mm])
            skills_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",    (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(skills_table)

        # ── Red Flags ──────────────────────────────────────────
        red_flags = r.get("red_flags", [])
        if red_flags:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                "Red Flags: " + " · ".join(red_flags[:4]),
                ParagraphStyle("rf", fontSize=8, textColor=RED, spaceAfter=2, leading=12, fontName="Helvetica-Bold"),
            ))

        # ── Recommendation ─────────────────────────────────────
        recommendation = r.get("recommendation", "")
        if recommendation:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                "Recommendation",
                ParagraphStyle("rh", fontSize=9, textColor=ACCENT, fontName="Helvetica-Bold", spaceAfter=3),
            ))
            story.append(Paragraph(recommendation, rec_style))

        story.append(Spacer(1, 4 * mm))
        if i < len(results):
            story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY, spaceAfter=4 * mm))

    # ── Footer note ────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceBefore=4 * mm, spaceAfter=3 * mm))
    story.append(Paragraph(
        "Generated by Resume & JD Analyzer · AI-powered matching with BGE embeddings, "
        "LLM extraction, and ontology-based skill inference.",
        ParagraphStyle("footer", fontSize=7, textColor=TEXT_MUTED, alignment=TA_CENTER),
    ))

    doc.build(story)
    return buffer.getvalue()
