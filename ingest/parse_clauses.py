"""Module A2: Document Parser & Clause Splitter CLI Entry Point.

Deterministic, offline extraction of Indian Standards PDFs into structured clauses.
Generates data/clauses.json, data/parse_manifest.json, and data/quarantine.json.
"""

import os
import sys
# Ensure pylib and root are in sys.path
sys.path.insert(0, os.path.abspath("pylib"))
sys.path.insert(0, os.path.abspath("."))

import argparse
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import fitz

from contracts.clause import (
    ClauseRecord,
    StandardManifestEntry,
    QuarantineEntry,
)
from ingest.parsing.clause_splitter import (
    parse_standard_pages,
    compute_sha256,
)
from ingest.parsing.segmenter import (
    segment_compilation_pdf,
    StandardSegment,
    load_catalogue_lookup,
)
from ingest.parsing.normalizer import (
    parse_is_identifier,
    is_lookup_key,
)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Standards360.A2")


def clause_sort_key(clause: str) -> Tuple[int, Tuple[int, ...], str]:
    """Order clauses the way they are printed: '2' before '10', annexes last."""
    c = (clause or "").strip()
    if c.upper().startswith(("ANNEX", "APPENDIX")):
        return (2, (), c.upper())
    try:
        return (1, tuple(int(p) for p in c.split(".")), "")
    except ValueError:
        return (3, (), c)


def parse_individual_pdf(
    pdf_path: Path,
    exact_lookup: Dict[str, Any],
    family_lookup: Dict[str, List[Any]],
) -> Optional[StandardSegment]:
    """Inspect the first pages of an individual PDF to extract its IS identity and match catalogue."""
    doc = fitz.open(str(pdf_path))
    if len(doc) == 0:
        return None

    # Search first 3 pages for IS number and year
    sample_text = ""
    for pno in range(min(3, len(doc))):
        sample_text += "\n" + doc[pno].get_text()

    canon_is, family, year = parse_is_identifier(sample_text)
    if not canon_is or not family:
        # Fallback to filename (e.g. is269_2013.pdf)
        # File names come in as 'is.1786.2008' or 'is_1786_2008'; both separators become spaces.
        fname = pdf_path.stem
        m_fn = parse_is_identifier(re.sub(r"[._]", " ", fname))
        if m_fn[0]:
            canon_is, family, year = m_fn

    if not canon_is or not family:
        return None

    # Match against catalogue
    exact_key = is_lookup_key(canon_is)
    fam_key = is_lookup_key(family)

    matched = None
    if exact_key in exact_lookup:
        matched = exact_lookup[exact_key]
    elif fam_key in family_lookup:
        cands = family_lookup[fam_key]
        cands_sorted = sorted(cands, key=lambda x: (not x["withdrawn"], x["year"] or 0), reverse=True)
        matched = cands_sorted[0]

    return StandardSegment(
        raw_header=canon_is,
        is_canonical=canon_is,
        family=family,
        year=year or (matched.get("year") if matched else None),
        title=matched.get("title", "") if matched else "",
        revision="",
        page_start=1,
        page_end=len(doc),
        record_id=matched.get("record_id") if matched else None,
        catalogue_is=matched.get("is_number") if matched else None,
        catalogue_current_year=matched.get("year") if matched else None,
        is_withdrawn=matched.get("withdrawn", False) if matched else False,
    )


def process_segment_task(
    pdf_path_str: str,
    seg: StandardSegment,
    source_sha256: str,
    parsed_dir: Path,
    max_chars: int,
    top_y: float,
    bot_y: float,
    resume: bool,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Worker task to parse a single segment."""
    safe_name = seg.is_canonical.replace(":", "_").replace(" ", "_").replace("/", "_").replace("(", "_").replace(")", "_")
    cache_file = parsed_dir / f"{safe_name}.json"

    if resume and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return seg.is_canonical, data["clauses"], data["manifest"]
        except Exception:
            pass

    # Open doc in thread-safe local handle
    doc = fitz.open(pdf_path_str)
    clauses, manifest = parse_standard_pages(
        doc=doc,
        segment=seg,
        source_sha256=source_sha256,
        max_clause_chars=max_chars,
        top_margin_y=top_y,
        bottom_margin_y=bot_y,
    )
    doc.close()

    clause_dicts = [c.model_dump(by_alias=True) for c in clauses]
    manifest_dict = manifest.model_dump(by_alias=True)

    # Save intermediate cache
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"clauses": clause_dicts, "manifest": manifest_dict}, f, indent=2, ensure_ascii=False)

    return seg.is_canonical, clause_dicts, manifest_dict


def run_pipeline(
    input_path: str,
    catalogue_path: str,
    output_dir: str,
    config_path: str,
    only_filter: Optional[str] = None,
    resume: bool = False,
    workers: int = 4,
) -> Dict[str, Any]:
    """Execute the complete A2 parsing pipeline."""
    # Load config
    cfg = {
        "max_clause_chars": 3000,
        "top_margin_max_y": 95.0,
        "bottom_margin_min_y": 750.0,
    }
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir = out_dir / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)

    exact_lookup, family_lookup = load_catalogue_lookup(catalogue_path)
    logger.info(f"Loaded catalogue: {len(exact_lookup)} exact standard entries")

    input_p = Path(input_path)
    segments_to_process: List[Tuple[str, StandardSegment]] = []
    quarantined_records: List[Dict[str, Any]] = []

    if input_p.is_file():
        source_sha = compute_sha256(str(input_p))
        doc_test = fitz.open(str(input_p))
        
        # Check if compilation volume (e.g. SP 21 with > 100 pages and SUMMARY OF banners)
        is_compilation = False
        if len(doc_test) > 50:
            for pno in range(min(25, len(doc_test))):
                if "SUMMARY OF" in doc_test[pno].get_text("text").upper():
                    is_compilation = True
                    break
        doc_test.close()

        if is_compilation:
            logger.info(f"Detected compilation volume: {input_p.name} ({len(fitz.open(str(input_p)))} pages). Segmenting...")
            segs, quars = segment_compilation_pdf(str(input_p), catalogue_path)
            logger.info(f"Segmenter identified {len(segs)} valid standards, {len(quars)} quarantined entries")
            for s in segs:
                segments_to_process.append((str(input_p), s))
            quarantined_records.extend(quars)
        else:
            logger.info(f"Processing single standard PDF: {input_p.name}")
            seg = parse_individual_pdf(input_p, exact_lookup, family_lookup)
            if seg:
                segments_to_process.append((str(input_p), seg))
            else:
                quarantined_records.append({
                    "is_number": input_p.stem,
                    "reason": "unmatched_single_pdf",
                    "details": f"Could not map individual PDF '{input_p.name}' to catalogue",
                    "page_range": [1, len(fitz.open(str(input_p)))],
                })
    elif input_p.is_dir():
        pdf_files = list(input_p.glob("*.pdf"))
        logger.info(f"Processing directory with {len(pdf_files)} PDFs")
        for pdf_f in pdf_files:
            seg = parse_individual_pdf(pdf_f, exact_lookup, family_lookup)
            if seg:
                segments_to_process.append((str(pdf_f), seg))
            else:
                quarantined_records.append({
                    "is_number": pdf_f.stem,
                    "reason": "unmatched_single_pdf",
                    "details": f"Could not map '{pdf_f.name}' to catalogue",
                    "page_range": [1, 1],
                })

    # Apply --only filter if specified
    if only_filter:
        norm_filter = is_lookup_key(only_filter)
        filtered = [
            (p, s) for (p, s) in segments_to_process
            if norm_filter in is_lookup_key(s.is_canonical) or norm_filter in is_lookup_key(s.family)
        ]
        logger.info(f"Applied filter '--only {only_filter}': {len(filtered)} standards matched")
        segments_to_process = filtered

    logger.info(f"Starting execution for {len(segments_to_process)} standards with {workers} workers...")

    all_clauses: List[Dict[str, Any]] = []
    manifest_rows: List[Dict[str, Any]] = []

    # Process segments concurrently
    sha_cache: Dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for pdf_path_str, seg in segments_to_process:
            if pdf_path_str not in sha_cache:
                sha_cache[pdf_path_str] = compute_sha256(pdf_path_str)
            sha = sha_cache[pdf_path_str]

            fut = executor.submit(
                process_segment_task,
                pdf_path_str,
                seg,
                sha,
                parsed_dir,
                cfg["max_clause_chars"],
                cfg["top_margin_max_y"],
                cfg["bottom_margin_min_y"],
                resume,
            )
            future_map[fut] = seg.is_canonical

        completed_count = 0
        for fut in as_completed(future_map):
            canon_name = future_map[fut]
            completed_count += 1
            try:
                name, c_list, m_row = fut.result()
                all_clauses.extend(c_list)
                manifest_rows.append(m_row)
                if completed_count % 50 == 0 or completed_count == len(segments_to_process):
                    logger.info(f"Progress: [{completed_count}/{len(segments_to_process)}] standards processed")
            except Exception as e:
                logger.error(f"Error processing standard '{canon_name}': {e}")
                quarantined_records.append({
                    "is_number": canon_name,
                    "reason": "parser_exception",
                    "details": str(e),
                })

    # For quarantined items, add to manifest as well
    for q in quarantined_records:
        manifest_rows.append({
            "is_number": q["is_number"],
            "record_id": None,
            "status": "quarantined",
            "reason": q.get("reason"),
            "page_range": q.get("page_range", []),
            "n_clauses": 0,
            "has_scope": False,
            "has_references": False,
            "text_coverage_ratio": 0.0,
            "flags": [q.get("reason", "quarantined")],
            "sha256": "N/A",
        })

    # Sort deterministically, in reading order: foreword, then numbered clauses by value
    # ('2' before '10'), then annexes.
    all_clauses.sort(key=lambda x: (x.get("is", ""), clause_sort_key(x.get("clause", ""))))
    manifest_rows.sort(key=lambda x: x.get("is_number", ""))
    quarantined_records.sort(key=lambda x: x.get("is_number", ""))

    # Output filenames
    clauses_file = out_dir / "clauses.json"
    manifest_file = out_dir / "parse_manifest.json"
    quarantine_file = out_dir / "quarantine.json"

    with open(clauses_file, "w", encoding="utf-8") as f:
        json.dump(all_clauses, f, indent=2, ensure_ascii=False)

    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_rows, f, indent=2, ensure_ascii=False)

    with open(quarantine_file, "w", encoding="utf-8") as f:
        json.dump(quarantined_records, f, indent=2, ensure_ascii=False)

    logger.info(f"Pipeline finished successfully.")
    logger.info(f"Total clauses saved: {len(all_clauses)} -> {clauses_file}")
    logger.info(f"Manifest saved: {len(manifest_rows)} rows -> {manifest_file}")
    logger.info(f"Quarantined standards: {len(quarantined_records)} -> {quarantine_file}")

    return {
        "clauses_count": len(all_clauses),
        "manifest_count": len(manifest_rows),
        "quarantine_count": len(quarantined_records),
    }


def main():
    parser = argparse.ArgumentParser(description="A2: Document Parser & Clause Splitter")
    parser.add_argument("--input", "-i", default="sp21_2005.pdf", help="Path to PDF file or directory")
    parser.add_argument("--catalogue", "-c", default="catalogue/catalogue.db", help="Path to catalogue.db")
    parser.add_argument("--out", "-o", default="data", help="Output directory")
    parser.add_argument("--config", default="config/parser_config.json", help="Path to config file")
    parser.add_argument("--only", default=None, help="Filter to single standard or family (e.g. 'IS 269')")
    parser.add_argument("--resume", action="store_true", help="Resume from intermediate parsed files")
    parser.add_argument("--workers", "-w", type=int, default=4, help="Number of worker threads")

    args = parser.parse_args()

    run_pipeline(
        input_path=args.input,
        catalogue_path=args.catalogue,
        output_dir=args.out,
        config_path=args.config,
        only_filter=args.only,
        resume=args.resume,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
