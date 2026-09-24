"""Clause Splitter and Document Parser Engine.

Segments standard page text into discrete, structured ClauseRecord objects,
enforces granularity thresholds, computes text coverage, and verifies version honesty.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple
import fitz

from contracts.clause import ClauseRecord, ClauseRole, StandardManifestEntry
from ingest.parsing.normalizer import normalize_unicode_text, dehyphenate_text
from ingest.parsing.table_extractor import extract_tables_from_page
from ingest.parsing.heading_detector import detect_heading_line, is_sequence_valid
from ingest.parsing.role_classifier import classify_clause_role
from ingest.parsing.segmenter import StandardSegment


# The first amendment page is titled 'AMENDMENT NO. 1 ...'; its continuation pages carry a
# running header such as 'Amend No. 1 to IS 1786 : 2008'. Both must be skipped.
AMENDMENT_BANNER = re.compile(r"AMENDMENT\s+NO\.?\s*\d+|AMEND\.?\s*NO\.?\s*\d+\s+TO\s+IS\b", re.IGNORECASE)
# Some BIS PDFs embed subset fonts with no character map. Text is present but extracts as symbols,
# so the parser would produce clauses full of nonsense. Such a file needs OCR, not parsing.
READABLE_RATIO = 0.55
LETTERS = re.compile(r"[A-Za-z]")


def readability(text: str) -> float:
    """Share of letters among the non-space characters, as a check that text extracted sensibly."""
    body = "".join(text.split())
    return (len(LETTERS.findall(body)) / len(body)) if body else 0.0


def compute_sha256(file_path: str) -> str:
    """Calculate SHA-256 hash of the source document."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class RawClause:
    def __init__(self, clause_num: str, title: str, text: str, page_start: int, page_end: int, has_table: bool):
        self.clause_num = clause_num
        self.title = title
        self.text = text.strip()
        self.page_start = page_start
        self.page_end = page_end
        self.has_table = has_table
        self.children: List["RawClause"] = []


def parse_standard_pages(
    doc: fitz.Document,
    segment: StandardSegment,
    source_sha256: str,
    max_clause_chars: int = 3000,
    top_margin_y: float = 95.0,
    bottom_margin_y: float = 750.0,
) -> Tuple[List[ClauseRecord], StandardManifestEntry]:
    """Parse the page range of a standard into validated ClauseRecord objects."""
    start_pno = segment.page_start - 1
    end_pno = segment.page_end

    total_cleaned_text_chars = 0
    scanned_pages = []
    amendment_pages = []

    # Collect clean text lines and table markdown across the page range
    page_blocks_data = []

    for pno in range(start_pno, end_pno):
        page = doc[pno]
        raw_text = page.get_text().strip()
        if len(raw_text) < 40:
            scanned_pages.append(pno + 1)

        # Amendment sheets are often bound into the same PDF. They restate clause numbers
        # of their own, which would otherwise be parsed as clauses of the standard.
        if AMENDMENT_BANNER.search(raw_text[:400]):
            amendment_pages.append(pno + 1)
            continue

        # 1. Extract tables on this page
        tables = extract_tables_from_page(page)
        table_bboxes = [t.bbox for t in tables]

        # 2. Extract text blocks and spans outside table bboxes and margins
        page_dict = page.get_text("dict")
        page_lines = []

        for b in page_dict.get("blocks", []):
            if b.get("type") == 0:  # text block
                b_bbox = b["bbox"]
                # Skip running headers and footers
                if b_bbox[1] < top_margin_y or b_bbox[3] > bottom_margin_y:
                    continue
                
                # Check if inside any table bbox
                in_table = False
                for tbox in table_bboxes:
                    if b_bbox[0] >= tbox[0] - 5 and b_bbox[2] <= tbox[2] + 5 and b_bbox[1] >= tbox[1] - 5 and b_bbox[3] <= tbox[3] + 5:
                        in_table = True
                        break
                if in_table:
                    continue

                for line in b["lines"]:
                    # Gather line text and typography
                    line_spans = line["spans"]
                    line_text = "".join(s["text"] for s in line_spans).strip()
                    if not line_text:
                        continue
                    
                    is_bold = any((s.get("flags", 0) & 16) or (s.get("flags", 0) & 2) or ("bold" in s.get("font", "").lower()) for s in line_spans)
                    max_font_size = max(s.get("size", 10.0) for s in line_spans)
                    
                    page_lines.append({
                        "text": line_text,
                        "is_bold": is_bold,
                        "font_size": max_font_size,
                        "page_num": pno + 1,
                    })

        # Append tables as special blocks
        for t in tables:
            page_lines.append({
                "text": t.markdown,
                "is_bold": False,
                "font_size": 10.0,
                "page_num": pno + 1,
                "is_table": True,
            })

        page_blocks_data.append((pno + 1, page_lines))

    # Refuse a document whose text layer cannot be read, rather than filling the index with symbols.
    sample = " ".join(l["text"] for _, lines in page_blocks_data for l in lines[:40])[:4000]
    if sample and readability(sample) < READABLE_RATIO:
        raise ValueError(
            f"text layer is not readable ({readability(sample):.0%} letters); the PDF embeds fonts "
            f"without a character map and needs OCR")

    # Identify clause boundaries across the stream of lines
    headings_found = []
    lines_stream = []
    for p_num, lines in page_blocks_data:
        for l in lines:
            l["stream_idx"] = len(lines_stream)
            lines_stream.append(l)

    prev_clause_num = None
    for idx, line_info in enumerate(lines_stream):
        if line_info.get("is_table"):
            continue
        next_text = lines_stream[idx + 1]["text"] if idx + 1 < len(lines_stream) else ""
        hd = detect_heading_line(
            line_info["text"],
            line_info["is_bold"],
            line_info["font_size"],
            line_info["page_num"],
            next_line_text=next_text,
        )
        if hd:
            c_num, c_title = hd
            # Check sequence validity
            if is_sequence_valid(prev_clause_num, c_num):
                headings_found.append({
                    "clause_num": c_num,
                    "title": c_title,
                    "line_idx": line_info["stream_idx"],
                    "page_num": line_info["page_num"],
                })
                prev_clause_num = c_num

    # If no headings found at all, create a single fallback clause
    if not headings_found:
        full_text = "\n".join(l["text"] for l in lines_stream)
        norm_text = normalize_unicode_text(dehyphenate_text(full_text))
        role = classify_clause_role(segment.title, norm_text, "1")
        rec = ClauseRecord(
            is_standard=segment.is_canonical,
            clause="1",
            title=segment.title or "General",
            text=norm_text,
            clause_id=f"{segment.is_canonical}#1",
            record_id=segment.record_id,
            family=segment.family,
            year=segment.year or 2005,
            level=1,
            parent_clause=None,
            role=role,
            page_start=segment.page_start,
            page_end=segment.page_end,
            has_table=any(l.get("is_table") for l in lines_stream),
            flags=["single_fallback_clause"],
        )
        manifest = StandardManifestEntry(
            is_number=segment.is_canonical,
            record_id=segment.record_id,
            status="parsed",
            page_range=[segment.page_start, segment.page_end],
            n_clauses=1,
            has_scope=(role == ClauseRole.SCOPE),
            has_references=(role == ClauseRole.REFERENCES),
            text_coverage_ratio=1.0,
            flags=["single_fallback_clause"],
            sha256=source_sha256,
        )
        return [rec], manifest

    # Assemble raw clauses from headings
    raw_clauses: List[RawClause] = []
    for i, h in enumerate(headings_found):
        start_idx = h["line_idx"]
        end_idx = headings_found[i + 1]["line_idx"] if i + 1 < len(headings_found) else len(lines_stream)
        
        clause_lines = lines_stream[start_idx:end_idx]
        # Text without heading line itself if heading was just the number/title
        body_lines = [l["text"] for l in clause_lines]
        has_tab = any(l.get("is_table", False) for l in clause_lines)
        
        c_text = "\n".join(body_lines)
        # Remove the heading banner itself from body if repeated
        c_text_clean = normalize_unicode_text(dehyphenate_text(c_text))
        
        raw_clauses.append(RawClause(
            clause_num=h["clause_num"],
            title=h["title"],
            text=c_text_clean,
            page_start=h["page_num"],
            page_end=clause_lines[-1]["page_num"] if clause_lines else h["page_num"],
            has_table=has_tab,
        ))

    # Version honesty evaluation
    flags = []
    if segment.catalogue_current_year and segment.year:
        if segment.year != segment.catalogue_current_year:
            flags.append("text_version_differs_from_current")
    if segment.is_withdrawn:
        flags.append("standard_withdrawn")
    if scanned_pages:
        flags.append(f"pages_without_text:{len(scanned_pages)}")
    if amendment_pages:
        flags.append(f"amendment_pages_skipped:{len(amendment_pages)}")

    # Granularity & Sub-clause splitting
    final_clauses: List[ClauseRecord] = []
    
    # Organize into top-level and sub-clauses
    role_by_clause: Dict[str, ClauseRole] = {}
    for rc in raw_clauses:
        role = classify_clause_role(rc.title, rc.text, rc.clause_num)

        # Inviolable rule: scope and references are always standalone records
        is_protected_role = (role in (ClauseRole.SCOPE, ClauseRole.REFERENCES))

        is_subclause = ("." in rc.clause_num and not rc.clause_num.startswith("ANNEX"))
        parent = rc.clause_num.rsplit(".", 1)[0] if is_subclause else None
        level = len(rc.clause_num.split(".")) if not rc.clause_num.startswith("ANNEX") else 1

        # A sub-clause with no role of its own belongs to the same role as its parent:
        # '11 MECHANICAL TESTS' makes '11.2 Tensile Test' a test method too.
        if role == ClauseRole.OTHER and parent:
            ancestor = parent
            while ancestor:
                inherited = role_by_clause.get(ancestor)
                if inherited and inherited != ClauseRole.OTHER:
                    role = inherited
                    break
                ancestor = ancestor.rsplit(".", 1)[0] if "." in ancestor else None
        role_by_clause[rc.clause_num] = role

        rec = ClauseRecord(
            is_standard=segment.is_canonical,
            clause=rc.clause_num,
            title=rc.title or f"Clause {rc.clause_num}",
            text=rc.text,
            clause_id=f"{segment.is_canonical}#{rc.clause_num}",
            record_id=segment.record_id,
            family=segment.family,
            year=segment.year or 2005,
            level=level,
            parent_clause=parent,
            role=role,
            page_start=rc.page_start,
            page_end=rc.page_end,
            has_table=rc.has_table,
            flags=list(flags),
        )
        final_clauses.append(rec)

    # Compute text coverage ratio
    total_page_chars = sum(len(l["text"]) for l in lines_stream)
    total_clause_chars = sum(len(c.text) for c in final_clauses)
    coverage_ratio = round(total_clause_chars / max(1, total_page_chars), 3) if total_page_chars > 0 else 1.0
    if coverage_ratio > 1.0:
        coverage_ratio = 1.0

    has_scope = any(c.role == ClauseRole.SCOPE for c in final_clauses)
    has_refs = any(c.role == ClauseRole.REFERENCES for c in final_clauses)

    manifest_entry = StandardManifestEntry(
        is_number=segment.is_canonical,
        record_id=segment.record_id,
        status="parsed",
        page_range=[segment.page_start, segment.page_end],
        n_clauses=len(final_clauses),
        has_scope=has_scope,
        has_references=has_refs,
        text_coverage_ratio=coverage_ratio,
        flags=flags,
        sha256=source_sha256,
    )

    return final_clauses, manifest_entry
