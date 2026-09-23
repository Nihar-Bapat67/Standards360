"""Module B3: Requirement Extractor.

Pulls the structured facts out of a tender's text and, just as importantly, records what the tender
failed to specify and which standards it already cites.

Two layers, in this order:

1. **Rules.** Citations, quantities, grades, diameters, pressure classes and the product category are
   found by regular expression and by matching against the BIS product categories in the catalogue.
   This layer always runs, works offline, and is what the system falls back to.
2. **The model.** When a key is configured, one call with a strict JSON schema fills the product name
   and any attribute the rules missed. It never supplies a standard number: citations come from the
   rules, so a model cannot invent one here.

The `not_specified` list comes from `config/required_fields.yaml`, which is also what B5 turns into
questions.

    from app.understand.extractor import RequirementExtractor
    RequirementExtractor().extract("Supply of 500 MT of 43 grade OPC for RCC work as per IS 8112")
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.catalogue import Catalogue  # noqa: E402
from app.llm import LLM  # noqa: E402
from contracts.requirement import InputPayload, RequirementObject  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
FIELD_TABLE = ROOT / "config" / "required_fields.yaml"

CITATION = re.compile(r"\bIS\s*[:\s\-]?\s*(\d{2,5})(\s*\(\s*(?:Part|Sec|Section)[^)]*\))?(?:\s*[:\-]\s*(\d{4}))?",
                      re.IGNORECASE)
PATTERNS = {
    "quantity": re.compile(r"\b(\d[\d,.]*)\s*(MT|metric\s+tonnes?|tonnes?|tons?|kg|nos\.?|numbers?|metres?|m|litres?|sqm|cum)\b", re.I),
    "grade": re.compile(r"\b((?:Fe|M|FG|YSt|E)\s?\d{3}[A-Z]?|\d{2,3}\s*grade|grade\s*\d{2,3}|OPC\s*\d{2}|class\s*[A-Z]?\d+)\b", re.I),
    "diameter": re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:mm|millimetres?)\s*(?:dia|diameter|nominal\s+bore|NB|OD)\b", re.I),
    "thickness": re.compile(r"\b(\d+(?:\.\d+)?)\s*mm\s*(?:thick|thickness)\b", re.I),
    "pressure_class": re.compile(r"\b(PN\s*\d+|class\s*K\d+|SDR\s*\d+|\d+\s*kgf/cm2|\d+\s*kg/cm2)\b", re.I),
    "size": re.compile(r"\b(\d+\s*[x×]\s*\d+(?:\s*[x×]\s*\d+)?)\s*mm\b", re.I),
    # Product type words that decide between standards for the same material, so that B5 does not
    # ask about something the text already said ("galvanized mild steel tubes").
    "type": re.compile(r"\b(seamless|electric\s+resistance\s+welded|ERW|HFIW|HFS|galvani[sz]ed|"
                       r"hot\s+finished|hot\s+rolled|cold\s+rolled|cold\s+drawn|welded|autoclaved|"
                       r"centrifugally\s+cast|spun|corrugated|deformed|annealed)\b", re.I),
}
APPLICATION = re.compile(
    r"\bfor\s+((?:[a-z0-9,\- ]{3,60}?))(?=\s*(?:,|\.|;|$|as\s+per|conforming|in\s+accordance))", re.I)

# Product words to a category key in config/required_fields.yaml.
CATEGORY_WORDS = [
    ("cement", ("cement", "opc", "ppc", "portland")),
    ("aggregate", ("aggregate", "coarse sand", "fine aggregate", "stone chips")),
    ("reinforcement_steel", ("reinforcement", "tmt", "deformed bar", "rebar", "reinforcing")),
    ("steel_tubes", ("tube", "tubular", "hollow section", "pipe truss")),
    ("pipes_iron", ("ductile iron pipe", "cast iron pipe", "di pipe", "steel pipe", "sewage pipe")),
    ("pipes_plastic", ("hdpe", "upvc", "pvc-u", "cpvc", "ppr", "polyethylene pipe", "plastic pipe")),
    ("steel_sheet", ("sheet", "strip", "coil", "plate")),
    ("steel_wire", ("wire", "wire rod")),
    ("structural_steel", ("structural steel", "girder", "angle", "channel", "beam")),
    ("plywood", ("plywood", "block board", "flush door", "particle board", "mdf")),
    ("concrete_products", ("paving block", "concrete block", "aac", "tile", "manhole", "precast")),
    ("aluminium", ("aluminium", "aluminum")),
    ("castings", ("casting", "grey iron", "cast iron")),
    ("welding_consumables", ("electrode", "welding rod", "filler wire")),
]

SYSTEM_PROMPT = (
    "You extract procurement facts from Indian tender text. Reply with one JSON object and nothing "
    "else. Keys: product (short noun phrase, no brand names), category (one word), attributes "
    "(object of simple string values such as grade, application, diameter, thickness, material). "
    "Never include standard numbers, prices, vendors or dates. If a fact is absent, omit the key."
)


class RequirementExtractor:
    def __init__(self, catalogue: Optional[Catalogue] = None, llm: Optional[LLM] = None,
                 use_llm: bool = True):
        """`use_llm=False` forces the offline rules path, which is what runs for a confidential
        document, without a key, or without a network."""
        self.cat = catalogue or Catalogue.shared()
        self.llm = llm or (LLM() if use_llm else None)
        self.fields = self._load_fields()
        self._category_products = self._catalogue_products()

    # ---------------------------------------------------------------- public

    def extract(self, text_or_payload, language: str = "en") -> RequirementObject:
        payload = (text_or_payload if isinstance(text_or_payload, InputPayload)
                   else InputPayload(source="text", text=str(text_or_payload), richness="spec_only"))
        text = payload.text or ""

        attributes = self._attributes(text)
        cited = self._citations(text)
        product = self._product_from_rules(text)
        category = self._category(product or text)
        used = "rules"

        if self.llm and self.llm.available:
            improved = self._ask_model(text)
            if improved:
                used = "llm+rules"
                product = improved.get("product") or product
                for key, value in (improved.get("attributes") or {}).items():
                    key = re.sub(r"\W+", "_", key.strip().lower())
                    if value and key not in attributes and key not in ("quantity", "price"):
                        attributes[key] = str(value)[:80]
                category = self._category(f"{product} {improved.get('category', '')}") or category

        required = self.fields.get(category, {}).get("required", [])
        missing = [field for field in required if field not in attributes]

        return RequirementObject(
            product=(product or "").strip()[:120],
            category=category,
            attributes=attributes,
            cited_standards=cited,
            not_specified=missing,
            language=language,
            source=payload.source,
            richness=payload.richness,
            extracted_by=used,
        )

    def questions_for(self, requirement: RequirementObject) -> List[Dict[str, str]]:
        """The question text for each missing field, used by B5."""
        asks = self.fields.get(requirement.category, {}).get("ask", {})
        return [{"field": field, "ask": asks.get(field, f"Please specify the {field.replace('_', ' ')}.")}
                for field in requirement.not_specified]

    # ---------------------------------------------------------------- rules

    @staticmethod
    def _citations(text: str) -> List[str]:
        """Standard numbers the tender already names, normalised and deduplicated in order."""
        out, seen = [], set()
        for match in CITATION.finditer(text or ""):
            number, part, year = match.group(1), (match.group(2) or "").strip(), match.group(3)
            citation = f"IS {number}"
            if part:
                citation += " " + re.sub(r"\s+", " ", part)
            if year:
                citation += f":{year}"
            key = citation.replace(" ", "").upper()
            if key not in seen:
                seen.add(key)
                out.append(citation)
        return out

    @staticmethod
    def _attributes(text: str) -> Dict[str, str]:
        attributes: Dict[str, str] = {}
        for name, pattern in PATTERNS.items():
            match = pattern.search(text or "")
            if match:
                attributes[name] = re.sub(r"\s+", " ", match.group(0)).strip()
        application = APPLICATION.search(text or "")
        if application:
            value = application.group(1).strip(" ,.")
            if len(value.split()) <= 8:
                attributes["application"] = value
        return attributes

    def _product_from_rules(self, text: str) -> str:
        """Match the text against the product names on BIS's own category pages.

        These are 777 real product descriptions, so the match is against BIS vocabulary rather than
        a hand-written list.
        """
        lowered = (text or "").lower()
        best, best_len = "", 0
        for product in self._category_products:
            if len(product) > best_len and product in lowered:
                best, best_len = product, len(product)
        return best.title() if best else self._first_noun_phrase(text)

    @staticmethod
    def _first_noun_phrase(text: str) -> str:
        """Fallback: the opening words of the description, minus the procurement boilerplate."""
        cleaned = re.sub(r"^(supply|procurement|providing|provision|purchase)\s+(and\s+\w+\s+)?(of\s+)?", "",
                         (text or "").strip(), flags=re.I)
        cleaned = re.sub(r"^\d[\d,.]*\s*\w+\s+(of\s+)?", "", cleaned)
        return " ".join(cleaned.split()[:6])

    def _category(self, text: str) -> str:
        lowered = (text or "").lower()
        for category, words in CATEGORY_WORDS:
            if any(word in lowered for word in words):
                return category
        return ""

    # ---------------------------------------------------------------- model

    def _ask_model(self, text: str) -> Optional[dict]:
        excerpt = (text or "")[:4000]
        result = self.llm.complete_json(SYSTEM_PROMPT, excerpt, max_tokens=500)
        if not isinstance(result, dict):
            return None
        return result

    # ---------------------------------------------------------------- loading

    @staticmethod
    def _load_fields() -> dict:
        """Read the required-field table. Parsed without PyYAML: the file is a fixed small shape."""
        if not FIELD_TABLE.exists():
            return {}
        table, category, section = {}, None, None
        for raw in FIELD_TABLE.read_text(encoding="utf-8").splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip())
            line = raw.strip()
            if indent == 0 and line.endswith(":"):
                category = line[:-1].strip()
                table[category] = {"required": [], "ask": {}}
                section = None
            elif indent == 2 and line.startswith("required:"):
                values = line.split(":", 1)[1].strip().strip("[]")
                table[category]["required"] = [v.strip() for v in values.split(",") if v.strip()]
                section = "required"
            elif indent == 2 and line.startswith("ask:"):
                section = "ask"
            elif indent >= 4 and section == "ask" and ":" in line:
                field, _, question = line.partition(":")
                table[category]["ask"][field.strip()] = question.strip().strip('"')
        return table

    def _catalogue_products(self) -> List[str]:
        """Product descriptions from the BIS category pages, longest first."""
        rows = self.cat.con.execute("SELECT DISTINCT product FROM categories WHERE product <> ''").fetchall()
        products = sorted({(r[0] or "").strip().lower() for r in rows if len(r[0] or "") > 4},
                          key=len, reverse=True)
        return products
