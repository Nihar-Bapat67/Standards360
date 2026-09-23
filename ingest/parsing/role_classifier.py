"""Semantic Clause Role Classifier.

Maps clause titles and text characteristics to standardized ClauseRole enum values.
Decoupled from clause numbers (never assumes Clause 2 == References).
"""

import re
from contracts.clause import ClauseRole


ROLE_PATTERNS = [
    (ClauseRole.FOREWORD, re.compile(r"^\s*(?:FOREWORD|PREFACE)\b", re.IGNORECASE)),
    (ClauseRole.SCOPE, re.compile(r"^\s*(?:SCOPE|FIELD\s+OF\s+APPLICATION)\b", re.IGNORECASE)),
    (ClauseRole.REFERENCES, re.compile(r"^\s*(?:REFERENCES|NORMATIVE\s+REFERENCES|LIST\s+OF\s+REFERRED\s+INDIAN\s+STANDARDS|STANDARDS\s+FOR\s+REFERENCE)\b", re.IGNORECASE)),
    (ClauseRole.TERMINOLOGY, re.compile(r"^\s*(?:TERMINOLOGY|DEFINITIONS|GLOSSARY|SYMBOLS|NOTATIONS)\b", re.IGNORECASE)),
    (ClauseRole.SAMPLING, re.compile(r"^\s*(?:SAMPLING|LOT\s+SIZE|SCALE\s+OF\s+SAMPLING|CRITERIA\s+FOR\s+CONFORMITY)\b", re.IGNORECASE)),
    # Named tests carry the test-method role too; BIS standards label them by the test, not by the word 'method'
    (ClauseRole.TEST_METHODS, re.compile(r"^\s*(?:TESTS|TEST\s+METHODS|METHODS\s+OF\s+TEST(?:ING)?|METHODS\s+OF\s+SAMPLING\s+AND\s+TEST|ACCEPTANCE\s+TESTS|TYPE\s+TESTS|ROUTINE\s+TESTS|MECHANICAL\s+TESTS?|CHEMICAL\s+ANALYSIS|RETEST(?:S)?|(?:TENSILE|BEND|COLD\s+BEND|FLATTENING|WRAPPING|IMPACT|DUCTILITY|COATING|HYDRAULIC|LEAK|DRIFT\s+EXPANSION|CRUSHING|ADHESION|MASS\s+OF\s+COATING)\s+TEST)\b", re.IGNORECASE)),
    (ClauseRole.MARKING, re.compile(r"^\s*(?:MARKING|LABELLING|MARKING\s+AND\s+PACKING)\b", re.IGNORECASE)),
    (ClauseRole.PACKING, re.compile(r"^\s*(?:PACKING|PACKAGING|DELIVERY)\b", re.IGNORECASE)),
    (ClauseRole.ANNEX, re.compile(r"^\s*(?:ANNEX|APPENDIX)\b", re.IGNORECASE)),
    (ClauseRole.REQUIREMENTS, re.compile(r"^\s*(?:REQUIREMENTS|CHEMICAL\s+REQUIREMENTS|PHYSICAL\s+REQUIREMENTS|RAW\s+MATERIALS?|MANUFACTURE|PROPERTIES|MECHANICAL\s+PROPERTIES|WORKMANSHIP|CONSTRUCTION|FINISH|DIMENSIONS|DESIGN\s+CRITERIA|SPECIFICATION|CHEMICAL\s+COMPOSITION|SIZES|LENGTHS|TOLERANCES|DESIGNATION|SUPPLY\s+OF\s+MATERIAL|MATERIAL|GALVANIZING|GALVANIZATION|COATING|STRAIGHTNESS|FREEDOM\s+FROM\s+DEFECTS|STORAGE|OILING\s+AND\s+PAINTING)\b", re.IGNORECASE)),
]


def classify_clause_role(title: str, text: str, clause_num: str = "") -> ClauseRole:
    """Classify the semantic role of a clause from its title and body content."""
    title_clean = (title or "").strip()
    
    # 1. Check title against explicit patterns
    for role, pat in ROLE_PATTERNS:
        if pat.search(title_clean):
            return role
    
    # 2. Check clause number if special (e.g. "ANNEX A")
    if clause_num.upper().startswith(("ANNEX", "APPENDIX")):
        return ClauseRole.ANNEX
    if clause_num == "0" and ("FOREWORD" in title_clean.upper() or "PREFACE" in title_clean.upper()):
        return ClauseRole.FOREWORD

    # 3. Content heuristics for references when title is ambiguous or absent
    text_snippet = text[:500].upper()
    if re.search(r"\b(?:LIST\s+OF\s+REFERRED\s+INDIAN\s+STANDARDS|NORMATIVE\s+REFERENCES)\b", text_snippet):
        return ClauseRole.REFERENCES
    
    # Check if text heavily consists of IS references table
    is_citations = re.findall(r"\bIS\s+\d{3,5}\b", text[:500])
    if len(is_citations) >= 3 and ("STANDARD" in text_snippet or "TITLE" in text_snippet):
        return ClauseRole.REFERENCES

    # 4. Check for requirement terms in body
    if any(k in text_snippet for k in ["SHALL COMPLY WITH", "REQUIREMENT", "CONFORM TO"]):
        return ClauseRole.REQUIREMENTS
    
    return ClauseRole.OTHER

