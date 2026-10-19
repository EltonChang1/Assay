# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["reportlab==4.4.9", "matplotlib==3.10.7", "pypdf==6.10.0"]
# ///
"""Build the single-file Assay paper; no API calls or experiment execution.

Run: uv run --script research/build_paper.py
The complete manuscript is research/paper.md. Figures and equations are embedded
in the PDF; readers need no companion files to read the report.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/paper.md"
OUTPUT = ROOT / "output/pdf/assay-technical-report.pdf"
WIDTH, HEIGHT = 612, 792
MARGIN = 62
BODY_WIDTH = WIDTH - 2 * MARGIN
NAVY = colors.HexColor("#243343")
GRAY = colors.HexColor("#626b75")
MATH_DIR = ROOT / "tmp/pdfs/math"
plt.rcParams["mathtext.fontset"] = "stix"


def clean_math(value: str) -> str:
    value = re.sub(r"\\(?:text|operatorname)\{([^}]*)\}", r"\\mathrm{\1}", value)
    value = value.replace(r"\texttt{", r"\mathtt{")
    for source, target in (
        (r"\land", r"\wedge"),
        (r"\lor", r"\vee"),
        (r"\le", r"\leq"),
        (r"\ge", r"\geq"),
        (r"\ne", r"\neq"),
    ):
        value = re.sub(re.escape(source) + r"(?![a-zA-Z])", lambda _, target=target: target, value)
    return value


def inline_equation(value: str) -> str:
    """Embed a small equation image; all such files are embedded in the PDF."""
    MATH_DIR.mkdir(parents=True, exist_ok=True)
    path = MATH_DIR / (hashlib.sha256(value.encode()).hexdigest() + ".png")
    if not path.exists():
        fig = plt.figure(figsize=(6, 0.3))
        try:
            artist = fig.text(
                0.5, 0.5, "$" + clean_math(value) + "$", ha="center", va="center", fontsize=10.2
            )
            fig.canvas.draw()
            bbox = artist.get_window_extent().expanded(1.025, 1.15)
            fig.savefig(
                path,
                dpi=240,
                bbox_inches=bbox.transformed(fig.dpi_scale_trans.inverted()),
                pad_inches=0.005,
            )
        except Exception as exc:
            raise ValueError(f"Cannot render inline equation: {value}") from exc
        finally:
            plt.close(fig)
    iw, ih = ImageReader(str(path)).getSize()
    w, h = iw * 72 / 240, ih * 72 / 240
    return f'<img src="{path.as_posix()}" width="{w:.2f}" height="{h:.2f}" valign="-3"/>'


def register_fonts():
    fonts = Path("C:/Windows/Fonts")
    if (fonts / "times.ttf").exists():
        for name, filename in (
            ("Paper", "times.ttf"),
            ("Paper-Bold", "timesbd.ttf"),
            ("Paper-Italic", "timesi.ttf"),
            ("Paper-BoldItalic", "timesbi.ttf"),
            ("Code", "consola.ttf"),
        ):
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
        pdfmetrics.registerFontFamily(
            "Paper",
            normal="Paper",
            bold="Paper-Bold",
            italic="Paper-Italic",
            boldItalic="Paper-BoldItalic",
        )
    else:
        # Standard PDF fonts keep the builder usable without Windows fonts.
        for name, target in (
            ("Paper", "Times-Roman"),
            ("Paper-Bold", "Times-Bold"),
            ("Paper-Italic", "Times-Italic"),
            ("Code", "Courier"),
        ):
            pdfmetrics.registerFont(pdfmetrics.Font(name, target, "WinAnsiEncoding"))
        pdfmetrics.registerFontFamily(
            "Paper",
            normal="Paper",
            bold="Paper-Bold",
            italic="Paper-Italic",
            boldItalic="Paper-Bold",
        )


def inline(value: str) -> str:
    equations = []

    def capture(match):
        equations.append(inline_equation(match.group(1)))
        return f"EQUATIONTOKEN{len(equations) - 1}ENDTOKEN"

    value = re.sub(r"\\\((.*?)\\\)", capture, value)
    value = html.escape(value.strip())
    # Links remain clickable and the descriptive label remains visible text.
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<link href="\2" color="#183247"><u>\1</u></link>',
        value,
    )
    value = re.sub(r"`([^`]+)`", r'<font name="Code" size="8.0">\1</font>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", value)
    # Internal file links render as inspectable paths rather than invalid URLs.
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", value)
    for i, content in enumerate(equations):
        value = value.replace(f"EQUATIONTOKEN{i}ENDTOKEN", content)
    return value


class PaperDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(
            str(filename),
            pagesize=(WIDTH, HEIGHT),
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=52,
            bottomMargin=49,
            title="Assay: Analytical Correctness and Controlled Release of AI Reports",
            author="Assay research project",
            subject="Analytical contracts, partial verification, and revision-bound release",
        )
        self.addPageTemplates(
            PageTemplate(
                id="paper",
                frames=Frame(
                    MARGIN,
                    49,
                    BODY_WIDTH,
                    HEIGHT - 101,
                    leftPadding=0,
                    rightPadding=0,
                    topPadding=0,
                    bottomPadding=0,
                ),
                onPage=self.decorate,
            )
        )

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(GRAY)
        canvas.setFont("Paper", 8)
        if doc.page > 1:
            canvas.drawString(
                MARGIN, HEIGHT - 32, "Assay: Analytical Correctness and Controlled Release"
            )
            canvas.setStrokeColor(colors.HexColor("#d9dce0"))
            canvas.line(MARGIN, HEIGHT - 38, WIDTH - MARGIN, HEIGHT - 38)
        canvas.drawCentredString(WIDTH / 2, 29, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in {"Section", "Subsection"}:
            if flowable.getPlainText() == "Contents":
                return
            level = 0 if flowable.style.name == "Section" else 1
            key = "h-" + hashlib.sha256(flowable.getPlainText().encode()).hexdigest()[:16]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(), key, level=level, closed=False)
            self.notify("TOCEntry", (level, flowable.getPlainText(), self.page, key))


def equation(lines: list[str], assets: list[io.BytesIO]) -> list[Flowable]:
    # Mathtext accepts the paper's scalar equations. Avoid unsupported TeX environments.
    raw = " ".join(lines).strip()
    raw = re.sub(r"\\(?:begin|end)\{(?:aligned|align|gathered)\}", "", raw)
    raw = raw.replace("&", "")
    raw = clean_math(raw)
    out = []
    for part in re.split(r"\\\\", raw):
        if not part.strip():
            continue
        part = part.strip().replace("\\tag", "\\mathrm")
        fig = plt.figure(figsize=(8.5, 0.5))
        try:
            artist = fig.text(0.5, 0.5, "$" + part + "$", ha="center", va="center", fontsize=12)
            fig.canvas.draw()
            bbox = artist.get_window_extent().expanded(1.035, 1.5)
            buf = io.BytesIO()
            fig.savefig(
                buf,
                format="png",
                dpi=240,
                bbox_inches=bbox.transformed(fig.dpi_scale_trans.inverted()),
                pad_inches=0.035,
            )
            buf.seek(0)
            assets.append(buf)
            iw, ih = ImageReader(buf).getSize()
            width = min(BODY_WIDTH - 15, iw * 72 / 240)
            out.append(Image(buf, width=width, height=ih * width / iw, hAlign="CENTER"))
            out.append(Spacer(1, 7))
        except Exception as exc:
            raise ValueError(f"Cannot render equation: {part}") from exc
        finally:
            plt.close(fig)
    return out


def fixture_figure(assets):
    evidence = json.loads((ROOT / "research/validation/milestone.json").read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in evidence["cases"]}

    def values_for(fixture):
        strategies = ("order_aggregation", "duplicated_join", "distinct_amount")
        rows = [cases[f"{fixture}.{strategy}"] for strategy in strategies]
        if not all(row["regression_passed"] for row in rows):
            raise ValueError("Fixture figure requires passing saved numerical regressions")
        return [float(row["query_value"]) for row in rows], float(
            rows[0]["canonical_reference_value"]
        )

    fig, axes = plt.subplots(1, 2, figsize=(8.1, 2.9), sharey=True)
    for ax, title, fixture in (
        (axes[0], "Base development fixture", "base"),
        (axes[1], "Equal-amount counterexample", "equal_amount"),
    ):
        values, truth = values_for(fixture)
        bars = ax.bar(
            ["Order\ngrain", "Expanded\njoin", "DISTINCT\namount"],
            values,
            color=["#315f79", "#ac5c4e", "#889aab"],
            width=0.6,
        )
        ax.axhline(truth, color="#223745", ls="--", lw=1)
        ax.set_title(title, fontsize=10)
        ax.spines[["right", "top"]].set_visible(False)
        ax.tick_params(labelsize=9)
        ax.set_ylim(0, 500)
        for bar, value in zip(bars, values, strict=True):
            ax.text(
                bar.get_x() + bar.get_width() / 2, value + 10, f"{value:g}", ha="center", fontsize=9
            )
    axes[0].set_ylabel("Computed settled revenue (USD)", fontsize=9)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=240, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    assets.append(buf)
    iw, ih = ImageReader(buf).getSize()
    return Image(buf, width=BODY_WIDTH, height=BODY_WIDTH * ih / iw)


class ProtocolFigure(Flowable):
    """Vector diagram of the release chain; no external image dependency."""

    def __init__(self):
        super().__init__()
        self.width = BODY_WIDTH
        self.height = 120
        self.keepWithNext = True

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        gap = 11
        box_width = (self.width - 4 * gap) / 5
        labels = [
            ("Task +", "snapshot"),
            ("Query +", "result"),
            ("Claims +", "checks"),
            ("Review +", "approval"),
            ("Released", "bytes"),
        ]
        for index, lines in enumerate(labels):
            x = index * (box_width + gap)
            canvas.setFillColor(
                colors.HexColor("#e8eef3") if index == 4 else colors.HexColor("#f6f7f8")
            )
            canvas.setStrokeColor(colors.HexColor("#82909c"))
            canvas.roundRect(x, 61, box_width, 36, 3, fill=1, stroke=1)
            canvas.setFont("Paper-Bold", 9)
            canvas.setFillColor(NAVY)
            for row, line in enumerate(lines):
                canvas.drawCentredString(x + box_width / 2, 83 - 11 * row, line)
            if index < 4:
                right = x + box_width
                canvas.line(right + 1, 79, right + gap - 1, 79)
                canvas.line(right + gap - 4, 81, right + gap - 1, 79)
                canvas.line(right + gap - 4, 77, right + gap - 1, 79)
        canvas.setFont("Paper-Italic", 8.5)
        canvas.setFillColor(GRAY)
        canvas.drawString(0, 106, "Host-recorded evidence and authorization")
        canvas.setStrokeColor(GRAY)
        canvas.line(self.width - box_width / 2, 61, self.width - box_width / 2, 43)
        canvas.line(self.width - box_width / 2 - 2, 46, self.width - box_width / 2, 43)
        canvas.line(self.width - box_width / 2 + 2, 46, self.width - box_width / 2, 43)
        canvas.setFont("Paper", 9)
        canvas.drawRightString(
            self.width, 29, "Independent evaluator scores releases after the episode"
        )
        canvas.setFont("Paper-Italic", 8.5)
        canvas.drawRightString(
            self.width, 15, "Private truth is not an input to publication authority"
        )
        canvas.restoreState()


def main():
    register_fonts()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "BodyPaper",
            fontName="Paper",
            fontSize=10.5,
            leading=13.8,
            autoLeading="max",
            alignment=TA_JUSTIFY,
            spaceAfter=5.5,
            splitLongWords=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "Section",
            fontName="Paper-Bold",
            fontSize=13,
            leading=16,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=7,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "Subsection",
            fontName="Paper-Bold",
            fontSize=11,
            leading=14,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "Minor",
            fontName="Paper-Italic",
            fontSize=10.5,
            leading=14,
            spaceBefore=7,
            spaceAfter=5,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "TitlePaper",
            fontName="Paper-Bold",
            fontSize=20,
            leading=24,
            textColor=NAVY,
            spaceAfter=11,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            "MetaPaper", fontName="Paper", fontSize=10, leading=14, textColor=GRAY, spaceAfter=9
        )
    )
    styles.add(
        ParagraphStyle(
            "AbstractPaper", parent=styles["BodyPaper"], fontSize=9.8, leading=12.5, spaceAfter=10
        )
    )
    styles.add(
        ParagraphStyle(
            "ReferencePaper",
            parent=styles["BodyPaper"],
            fontSize=9,
            leading=11.3,
            spaceAfter=5,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle("CaptionPaper", fontName="Paper", fontSize=9, leading=11.5, spaceAfter=9)
    )
    styles.add(
        ParagraphStyle("CellPaper", fontName="Paper", fontSize=8.5, leading=10.8, autoLeading="max")
    )
    styles.add(
        ParagraphStyle(
            "CodePaper",
            fontName="Code",
            fontSize=7.5,
            leading=10,
            spaceBefore=5,
            spaceAfter=7,
            backColor=colors.HexColor("#f2f5f7"),
            borderPadding=7,
        )
    )
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC0", fontName="Paper", fontSize=9, leading=11, spaceBefore=1),
        ParagraphStyle("TOC1", fontName="Paper", fontSize=8, leading=9.5, leftIndent=12),
    ]
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    story, assets = [], []
    i = 0
    in_references = False
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line == "<!-- TOC -->":
            story += [PageBreak(), Paragraph("Contents", styles["Section"]), toc, PageBreak()]
            i += 1
            continue
        if line == "<!-- PAGEBREAK -->":
            story.append(PageBreak())
            i += 1
            continue
        if line == "<!-- FIXTURE_FIGURE -->":
            figure = fixture_figure(assets)
            figure.keepWithNext = True
            story.append(figure)
            i += 1
            continue
        if line == "<!-- PROTOCOL_FIGURE -->":
            story.append(ProtocolFigure())
            i += 1
            continue
        if line.startswith("<!--"):
            i += 1
            continue
        if line in {r"\[", "$$"}:
            end = r"\]" if line == r"\[" else "$$"
            content = []
            i += 1
            while i < len(lines) and lines[i].strip() != end:
                content.append(lines[i])
                i += 1
            story.extend(equation(content, assets))
            i += 1
            continue
        if line.startswith(("```", "~~~")):
            fence = line[:3]
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                code.extend(
                    textwrap.wrap(
                        lines[i].expandtabs(4),
                        width=96,
                        replace_whitespace=False,
                        drop_whitespace=False,
                    )
                    or [""]
                )
                i += 1
            # Ordinary Preformatted can split across pages.
            story.append(Preformatted("\n".join(code), styles["CodePaper"]))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c.replace(" ", "")) for c in cells):
                    rows.append(cells)
                i += 1
            columns = max(map(len, rows))
            rows = [r + [""] * (columns - len(r)) for r in rows]
            data = [[Paragraph(inline(c), styles["CellPaper"]) for c in r] for r in rows]
            table = Table(
                data, colWidths=[BODY_WIDTH / columns] * columns, repeatRows=1, hAlign="LEFT"
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6edf2")),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f7f9fa")],
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            group = KeepTogether([table, Spacer(1, 7)])
            group.keepWithNext = True
            story.append(group)
            continue
        if line.startswith("#"):
            depth = len(line) - len(line.lstrip("#"))
            if depth == 2:
                in_references = line[depth:].strip() == "References"
            style = {1: "TitlePaper", 2: "Section", 3: "Subsection"}.get(depth, "Minor")
            story.append(Paragraph(inline(line[depth:].strip()), styles[style]))
            i += 1
            continue
        if line == "---":
            story.append(Spacer(1, 8))
            i += 1
            continue
        bullet = re.match(r"^(?:[-*]|\d+[.)])\s+", line)
        if bullet:
            content = line[bullet.end() :]
            i += 1
            while i < len(lines) and lines[i].strip() and lines[i].startswith("  "):
                content += " " + lines[i].strip()
                i += 1
            story.append(
                Paragraph(
                    "<b>" + html.escape(bullet.group().strip()) + "</b> " + inline(content),
                    styles["BodyPaper"],
                )
            )
            continue
        paragraph = [line]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not lines[i].lstrip().startswith(("#", "|", "```", "~~~", "<!--", "\\[", "$$"))
        ):
            paragraph.append(lines[i].strip())
            i += 1
        text = " ".join(paragraph)
        if text.startswith("**Abstract."):
            style = "AbstractPaper"
        elif text.startswith(("**Figure ", "**Table ")):
            style = "CaptionPaper"
        else:
            style = "ReferencePaper" if in_references else "BodyPaper"
        paragraph = Paragraph(inline(text), styles[style])
        next_content = next((item.strip() for item in lines[i:] if item.strip()), "")
        if next_content.startswith("|"):
            paragraph.keepWithNext = True
        story.append(paragraph)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    PaperDoc(OUTPUT).multiBuild(story)
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(OUTPUT))
    writer.metadata = {
        key: value
        for key, value in (writer.metadata or {}).items()
        if key not in {"/CreationDate", "/ModDate"}
    }
    writer.write(OUTPUT)
    reader = PdfReader(OUTPUT)
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    target = ROOT / "research/validation/paper-build.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source": "research/paper.md",
                "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "figure_evidence_sha256": hashlib.sha256(
                    (ROOT / "research/validation/milestone.json").read_bytes()
                ).hexdigest(),
                "output": "output/pdf/assay-technical-report.pdf",
                "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                "pages": len(reader.pages),
                "extracted_characters": len(extracted),
                "visual_inspection": "required separately; this record only checks extraction",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"pdf": str(OUTPUT), "pages": len(reader.pages), "extracted_characters": len(extracted)}
        )
    )


if __name__ == "__main__":
    main()
