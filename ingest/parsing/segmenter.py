"""Compilation Volume Segmenter and Boundary Validator.

Segments compilation volumes (such as SP 21) into per-standard page ranges,
extracts document-asserted standard numbers and years, and validates every
boundary against the A1 SQLite catalogue.
"""

import re
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
import fitz

from ingest.parsing.normalizer import parse_is_identifier, is_lookup_key


class StandardSegment:
    def __init__(
        self,
        raw_header: str,
        is_canonical: str,
        family: str,
        year: Optional[int],
        title: str,
        revision: str,
        page_start: int,
        page_end: int,
        record_id: Optional[int],
        catalogue_is: Optional[str],
        catalogue_current_year: Optional[int],
        is_withdrawn: bool,
    ):
        self.raw_header = raw_header
        self.is_canonical = is_canonical
        self.family = family
        self.year = year
        self.title = title
        self.revision = revision
        self.page_start = page_start
        self.page_end = page_end
        self.record_id = record_id
        self.catalogue_is = catalogue_is
        self.catalogue_current_year = catalogue_current_year
        self.is_withdrawn = is_withdrawn

    def __repr__(self):
        return f"<Segment {self.is_canonical} pages {self.page_start}-{self.page_end} (rec={self.record_id})>"


def load_catalogue_lookup(db_path: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Load normalized catalogue entries for fast O(1) matching."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT record_id, is_number, title, withdrawn, superseded_by, superseding_is FROM standards"
    ).fetchall()
    
    exact_lookup: Dict[str, Dict[str, Any]] = {}
    family_lookup: Dict[str, List[Dict[str, Any]]] = {}

    for rid, num, title, wd, sup_by, sup_is in rows:
        m = re.match(r"(IS\s*[:\s]?\s*\d+(?:\s*\([^\)]+\))?)(?:\s*[:\-]\s*(\d{4}))?", num or "", re.I)
        year = int(m.group(2)) if m and m.group(2) else None
        
        entry = {
            "record_id": rid,
            "is_number": num,
            "title": title,
            "withdrawn": bool(wd),
            "superseded_by": sup_by,
            "superseding_is": sup_is,
            "year": year,
        }
        
        # Key 1: exact normalized number with year. BIS publishes the same number on more than one
        # record, so never let a withdrawn record displace the current one for the same key.
        key = is_lookup_key(num)
        existing = exact_lookup.get(key)
        if existing is None or (existing["withdrawn"] and not entry["withdrawn"]):
            exact_lookup[key] = entry
        
        # Key 2: family only without year
        if m:
            fam_key = is_lookup_key(m.group(1))
            family_lookup.setdefault(fam_key, []).append(entry)

    return exact_lookup, family_lookup


def segment_compilation_pdf(
    pdf_path: str,
    catalogue_db_path: str,
) -> Tuple[List[StandardSegment], List[Dict[str, Any]]]:
    """Segment compilation PDF into validated per-standard page ranges."""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    
    exact_lookup, family_lookup = load_catalogue_lookup(catalogue_db_path)
    
    raw_candidates = []
    
    # Regex to detect SUMMARY OF IS banner
    banner_pattern = re.compile(
        r"SUMMARY\s+OF\s*\n?\s*(IS\s*[:\s]?\s*\d+(?:\s*\([^\)]+\))?[^\n]*)",
        re.IGNORECASE
    )

    for pno in range(total_pages):
        page = doc[pno]
        text = page.get_text("text")
        if "SUMMARY OF" in text.upper():
            m = banner_pattern.search(text)
            if m:
                banner_line = m.group(1).strip()
                # Clean up newlines in banner
                banner_clean = re.sub(r"\s+", " ", banner_line)
                
                # Check for revision in subsequent lines
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                rev = ""
                for l in lines[:10]:
                    if re.search(r"\((?:First|Second|Third|Fourth|Fifth|Sixth|[0-9]+th)\s+Revision\)", l, re.I):
                        rev = l
                        break

                raw_candidates.append({
                    "page": pno + 1,
                    "banner": banner_clean,
                    "rev": rev,
                })

    segments: List[StandardSegment] = []
    quarantined: List[Dict[str, Any]] = []

    for idx, cand in enumerate(raw_candidates):
        page_start = cand["page"]
        # End page is the page before next standard, or total_pages for the last standard
        if idx + 1 < len(raw_candidates):
            page_end = raw_candidates[idx + 1]["page"] - 1
        else:
            page_end = total_pages
        
        # Ensure start <= end
        if page_end < page_start:
            page_end = page_start

        # Parse IS number, family, and year
        canon_is, family, year = parse_is_identifier(cand["banner"])
        if not canon_is or not family:
            quarantined.append({
                "is_number": cand["banner"][:40],
                "reason": "unparseable_banner",
                "details": f"Could not extract standard number from banner '{cand['banner']}' on page {page_start}",
                "page_range": [page_start, page_end],
            })
            continue

        # Extract title from remainder of banner
        title = ""
        m_title = re.search(r"\d{4}\s+(.+)$", cand["banner"])
        if m_title:
            title = m_title.group(1).strip()
        else:
            m_title2 = re.search(r"IS\s*[:\s]?\s*\d+(?:\s*\([^\)]+\))?\s*(.+)$", cand["banner"], re.I)
            if m_title2:
                title = m_title2.group(1).strip()

        # Validate against catalogue
        lookup_exact = is_lookup_key(canon_is)
        lookup_fam = is_lookup_key(family)

        matched_record = None
        if lookup_exact in exact_lookup:
            matched_record = exact_lookup[lookup_exact]
        elif lookup_fam in family_lookup:
            # Match family (e.g. catalogue has 2015 edition, document has 1989 edition)
            candidates = family_lookup[lookup_fam]
            # Prefer active non-withdrawn, or highest year
            candidates_sorted = sorted(candidates, key=lambda x: (not x["withdrawn"], x["year"] or 0), reverse=True)
            matched_record = candidates_sorted[0]

        if matched_record:
            segment = StandardSegment(
                raw_header=cand["banner"],
                is_canonical=canon_is,
                family=family,
                year=year or matched_record.get("year"),
                title=title or matched_record.get("title", ""),
                revision=cand["rev"],
                page_start=page_start,
                page_end=page_end,
                record_id=matched_record["record_id"],
                catalogue_is=matched_record["is_number"],
                catalogue_current_year=matched_record.get("year"),
                is_withdrawn=matched_record.get("withdrawn", False),
            )
            segments.append(segment)
        else:
            quarantined.append({
                "is_number": canon_is,
                "reason": "not_in_catalogue",
                "details": f"Standard '{canon_is}' (family '{family}') from page {page_start} not found in A1 catalogue.db",
                "page_range": [page_start, page_end],
            })

    return segments, quarantined

