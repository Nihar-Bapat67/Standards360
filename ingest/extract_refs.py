"""Module A3: Cross-Reference Extractor CLI Entry Point.

Deterministic, offline extraction of Indian Standards cross-references from parsed clauses.
Produces data/edges.csv, data/edges.json, and data/a3_manifest.json.
"""

import os
import sys
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("pylib"))

import argparse
import csv
import json
import logging
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from contracts.edge import (
    EdgeRecord,
    RelationType,
    A3ManifestEntry,
)
from common.is_normalizer import (
    NormalizedIS,
    parse_is_number,
    norm_is_lookup_key,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Standards360.A3")

# Citation regex scanner - require uppercase IS or I.S. to prevent matching lowercase English verb 'is'
IS_CITATION_PATTERN = re.compile(
    r"\b(?:I\.?\s*S\.?|IS)\s*[:\s\-]?\s*(\d{3,5})"
    r"(?:\s*[\(/]\s*(?:Part|Sec|Section|part|sec|section)?\s*([A-Za-z0-9/\s]+)[\)/])?"
    r"(?:\s*[:\-]\s*(\d{4}))?"
)

# Syntactic classification pattern rules
PATTERN_RULES: List[Tuple[RelationType, re.Pattern, float]] = [
    (RelationType.TEST_METHOD, re.compile(r"(?:tested in accordance with|methods? (?:of tests?|given in|specified in)|tests? (?:as per|in|procedure)|testing|sampling and test).*?\bIS\b", re.I), 0.95),
    (RelationType.TERMINOLOGY, re.compile(r"(?:definitions?|terminology|glossary|symbols?)\s+(?:given in|as per|defined in).*?\bIS\b", re.I), 0.95),
    (RelationType.SAFETY, re.compile(r"(?:safety|protection|hazardous|fire safety)\s+(?:as per|requirements of|in accordance with)?.*?\bIS\b", re.I), 0.90),
    (RelationType.INSTALLATION, re.compile(r"(?:laying|installation|fixing|erection|workmanship|code of practice for)\s+(?:as per|in accordance with)?.*?\bIS\b", re.I), 0.90),
    (RelationType.RELATED_PRODUCT, re.compile(r"(?:raw material|materials?|cement|aggregate|sand|steel|brick|lime|fly ash|pozzolana|slag|gypsum|fitting|timber|glass|admixture)\b(?:\s+\w+){0,3}\s+(?:shall conform to|conforming to|shall be in accordance with|shall comply with).*?\bIS\b", re.I), 0.90),
    (RelationType.NORMATIVE_REFERENCE, re.compile(r"(?:shall conform to|shall comply with|conforming to|complying with|in accordance with|shall be as specified in).*?\bIS\b", re.I), 0.85),
]


class CatalogueReferenceStore:
    """In-memory index of catalogue standards for validation and relation priors."""
    def __init__(self, db_path: str):
        self.exact_keys = set()
        self.family_keys = set()
        self.base_numbers = set()
        self.aspects: Dict[str, str] = {}
        self.titles: Dict[str, str] = {}
        
        con = sqlite3.connect(os.path.abspath(db_path))
        cur = con.cursor()
        rows = cur.execute("SELECT record_id, is_number, title, aspect FROM standards").fetchall()
        for rid, num, title, aspect in rows:
            if not num:
                continue
            k = norm_is_lookup_key(num)
            self.exact_keys.add(k)
            
            parsed = parse_is_number(num)
            if parsed:
                fam_k = norm_is_lookup_key(parsed.family)
                self.family_keys.add(fam_k)
                self.base_numbers.add(parsed.base_number)
                if aspect:
                    self.aspects[fam_k] = aspect.strip()
                    self.aspects[parsed.base_number] = aspect.strip()
                if title:
                    self.titles[fam_k] = title.strip()
                    self.titles[parsed.base_number] = title.strip()

    def is_in_catalogue(self, target: NormalizedIS) -> bool:
        """Check if target standard exists in catalogue."""
        if norm_is_lookup_key(target.canonical) in self.exact_keys:
            return True
        if norm_is_lookup_key(target.family) in self.family_keys:
            return True
        return target.base_number in self.base_numbers

    def get_aspect(self, target: NormalizedIS) -> Optional[str]:
        """Get the aspect of the target standard if recorded."""
        fam_k = norm_is_lookup_key(target.family)
        if fam_k in self.aspects:
            return self.aspects[fam_k]
        return self.aspects.get(target.base_number)


def extract_evidence_sentence(text: str, match_start: int, match_end: int) -> str:
    """Extract clean, self-contained sentence surrounding the citation."""
    start = max(0, match_start - 120)
    end = min(len(text), match_end + 120)

    # Walk backwards to find sentence start, avoiding abbreviations like Rs., No., etc.
    prev_periods = [i for i in range(max(0, match_start - 140), match_start) if text[i] == '.']
    for p in reversed(prev_periods):
        prefix = text[max(0, p - 6):p + 1].strip()
        if not re.search(r"\b(?:Rs|No|Cl|Fig|Vol|Ref|i\.e|e\.g)\.$", prefix, re.I):
            start = p + 1
            break

    next_periods = [i for i in range(match_end, min(len(text), match_end + 140)) if text[i] == '.']
    for p in next_periods:
        prefix = text[max(0, p - 6):p + 1].strip()
        if not re.search(r"\b(?:Rs|No|Cl|Fig|Vol|Ref|i\.e|e\.g)\.$", prefix, re.I):
            end = p + 1
            break

    sentence = text[start:end].replace("\n", " ").strip()
    sentence = re.sub(r"\s+", " ", sentence)
    return sentence


def classify_relation(
    source_is_obj: NormalizedIS,
    target_is_obj: NormalizedIS,
    clause_role: str,
    clause_title: str,
    evidence_text: str,
    cat_aspect: Optional[str],
) -> Tuple[RelationType, float]:
    """Classify relationship type and assign calibrated confidence."""
    # 1. Self-family part check (e.g. IS 456 (Part 1) citing IS 456 (Part 2))
    if source_is_obj.base_number == target_is_obj.base_number:
        if source_is_obj.part != target_is_obj.part:
            return RelationType.SAME_FAMILY_PART, 0.95

    # 2. Check contextual title indicating raw materials
    if re.search(r"\b(?:raw\s+materials?|materials?|constituents?)\b", clause_title, re.I):
        if cat_aspect and "product specification" in cat_aspect.lower():
            return RelationType.RELATED_PRODUCT, 0.90

    # 3. Check syntactic rules against evidence sentence
    for rel_type, pattern, base_conf in PATTERN_RULES:
        if pattern.search(evidence_text):
            conf = base_conf
            if cat_aspect:
                if rel_type == RelationType.TEST_METHOD and "test" in cat_aspect.lower():
                    conf = min(0.98, conf + 0.05)
                elif rel_type == RelationType.TERMINOLOGY and "terminology" in cat_aspect.lower():
                    conf = min(0.98, conf + 0.05)
                elif rel_type == RelationType.SAFETY and "safety" in cat_aspect.lower():
                    conf = min(0.98, conf + 0.05)
                elif rel_type == RelationType.RELATED_PRODUCT and "product specification" in cat_aspect.lower():
                    conf = min(0.98, conf + 0.05)
            return rel_type, round(conf, 3)

    # 4. Check authoritative catalogue aspect prior (methods of test, terminology, safety)
    if cat_aspect:
        aspect_lower = cat_aspect.lower()
        if "methods of test" in aspect_lower:
            return RelationType.TEST_METHOD, 0.92
        if "terminology" in aspect_lower:
            return RelationType.TERMINOLOGY, 0.92
        if "safety" in aspect_lower:
            return RelationType.SAFETY, 0.90
        if "code of practice" in aspect_lower:
            return RelationType.INSTALLATION, 0.85

    # 5. Use Clause Role as contextual signal
    if clause_role == "test_methods":
        return RelationType.TEST_METHOD, 0.90
    if clause_role == "terminology":
        return RelationType.TERMINOLOGY, 0.90
    if clause_role in ("packing", "marking"):
        return RelationType.RELATED_PRODUCT, 0.85
    if clause_role == "references":
        return RelationType.NORMATIVE_REFERENCE, 0.88

    # 6. Aspect prior fallback for products
    if cat_aspect:
        if "product specification" in cat_aspect.lower():
            return RelationType.RELATED_PRODUCT, 0.85

    # 7. Default normative reference for requirements prose
    return RelationType.NORMATIVE_REFERENCE, 0.75


def process_clause_citations(
    clause: Dict[str, Any],
    catalogue: CatalogueReferenceStore,
) -> Tuple[List[EdgeRecord], int, int]:
    """Scan a clause for citations and emit validated EdgeRecord instances.

    Returns: (emitted_edges, n_citations_found, n_rejected_false_positive)
    """
    text = clause.get("text", "")
    source_is_str = clause.get("is", "")
    clause_id = clause.get("clause_id", "")
    clause_role = clause.get("role", "other")
    clause_title = clause.get("title", "")

    source_norm = parse_is_number(source_is_str)
    if not source_norm:
        return [], 0, 0

    matches = list(IS_CITATION_PATTERN.finditer(text))
    if not matches:
        return [], 0, 0

    edges: List[EdgeRecord] = []
    n_found = len(matches)
    n_rejected = 0

    for m in matches:
        raw_match = m.group(0)
        target_norm = parse_is_number(raw_match)
        if not target_norm:
            n_rejected += 1
            continue

        # False-positive rejection 1: Exact reflexive self-mention (from_is == to_is without part diff)
        if source_norm.base_number == target_norm.base_number:
            if source_norm.part == target_norm.part:
                n_rejected += 1
                continue

        # Extract evidence sentence
        evidence = extract_evidence_sentence(text, m.start(), m.end())

        # False-positive rejection 2: Table header or price figures containing 'IS'
        context_window = text[max(0, m.start() - 30):min(len(text), m.end() + 30)]
        if re.search(r"\bPrice\s+(?:Rs\.?|INR|\$)?\s*IS\b", context_window, re.I) or re.search(r"\bRs\.?\s*IS\b", context_window, re.I):
            n_rejected += 1
            continue

        # Target catalogue resolution
        in_catalogue = catalogue.is_in_catalogue(target_norm)
        cat_aspect = catalogue.get_aspect(target_norm)

        # Classify relationship & confidence
        relation, confidence = classify_relation(
            source_is_obj=source_norm,
            target_is_obj=target_norm,
            clause_role=clause_role,
            clause_title=clause_title,
            evidence_text=evidence,
            cat_aspect=cat_aspect,
        )

        flags = []
        if not in_catalogue:
            flags.append("target_outside_catalogue_scope")
            confidence = max(0.40, confidence - 0.20)
        if relation == RelationType.SAME_FAMILY_PART:
            flags.append("same_family_part")

        edge = EdgeRecord(
            from_is=source_is_str,
            to_is=target_norm.canonical,
            relation=relation,
            confidence=round(confidence, 3),
            clause_id=clause_id,
            evidence_text=evidence,
            to_in_catalogue=in_catalogue,
            extraction_method="regex+nlp_prior",
            flags=flags,
        )
        edges.append(edge)

    return edges, n_found, n_rejected


def run_a3_pipeline(
    clauses_path: str,
    catalogue_path: str,
    output_dir: str,
    only_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute complete A3 extraction pipeline across all clauses."""
    logger.info("Initializing A3 Cross-Reference Extractor...")
    catalogue = CatalogueReferenceStore(catalogue_path)
    logger.info(f"Loaded catalogue reference store: {len(catalogue.base_numbers)} unique standard families")

    with open(clauses_path, "r", encoding="utf-8") as f:
        clauses = json.load(f)
    logger.info(f"Loaded {len(clauses)} clauses from {clauses_path}")

    if only_filter:
        norm_filter = norm_is_lookup_key(only_filter)
        clauses = [c for c in clauses if norm_filter in norm_is_lookup_key(c.get("is", "")) or norm_filter in norm_is_lookup_key(c.get("family", ""))]
        logger.info(f"Applied filter '--only {only_filter}': {len(clauses)} clauses retained")

    out_p = Path(output_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    all_edges: List[EdgeRecord] = []
    manifest_by_standard: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "n_citations_found": 0,
        "n_edges_emitted": 0,
        "n_rejected_false_positive": 0,
        "n_target_not_in_catalogue": 0,
    })

    # Group clauses by standard to track manifest
    for c in clauses:
        std_is = c.get("is", "")
        edges, n_found, n_rej = process_clause_citations(c, catalogue)
        all_edges.extend(edges)

        m = manifest_by_standard[std_is]
        m["n_citations_found"] += n_found
        m["n_edges_emitted"] += len(edges)
        m["n_rejected_false_positive"] += n_rej
        for e in edges:
            if not e.to_in_catalogue:
                m["n_target_not_in_catalogue"] += 1

    # Deterministic sorting: sorted by (from_is, to_is, clause_id)
    all_edges.sort(key=lambda e: (e.from_is, e.to_is, e.clause_id))

    # Output 1: data/edges.json
    edges_json_file = out_p / "edges.json"
    with open(edges_json_file, "w", encoding="utf-8") as f:
        json.dump([e.model_dump() for e in all_edges], f, indent=2, ensure_ascii=False)

    # Output 2: data/edges.csv (per manual §14: from, relation, to, clause, confidence, evidence)
    edges_csv_file = out_p / "edges.csv"
    with open(edges_csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["from", "relation", "to", "clause", "confidence", "evidence"])
        for e in all_edges:
            writer.writerow([
                e.from_is,
                e.relation.value,
                e.to_is,
                e.clause_id,
                e.confidence,
                e.evidence_text,
            ])

    # Output 3: data/a3_manifest.json
    manifest_file = out_p / "a3_manifest.json"
    manifest_rows = []
    for std_num in sorted(manifest_by_standard.keys()):
        stats = manifest_by_standard[std_num]
        manifest_rows.append(A3ManifestEntry(
            is_number=std_num,
            n_citations_found=stats["n_citations_found"],
            n_edges_emitted=stats["n_edges_emitted"],
            n_rejected_false_positive=stats["n_rejected_false_positive"],
            n_target_not_in_catalogue=stats["n_target_not_in_catalogue"],
        ).model_dump())

    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_rows, f, indent=2, ensure_ascii=False)

    logger.info("A3 Cross-Reference Extraction Complete.")
    logger.info(f"Total Edges Emitted: {len(all_edges)}")
    logger.info(f"Edges JSON: {edges_json_file}")
    logger.info(f"Edges CSV:  {edges_csv_file}")
    logger.info(f"Manifest:   {manifest_file}")

    return {
        "edges_count": len(all_edges),
        "manifest_count": len(manifest_rows),
    }


def main():
    parser = argparse.ArgumentParser(description="Module A3: Cross-Reference Extractor")
    parser.add_argument("--clauses", "-c", default="data/clauses.json", help="Path to clauses.json")
    parser.add_argument("--catalogue", default="catalogue/catalogue.db", help="Path to catalogue.db")
    parser.add_argument("--out", "-o", default="data", help="Output directory")
    parser.add_argument("--only", default=None, help="Filter to specific standard")
    parser.add_argument("--resume", action="store_true", help="Resume from cache")
    parser.add_argument("--llm-batch-size", type=int, default=50, help="LLM batch size")

    args = parser.parse_args()
    run_a3_pipeline(
        clauses_path=args.clauses,
        catalogue_path=args.catalogue,
        output_dir=args.out,
        only_filter=args.only,
    )


if __name__ == "__main__":
    main()
