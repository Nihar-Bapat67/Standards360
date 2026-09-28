"""Read-only access to the A1 catalogue, shared by the online modules.

Every fact the online stages state about a standard comes from here, which is what makes C3, C4
and D1 deterministic: they perform lookups, never inference. The database is opened read-only and
the family index is built once per process, because C3 and D1 are called on every request.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.is_normalizer import NormalizedIS, norm_is_lookup_key, parse_is_number  # noqa: E402

DB = ROOT / "data" / "catalogue.db"
NBSP = re.compile(r"&nbsp;|\s+")


def parse_any_is(text: str) -> Optional[NormalizedIS]:
    """Parse an identifier that may lack the 'IS' prefix.

    BIS's own 'Superseded by IS' field holds values such as '18427 : 2024' and
    '101 (PART 1/SEC 4) : 2024', so the prefix cannot be assumed.
    """
    if not text:
        return None
    s = text.strip()
    if re.match(r"^\(?\s*\d", s):
        s = "IS " + s.lstrip("(").strip()
    return parse_is_number(s)


class Catalogue:
    """One process-wide handle on catalogue.db."""

    _instance = None

    def __init__(self, db_path: Path = DB):
        if not Path(db_path).exists():
            raise SystemExit(f"{db_path} not found. Run `python ingest/collect.py load` first.")
        self.con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self._by_family: Dict[str, List[sqlite3.Row]] = {}
        self._by_base: Dict[str, List[sqlite3.Row]] = {}
        self._by_record: Dict[int, sqlite3.Row] = {}
        self._known_keys = set()
        for row in self.con.execute("SELECT * FROM standards"):
            self._by_record[row["record_id"]] = row
            parsed = parse_any_is(row["is_number"] or "")
            if parsed:
                self._by_family.setdefault(norm_is_lookup_key(parsed.family), []).append(row)
                self._by_base.setdefault(parsed.base_number, []).append(row)
                self._known_keys.add(norm_is_lookup_key(parsed.family))
                self._known_keys.add(norm_is_lookup_key(parsed.canonical))

    @classmethod
    def shared(cls) -> "Catalogue":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------------- lookups

    def family(self, parsed: NormalizedIS) -> List[sqlite3.Row]:
        """Every edition of a standard family, newest first, current editions before withdrawn ones."""
        rows = self._by_family.get(norm_is_lookup_key(parsed.family), [])
        return sorted(rows, key=lambda r: (r["withdrawn"], -(self.year_of(r) or 0)))

    def same_number(self, parsed: NormalizedIS) -> List[sqlite3.Row]:
        """Every record sharing the base number, including other parts.

        A standard is sometimes republished in parts: IS 2062:2011 was withdrawn and the subject now
        appears as IS 2062 (Part 1):2025, which is a different family but the same number.
        """
        rows = self._by_base.get(parsed.base_number, [])
        return sorted(rows, key=lambda r: (r["withdrawn"], (r["is_number"] or "")))

    def record(self, record_id: int) -> Optional[sqlite3.Row]:
        return self._by_record.get(record_id)

    def exists(self, is_number: str) -> bool:
        """True when the number names a real standard, current or withdrawn.

        D1 validates against the whole catalogue, not only the standards whose text we hold.
        """
        parsed = parse_any_is(is_number)
        if not parsed:
            return False
        return (norm_is_lookup_key(parsed.family) in self._known_keys
                or norm_is_lookup_key(parsed.canonical) in self._known_keys)

    @staticmethod
    def year_of(row) -> Optional[int]:
        parsed = parse_any_is(row["is_number"] or "")
        return parsed.year if parsed else None

    def amendments(self, record_id: int) -> List[dict]:
        """Amendments recorded for a standard, cleaned of the portal's HTML entities."""
        out = []
        for (detail,) in self.con.execute("SELECT detail FROM amendments WHERE record_id = ?", (record_id,)):
            try:
                data = json.loads(detail)
            except ValueError:
                continue
            out.append({
                "number": NBSP.sub(" ", data.get("AmendmentNumber", "")).strip(),
                "year": (data.get("AmendmentYear") or "").strip(),
                "file": (data.get("AmdFileName") or "").strip(),
            })
        return sorted(out, key=lambda a: a["year"])

    def labs(self, record_id: int) -> List[dict]:
        """The BIS-recognised laboratories that can test this standard, with contact detail.

        `labs` records which standards a laboratory is recognised for; `lab_directory`, written by
        `ingest/fetch_labs.py`, records where it is and how to reach it. The two join on `lab_key`
        because BIS spells the same laboratory name with varying case and spacing. A laboratory
        missing from the directory is still returned, with its address and contact fields empty,
        so a gap in the directory never hides a recognised laboratory.
        """
        rows = self.con.execute(
            "SELECT DISTINCT l.name, l.city, l.state, d.address, d.phone, d.email, d.city_key "
            "FROM labs l LEFT JOIN lab_directory d ON d.lab_key = l.lab_key "
            "WHERE l.record_id = ? ORDER BY l.state, l.city, l.name", (record_id,))
        return [{"name": r["name"], "city": r["city"], "state": r["state"],
                 "address": r["address"] or None, "phone": r["phone"] or None,
                 "email": r["email"] or None, "city_key": r["city_key"] or None}
                for r in rows]

    def cited_by_record(self, record_id: int) -> List[sqlite3.Row]:
        """Standards this one cites, as catalogue rows (used by C2 later)."""
        return [self._by_record[r["cited_record"]]
                for r in self.con.execute("SELECT cited_record FROM xrefs WHERE citing_record = ?", (record_id,))
                if r["cited_record"] in self._by_record]
