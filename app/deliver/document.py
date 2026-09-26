"""Module D3: Document Generator — the deliverable.

Two modes, as the manual's §4 sets out:

* **Annexure**: an "Annexure — Applicable Indian Standards" appended to the officer's own tender.
  This is how government tenders actually carry this information, so it is authentic rather than a
  workaround, and it is the robust path: editing an arbitrary third-party PDF in place is fragile,
  and a botched insertion looks worse than no insertion.
* **Report**: the same content as a standalone document, for a manufacturer or for a file note.

Rendered with PyMuPDF's HTML story rather than WeasyPrint, which needs GTK libraries that are
awkward on Windows. PyMuPDF is already a dependency because A2 reads PDFs with it, and the same
library appends the annexure to the user's original file.

Every standard named in the document came from the catalogue, and the one generated paragraph has
already passed D1. Clause extracts are short and attributed; BIS text is never reproduced in full.

    from app.deliver.document import DocumentGenerator
    DocumentGenerator().generate(result, "out.pdf", option_id="B", mode="annexure",
                                 original_pdf="tender.pdf")
"""

import html
import io
import re
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contracts.answer import Recommendation  # noqa: E402

MARGIN = 45
QUOTE_CHARS = 220
MAX_PAGES = 30          # a guard: a malformed fragment must not spin the writer forever
# The last words of the footer. Their absence means the renderer stopped early.
FOOTER_SENTINEL = "no standard is reproduced"
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}

CSS = """
body { font-family: sans-serif; font-size: 9.5pt; color: #111; }
h1 { font-size: 15pt; margin: 0 0 2pt 0; }
h2 { font-size: 11pt; margin: 14pt 0 4pt 0; color: #14304f; }
p  { margin: 3pt 0; line-height: 1.35; }
.sub { color: #555; font-size: 8.5pt; margin-bottom: 8pt; }
table { width: 100%; border: 1px solid #b8c4d0; }
th { background-color: #e8eef5; text-align: left; font-size: 8.5pt; padding: 3pt; }
td { font-size: 8.5pt; padding: 3pt; border-top: 1px solid #dde4ea; vertical-align: top; }
.num { font-weight: bold; }
.small { font-size: 8pt; color: #555; }
.high { color: #9a1b1b; font-weight: bold; }
.medium { color: #8a5a00; }
.low { color: #444; }
.foot { font-size: 7.5pt; color: #666; margin-top: 10pt; }
"""

BAND_WORDS = {
    "high": "High confidence",
    "medium": "Medium confidence",
    "low": "Low confidence — treat as a starting point and confirm before publishing",
}
VERDICT_WORDS = {
    "keep": "Keep", "replace": "Replace", "remove": "Remove",
    "add": "Add — missing from the tender", "verify": "Verify",
}


class DocumentGenerator:
    # ---------------------------------------------------------------- public

    def generate(self, result, out_path: str, option_id: str = "B", mode: str = "annexure",
                 original_pdf: Optional[str] = None, persona: str = "procurement",
                 reference: Optional[str] = None) -> Path:
        """Write the PDF and return its path.

        In annexure mode with an original file, the annexure pages are appended to a copy of the
        user's tender; the original is never modified in place.
        """
        pages = self._render(result, option_id, mode, persona, reference)
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if mode == "annexure" and original_pdf and Path(original_pdf).exists():
            document = pymupdf.open(original_pdf)
            document.insert_pdf(pages)
            document.save(str(target))
            document.close()
        else:
            pages.save(str(target))
        pages.close()
        return target

    def html(self, result, option_id: str = "B", mode: str = "annexure",
             persona: str = "procurement", reference: Optional[str] = None) -> str:
        """The document as HTML, which is also what the web interface can preview."""
        recommendation: Recommendation = result.recommendation
        option = next((o for o in recommendation.options if o.id.upper() == option_id.upper()),
                      recommendation.options[1] if len(recommendation.options) > 1 else None)
        blocks: List[str] = []

        title = ("Annexure — Applicable Indian Standards" if mode == "annexure"
                 else "Indian Standards — Compliance Report")
        blocks.append(f"<h1>{title}</h1>")
        subtitle = [f"Prepared {date.today().isoformat()}"]
        if reference:
            subtitle.append(f"Tender reference: {self._e(reference)}")
        subtitle.append("Persona: " + ("procurement official" if persona == "procurement" else "manufacturer"))
        blocks.append(f"<p class='sub'>{' &nbsp;·&nbsp; '.join(subtitle)}</p>")

        blocks.append(self._requirement_block(result))
        blocks.append(self._primary_block(recommendation, option))
        blocks.append(self._standards_table(recommendation, option))
        blocks.append(self._citation_review(recommendation))
        blocks.append(self._certification_block(recommendation, persona))
        blocks.append(self._warnings_block(recommendation))
        blocks.append(self._footer(result))
        return f"<html><head><style>{CSS}</style></head><body>{''.join(b for b in blocks if b)}</body></html>"

    # ---------------------------------------------------------------- sections

    def _requirement_block(self, result) -> str:
        requirement = result.requirement
        rows = [("Item", requirement.product or "not stated")]
        for key, value in list(requirement.attributes.items())[:6]:
            rows.append((key.replace("_", " ").title(), value))
        if requirement.not_specified:
            rows.append(("Not specified in the tender", ", ".join(requirement.not_specified)))
        cells = "".join(f'<tr><td width="140">{self._e(k)}</td><td width="330">{self._e(v)}</td></tr>'
                        for k, v in rows)
        return f"<h2>1. What was specified</h2><table>{cells}</table>"

    def _primary_block(self, recommendation: Recommendation, option) -> str:
        if not recommendation.primary:
            return ("<h2>2. Result</h2><p>No Indian Standard could be matched to this description "
                    "with enough confidence to recommend one. The catalogue may still hold a "
                    "suitable standard; its text has not been ingested.</p>")
        band = recommendation.band
        parts = [f"<h2>2. Recommended standard</h2>",
                 f"<p><span class='num'>{self._e(recommendation.primary_as_cited or recommendation.primary)}"
                 f"</span> — {self._e(recommendation.primary_title)}</p>",
                 f"<p class='{band}'>{BAND_WORDS.get(band, band)} ({recommendation.confidence:.2f})</p>"]
        if recommendation.evidence and recommendation.evidence.quote:
            evidence = recommendation.evidence
            # A summary match carries BIS's own one-page description of the standard rather than a
            # numbered clause. Saying "clause SUMMARY" would imply a clause that does not exist.
            if evidence.role == "summary":
                where = "BIS one-page summary of this standard"
            else:
                where = (f"clause {self._e(evidence.clause)} ({self._e(evidence.role)}), "
                         f"page {evidence.page_start}")
            parts.append(f"<p class='small'>Evidence — {where}: "
                         f"&ldquo;{self._e(evidence.quote[:QUOTE_CHARS])}&hellip;&rdquo;</p>")
        else:
            parts.append("<p class='small'>Matched on the catalogue entry for this standard. No "
                         "clause text is held for it, so no extract can be quoted here.</p>")
        if recommendation.amendments:
            listed = "; ".join(f"{a.get('number', '').strip()} ({a.get('year', '')})"
                               for a in recommendation.amendments)
            parts.append(f"<p class='small'>Amendments in force: {self._e(listed)}. The edition year "
                         f"does not change when a standard is amended, so cite it as amended.</p>")
        if recommendation.explanation:
            parts.append(f"<p>{self._e(recommendation.explanation)}</p>")
        if option:
            parts.append(f"<p class='small'>Citation depth: {self._e(option.label)} — "
                         f"{self._e(option.rationale)}</p>")
        return "".join(parts)

    def _standards_table(self, recommendation: Recommendation, option) -> str:
        if not option or not option.standards:
            return ""
        relation_of = {}
        for relation, items in recommendation.allied.items():
            for allied in items:
                relation_of[allied.is_number] = (relation.replace("_", " "), allied.title)

        rows = []
        for number in option.standards:
            if number == recommendation.primary:
                role, title = "primary product standard", recommendation.primary_title
            else:
                role, title = relation_of.get(number, ("allied", ""))
            rows.append(f'<tr><td class="num" width="105">{self._e(number)}</td>'
                        f'<td width="235">{self._e(title)}</td>'
                        f'<td width="130">{self._e(role)}</td></tr>')
        header = ('<tr><th width="105">Indian Standard</th><th width="235">Title</th>'
                  '<th width="130">Why it is cited</th></tr>')
        return (f"<h2>3. Standards to cite</h2><table>{header}{''.join(rows)}</table>"
                f"<p class='small'>Every number above exists in the BIS catalogue and is the edition "
                f"in force on {date.today().isoformat()}.</p>")

    def _citation_review(self, recommendation: Recommendation) -> str:
        if not recommendation.verdicts:
            return ""
        rows = []
        for verdict in recommendation.verdicts:
            action = VERDICT_WORDS.get(verdict.verdict, verdict.verdict)
            if verdict.replacement:
                action += f" with {verdict.replacement}"
            rows.append(f'<tr><td class="num" width="105">{self._e(verdict.citation)}</td>'
                        f'<td width="135" class="{verdict.severity.value}">{self._e(action)}</td>'
                        f'<td width="230">{self._e(verdict.reason)}</td></tr>')
        header = ('<tr><th width="105">Cited in the tender</th><th width="135">Action</th>'
                  '<th width="230">Reason</th></tr>')
        return f"<h2>4. Review of the standards already cited</h2><table>{header}{''.join(rows)}</table>"

    def _certification_block(self, recommendation: Recommendation, persona: str) -> str:
        certification = recommendation.certification
        if not certification:
            return ""
        parts = [f"<h2>5. Certification</h2><p>{self._e(certification.statement)}</p>"]
        rows = []
        for standard in certification.standards:
            if not (standard.mandatory or standard.qco_status):
                continue
            dates = standard.qco_date or "date not stated"
            rows.append(f'<tr><td class="num" width="105">{self._e(standard.is_number)}</td>'
                        f'<td width="150">{self._e(standard.scheme or "scheme not stated")}</td>'
                        f'<td width="85">{self._e(dates)}</td>'
                        f'<td width="130">{standard.labs_available} recognised labs</td></tr>')
        if rows:
            header = ('<tr><th width="105">Standard</th><th width="150">Scheme</th>'
                      '<th width="85">In force from</th><th width="130">Testing</th></tr>')
            parts.append(f"<table>{header}{''.join(rows)}</table>")
        if certification.nearest_labs:
            labs = "; ".join(f"{self._e(lab.name)} ({self._e(lab.city)})"
                            for lab in certification.nearest_labs[:4])
            parts.append(f"<p class='small'>Nearest recognised laboratories: {labs}.</p>")
        if certification.not_stated:
            parts.append(f"<p class='small'>BIS states nothing about compulsory certification for "
                         f"{self._e(', '.join(certification.not_stated[:6]))}. That is not a "
                         f"statement that certification is unnecessary.</p>")
        return "".join(parts)

    def _warnings_block(self, recommendation: Recommendation) -> str:
        if not recommendation.warnings:
            return ""
        seen, rows = set(), []
        for warning in recommendation.warnings:
            if warning.message in seen:
                continue
            seen.add(warning.message)
            action = f" {warning.action}" if warning.action else ""
            rows.append(f'<tr><td width="65" class="{warning.severity.value}">'
                        f'{warning.severity.value}</td>'
                        f'<td width="405">{self._e(warning.message + action)}</td></tr>')
        header = '<tr><th width="65">Severity</th><th width="405">Warning</th></tr>' 
        return f"<h2>6. Version and amendment warnings</h2><table>{header}{''.join(rows)}</table>"

    def _footer(self, result) -> str:
        meta = ("Generated by Standards360 from the Bureau of Indian Standards catalogue. "
                "Standard numbers, titles, current editions, Quality Control Order status and "
                "laboratory lists are taken from BIS records; clause extracts are short quotations "
                "for identification only and no standard is reproduced. Verify every citation "
                "against the BIS portal before the tender is published.")
        return (f"<p class='foot'>{meta}</p>"
                f"<p class='foot'>Query: {self._e(result.query)} &nbsp;·&nbsp; "
                f"processed in {result.seconds} s</p>")

    # ---------------------------------------------------------------- rendering

    def _render(self, result, option_id, mode, persona, reference) -> pymupdf.Document:
        """Render the document, and check that all of it arrived.

        The HTML story silently stops placing content when a table row falls on a page boundary and
        cannot be split: the writer reports no more content while sections remain. Since a tender
        annexure that loses its certification section is worse than an ugly one, the output is
        verified against a sentinel in the footer, and anything missing is re-rendered section by
        section, each section as its own story, which cannot hit the boundary case.
        """
        document = self.html(result, option_id, mode, persona, reference)
        rendered = self._story_to_pdf(document)
        if FOOTER_SENTINEL in self._text_of(rendered):
            return rendered

        rendered.close()
        combined = pymupdf.open()
        for section in self._split_sections(document):
            part = self._story_to_pdf(section)
            combined.insert_pdf(part)
            part.close()
        return combined

    @staticmethod
    def _split_sections(document: str) -> List[str]:
        """The document as a list of self-contained HTML fragments, one per section."""
        head, _, body = document.partition("<body>")
        body = body.replace("</body></html>", "")
        pieces = re.split(r"(?=<h2>)", body)
        return [f"{head}<body>{piece}</body></html>" for piece in pieces if piece.strip()]

    @staticmethod
    def _story_to_pdf(document: str) -> pymupdf.Document:
        story = pymupdf.Story(document)
        buffer = io.BytesIO()
        writer = pymupdf.DocumentWriter(buffer)
        page = pymupdf.paper_rect("a4")
        frame = page + (MARGIN, MARGIN, -MARGIN, -MARGIN)
        more, guard = 1, 0
        while more and guard < MAX_PAGES:
            device = writer.begin_page(page)
            more, _ = story.place(frame)
            story.draw(device)
            writer.end_page()
            guard += 1
        writer.close()
        return pymupdf.open("pdf", buffer.getvalue())

    @staticmethod
    def _text_of(document: pymupdf.Document) -> str:
        text = " ".join(page.get_text() for page in document)
        for ligature, plain in LIGATURES.items():
            text = text.replace(ligature, plain)
        return " ".join(text.split())

    @staticmethod
    def _e(value) -> str:
        return html.escape(str(value or ""))
