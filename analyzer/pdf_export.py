"""PDF export functionality for repository analysis results."""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import RepositoryAnalysis


def generate_pdf(analysis: "RepositoryAnalysis") -> bytes:
    """Generate a comprehensive PDF report from analysis results.

    Args:
        analysis: RepositoryAnalysis instance with scores and details.

    Returns:
        PDF content as bytes.
    """
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#0d1117"),
        spaceAfter=12,
        alignment=1,
    )
    story.append(Paragraph("Repository Analysis Report", title_style))
    story.append(Spacer(1, 0.2 * inch))

    # Repository URL
    url_style = ParagraphStyle(
        "URLStyle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#333333"),
        spaceAfter=6,
    )
    story.append(Paragraph(f"<b>Repository:</b> {analysis.repo_url}", url_style))
    story.append(
        Paragraph(
            f"<b>Analysis Date:</b> {analysis.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            url_style,
        )
    )
    story.append(Spacer(1, 0.3 * inch))

    # Overall Score
    overall_style = ParagraphStyle(
        "OverallScore",
        parent=styles["Heading2"],
        fontSize=18,
        textColor=_get_color_for_score(analysis.overall_score),
        spaceAfter=12,
    )
    story.append(
        Paragraph(f"Overall Score: {analysis.overall_score}/100", overall_style)
    )
    story.append(Spacer(1, 0.2 * inch))

    # Score Cards Table
    score_data = [
        ["Metric", "Score"],
        ["Code Style", str(analysis.style_score)],
        ["Security", str(analysis.security_score)],
        ["Architecture", str(analysis.architecture_score)],
        ["Type Checking", str(analysis.type_score)],
        ["Test Coverage", str(analysis.coverage_score)],
        ["Dead Code", str(analysis.dead_code_score)],
        ["Tech Debt", str(analysis.todo_score)],
    ]

    score_table = Table(score_data, colWidths=[3 * inch, 1.5 * inch])
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#161b22")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
            ]
        )
    )
    story.append(score_table)
    story.append(Spacer(1, 0.3 * inch))

    # Detailed Analysis Sections
    if analysis.report_details:
        section_style = ParagraphStyle(
            "SectionTitle",
            parent=styles["Heading2"],
            fontSize=13,
            textColor=colors.HexColor("#0d1117"),
            spaceAfter=10,
            spaceBefore=10,
            borderColor=colors.HexColor("#30363d"),
            borderWidth=1,
            borderPadding=6,
        )

        # Code Style Section
        if "style" in analysis.report_details:
            story.append(Paragraph("1. Code Style (Flake8 & Black)", section_style))
            _add_style_section(analysis.report_details["style"], story, styles)
            story.append(Spacer(1, 0.2 * inch))

        # Security Section
        if "security" in analysis.report_details:
            story.append(Paragraph("2. Security (Bandit)", section_style))
            _add_security_section(analysis.report_details["security"], story, styles)
            story.append(Spacer(1, 0.2 * inch))

        # Architecture Section
        if "architecture" in analysis.report_details:
            story.append(Paragraph("3. Architecture (Radon)", section_style))
            _add_architecture_section(
                analysis.report_details["architecture"], story, styles
            )
            story.append(Spacer(1, 0.2 * inch))

        # Type Checking Section
        if "typing" in analysis.report_details:
            story.append(Paragraph("4. Type Checking (Mypy)", section_style))
            _add_typing_section(analysis.report_details["typing"], story, styles)
            story.append(Spacer(1, 0.2 * inch))

        # Test Coverage Section
        if "coverage" in analysis.report_details:
            story.append(Paragraph("5. Test Coverage (Pytest)", section_style))
            _add_coverage_section(analysis.report_details["coverage"], story, styles)
            story.append(Spacer(1, 0.2 * inch))

        # Dead Code Section
        if "dead_code" in analysis.report_details:
            story.append(Paragraph("6. Dead Code (Vulture)", section_style))
            _add_dead_code_section(analysis.report_details["dead_code"], story, styles)
            story.append(Spacer(1, 0.2 * inch))

        # Tech Debt Section
        if "tech_debt" in analysis.report_details:
            story.append(Paragraph("7. Tech Debt (TODOs & Fixmes)", section_style))
            _add_tech_debt_section(analysis.report_details["tech_debt"], story, styles)

    # Footer
    story.append(PageBreak())
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
        alignment=1,
    )
    story.append(Spacer(1, 0.1 * inch))
    story.append(
        Paragraph(
            f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by RepoRanker",
            footer_style,
        )
    )

    # Build PDF
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def _add_style_section(style_info: dict, story: list, styles):
    """Add code style section to PDF."""
    text_style = styles["Normal"]
    story.append(
        Paragraph(f"<b>Status:</b> {style_info.get('status', 'N/A')}", text_style)
    )
    story.append(
        Paragraph(f"<b>Summary:</b> {style_info.get('summary', 'N/A')}", text_style)
    )

    if style_info.get("issues") and len(style_info["issues"]) > 0:
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(f"<b>Issues ({len(style_info['issues'])}):</b>", text_style)
        )

        issue_data = [["File", "Line", "Code", "Message"]]
        for issue in style_info["issues"][:20]:
            issue_data.append(
                [
                    issue.get("file", ""),
                    str(issue.get("line", "")),
                    issue.get("code", ""),
                    issue.get("message", "")[:50],
                ]
            )

        issue_table = Table(
            issue_data, colWidths=[1.2 * inch, 0.5 * inch, 0.6 * inch, 1.7 * inch]
        )
        issue_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f5f5f5")],
                    ),
                ]
            )
        )
        story.append(issue_table)
    else:
        story.append(Paragraph("<i>✓ No style issues found</i>", text_style))


def _add_security_section(security_info: dict, story: list, styles):
    """Add security section to PDF."""
    text_style = styles["Normal"]
    story.append(
        Paragraph(f"<b>Status:</b> {security_info.get('status', 'N/A')}", text_style)
    )
    story.append(
        Paragraph(f"<b>Summary:</b> {security_info.get('summary', 'N/A')}", text_style)
    )

    if (
        security_info.get("vulnerabilities")
        and len(security_info["vulnerabilities"]) > 0
    ):
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(
                f"<b>Vulnerabilities ({len(security_info['vulnerabilities'])}):</b>",
                text_style,
            )
        )

        vuln_data = [["Severity", "File", "Issue"]]
        for vuln in security_info["vulnerabilities"][:15]:
            vuln_data.append(
                [
                    vuln.get("severity", ""),
                    vuln.get("file", ""),
                    vuln.get("message", "")[:40],
                ]
            )

        vuln_table = Table(vuln_data, colWidths=[1 * inch, 1.5 * inch, 2 * inch])
        vuln_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f85149")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#ffe0e0")],
                    ),
                ]
            )
        )
        story.append(vuln_table)
    else:
        story.append(
            Paragraph("<i>✓ No security vulnerabilities found</i>", text_style)
        )


def _add_architecture_section(arch_info: dict, story: list, styles):
    """Add architecture section to PDF."""
    text_style = styles["Normal"]
    story.append(
        Paragraph(f"<b>Status:</b> {arch_info.get('status', 'N/A')}", text_style)
    )
    story.append(
        Paragraph(f"<b>Summary:</b> {arch_info.get('summary', 'N/A')}", text_style)
    )

    if arch_info.get("average_complexity"):
        story.append(Spacer(1, 0.05 * inch))
        story.append(
            Paragraph(
                f"<b>Average Complexity:</b> {arch_info.get('average_complexity', 'N/A')}",
                text_style,
            )
        )

    if arch_info.get("maintainability_index"):
        story.append(
            Paragraph(
                f"<b>Maintainability Index:</b> {arch_info.get('maintainability_index', 'N/A')}",
                text_style,
            )
        )

    if arch_info.get("functions") and len(arch_info["functions"]) > 0:
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(
                f"<b>Top Complex Functions ({len(arch_info['functions'])}):</b>",
                text_style,
            )
        )

        func_data = [["Function", "Complexity"]]
        for func in arch_info["functions"][:10]:
            func_data.append([func.get("name", ""), str(func.get("complexity", ""))])

        func_table = Table(func_data, colWidths=[3 * inch, 1.5 * inch])
        func_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f5f5f5")],
                    ),
                ]
            )
        )
        story.append(func_table)


def _add_typing_section(typing_info: dict, story: list, styles):
    """Add type checking section to PDF."""
    text_style = styles["Normal"]
    story.append(
        Paragraph(f"<b>Status:</b> {typing_info.get('status', 'N/A')}", text_style)
    )
    story.append(
        Paragraph(f"<b>Summary:</b> {typing_info.get('summary', 'N/A')}", text_style)
    )

    if typing_info.get("errors") and len(typing_info["errors"]) > 0:
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(f"<b>Type Errors ({len(typing_info['errors'])}):</b>", text_style)
        )

        error_data = [["File", "Message"]]
        for error in typing_info["errors"][:15]:
            error_data.append([error.get("file", ""), error.get("message", "")[:60]])

        error_table = Table(error_data, colWidths=[1.5 * inch, 3 * inch])
        error_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d29922")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fff9e6")],
                    ),
                ]
            )
        )
        story.append(error_table)
    else:
        story.append(Paragraph("<i>✓ No type errors found</i>", text_style))


def _add_coverage_section(coverage_info: dict, story: list, styles):
    """Add test coverage section to PDF."""
    text_style = styles["Normal"]
    story.append(
        Paragraph(f"<b>Status:</b> {coverage_info.get('status', 'N/A')}", text_style)
    )
    story.append(
        Paragraph(f"<b>Summary:</b> {coverage_info.get('summary', 'N/A')}", text_style)
    )

    if coverage_info.get("coverage_percent"):
        story.append(Spacer(1, 0.05 * inch))
        story.append(
            Paragraph(
                f"<b>Overall Coverage:</b> {coverage_info.get('coverage_percent', 'N/A')}%",
                text_style,
            )
        )

    if coverage_info.get("files") and len(coverage_info["files"]) > 0:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("<b>File Coverage:</b>", text_style))

        cov_data = [["File", "Coverage %"]]
        for file_name, pct in list(coverage_info["files"].items())[:15]:
            cov_data.append([file_name, f"{pct}%"])

        cov_table = Table(cov_data, colWidths=[3 * inch, 1.5 * inch])
        cov_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3fb950")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#e6f9e6")],
                    ),
                ]
            )
        )
        story.append(cov_table)


def _add_dead_code_section(dead_code_info: dict, story: list, styles):
    """Add dead code section to PDF."""
    text_style = styles["Normal"]
    story.append(
        Paragraph(f"<b>Status:</b> {dead_code_info.get('status', 'N/A')}", text_style)
    )
    story.append(
        Paragraph(f"<b>Summary:</b> {dead_code_info.get('summary', 'N/A')}", text_style)
    )

    if dead_code_info.get("issues") and len(dead_code_info["issues"]) > 0:
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(
                f"<b>Dead Code Issues ({len(dead_code_info['issues'])}):</b>",
                text_style,
            )
        )

        dead_data = [["File", "Type", "Name"]]
        for issue in dead_code_info["issues"][:15]:
            dead_data.append(
                [
                    issue.get("file", ""),
                    issue.get("type", ""),
                    issue.get("name", "")[:40],
                ]
            )

        dead_table = Table(dead_data, colWidths=[1.5 * inch, 1 * inch, 2.5 * inch])
        dead_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f5f5f5")],
                    ),
                ]
            )
        )
        story.append(dead_table)
    else:
        story.append(Paragraph("<i>✓ No dead code found</i>", text_style))


def _add_tech_debt_section(tech_debt_info: dict, story: list, styles):
    """Add tech debt (TODOs/FIXMEs) section to PDF."""
    text_style = styles["Normal"]
    story.append(
        Paragraph(f"<b>Status:</b> {tech_debt_info.get('status', 'N/A')}", text_style)
    )
    story.append(
        Paragraph(f"<b>Summary:</b> {tech_debt_info.get('summary', 'N/A')}", text_style)
    )

    if tech_debt_info.get("items") and len(tech_debt_info["items"]) > 0:
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(
                f"<b>TODOs & FIXMEs ({len(tech_debt_info['items'])}):</b>",
                text_style,
            )
        )

        debt_data = [["File", "Type", "Text"]]
        for item in tech_debt_info["items"][:20]:
            debt_data.append(
                [
                    item.get("file", ""),
                    item.get("type", ""),
                    item.get("text", "")[:50],
                ]
            )

        debt_table = Table(debt_data, colWidths=[1.5 * inch, 0.8 * inch, 2.7 * inch])
        debt_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d29922")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fff9e6")],
                    ),
                ]
            )
        )
        story.append(debt_table)
    else:
        story.append(Paragraph("<i>✓ No TODOs or FIXMEs found</i>", text_style))


def _get_color_for_score(score: int) -> colors.Color:
    """Return a color based on score value.

    Args:
        score: Score value from 0-100.

    Returns:
        reportlab color object.
    """
    if score >= 75:
        return colors.HexColor("#3fb950")  # Green
    if score >= 50:
        return colors.HexColor("#d29922")  # Yellow
    return colors.HexColor("#f85149")  # Red
