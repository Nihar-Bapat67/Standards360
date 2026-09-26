"""End-to-end walkthrough: one request through every module, printed stage by stage.

This is the demo driver and the quickest way to see the whole system work. It runs the same
`Pipeline` the API uses, so what it prints is what a procurement portal would receive.

    python demo/walkthrough.py --text "500 MT of 43 grade OPC for RCC work as per IS 8112:1989"
    python demo/walkthrough.py --file data/out/tender_sample.pdf --pdf
    python demo/walkthrough.py --scenario cement          one of the rehearsed scenarios
    python demo/walkthrough.py --scenario tubes --answers type="electric resistance welded"

Nothing is written unless --pdf is given, and then only into data/out/.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.deliver.document import DocumentGenerator  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402

SCENARIOS = {
    "cement": ("Supply of 500 MT ordinary Portland cement, 43 grade, for RCC structural work of the "
               "proposed office building, as per IS 8112:1989 and IS 456:2000"),
    "tubes": ("Supply of 200 MT structural steel tubes YSt 240, 50 NB medium class, for pipe truss "
              "of industrial shed, as per IS 1161:1998 and IS 2062:2011"),
    "thin": "steel tubes",
    "hindi": ("आपूर्ति — 500 मीट्रिक टन 43 ग्रेड साधारण पोर्टलैंड सीमेंट, RCC कार्य हेतु, "
              "IS 8112:1989 के अनुसार"),
    "wire": "Mild steel wire, 4 mm diameter, annealed, for general engineering fabrication and binding",
}
RULE = "─" * 78


def heading(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="tender text, a specification, or a product name")
    source.add_argument("--file", help="a tender PDF, DOCX or screenshot")
    source.add_argument("--scenario", choices=sorted(SCENARIOS), help="a rehearsed example")
    parser.add_argument("--persona", default="procurement", choices=["procurement", "manufacturer"])
    parser.add_argument("--state", default=None, help="used to list the nearest laboratories")
    parser.add_argument("--depth", default="B", choices=["A", "B", "C"], help="citation depth")
    parser.add_argument("--answers", nargs="*", default=[], metavar="field=value",
                        help="replies to the clarifying questions, closing B5's loop")
    parser.add_argument("--pdf", action="store_true", help="also write the document to data/out/")
    args = parser.parse_args()

    answers = dict(pair.split("=", 1) for pair in args.answers if "=" in pair)
    text = args.text or (SCENARIOS[args.scenario] if args.scenario else None)

    print("Loading the models. This takes about a minute on a laptop and happens once.", flush=True)
    started = time.time()
    pipeline = Pipeline.shared()
    print(f"Ready in {time.time() - started:.0f} s.")

    heading("INPUT")
    print(text or f"file: {args.file}")
    if answers:
        print(f"answers supplied: {answers}")

    result = pipeline.analyze(text=text, file_path=args.file, persona=args.persona,
                              state=args.state, answers=answers or None)
    requirement, recommendation = result.requirement, result.recommendation

    heading("B1 · what was read")
    print(f"source {result.payload.source}, {result.payload.pages} pages, "
          f"richness {result.payload.richness}")
    for note in result.payload.notes:
        print(f"  note: {note}")

    heading("B3 · the requirement, extracted")
    print(f"product    {requirement.product}")
    print(f"category   {requirement.category}")
    print(f"attributes {requirement.attributes}")
    print(f"cited      {requirement.cited_standards or 'none'}")
    print(f"missing    {requirement.not_specified or 'nothing required is missing'}")
    print(f"extracted by {requirement.extracted_by}")

    heading("C1 · retrieval")
    print(f"query: {result.query}")
    if not recommendation.primary:
        print("no standard matched closely enough to recommend one")
    else:
        print(f"primary: {recommendation.primary_as_cited or recommendation.primary} — "
              f"{recommendation.primary_title}")
        if recommendation.amendments:
            listed = "; ".join(f"{a.get('number','').strip()} ({a.get('year','')})"
                               for a in recommendation.amendments)
            print(f"amendments in force: {listed}")
            print(f"  (an amendment modifies {recommendation.primary} without replacing it, so the "
                  f"edition year does not change; cite it as amended)")
        if recommendation.evidence:
            evidence = recommendation.evidence
            where = ("BIS one-page summary" if evidence.role == "summary"
                     else f"clause {evidence.clause} ({evidence.role}), page {evidence.page_start}")
            print(f"evidence: {where}")
            print(f"  “{' '.join(evidence.quote.split())[:160]}…”")
        else:
            print("evidence: matched on the catalogue entry; no clause text is held for it")

    heading("C2 · allied standards, by the role each plays")
    for relation, items in recommendation.allied.items():
        print(f"  {relation:<20} {', '.join(a.is_number for a in items[:6])}")
    if not recommendation.allied:
        print("  none")

    heading("B4 · the standards the tender already cited")
    for verdict in recommendation.verdicts:
        arrow = f" -> {verdict.replacement}" if verdict.replacement else ""
        print(f"  {verdict.citation:<22} {verdict.verdict.upper():<8}{arrow}")
        print(f"      {verdict.reason}")
    if not recommendation.verdicts:
        print("  the tender cited no standards")

    heading("C3 · version and amendment warnings")
    for warning in recommendation.warnings[:6]:
        print(f"  [{warning.severity.value}] {warning.message}")
    if not recommendation.warnings:
        print("  none")

    heading("C4 · certification")
    if recommendation.certification:
        print(f"  {recommendation.certification.statement}")
        for lab in recommendation.certification.nearest_labs[:3]:
            print(f"    lab: {lab.name} ({lab.city}, {lab.state})")
    else:
        print("  not checked, because no standard was recommended")

    heading("C5 and B5 · confidence, and whether to ask")
    print(f"  confidence {recommendation.confidence} ({recommendation.band})")
    for driver in result.sufficiency.drivers:
        print(f"    because {driver}")
    if result.needs_more_info:
        print("  the system is asking rather than guessing:")
        for question in result.sufficiency.questions:
            print(f"    [{question['field']}] {question['ask']}")
        print("  re-run with --answers field=value to close the loop")

    heading("D2 · one answer, three citation depths")
    for option in recommendation.options:
        mark = " (default)" if option.default else ""
        print(f"  {option.id} {option.label}{mark}: {len(option.standards)} standards")
        print(f"      {', '.join(option.standards)}")

    heading("D1 and D2 · the paragraph, after the validity guard")
    print(f"  {recommendation.explanation}")
    print(f"  removed by the guard: {recommendation.removed_by_guard or 'nothing'}")

    if args.pdf and recommendation.primary:
        target = ROOT / "data" / "out" / f"walkthrough_{args.scenario or 'custom'}.pdf"
        DocumentGenerator().generate(result, str(target), option_id=args.depth,
                                     mode="annexure" if args.file else "report",
                                     original_pdf=args.file, persona=args.persona)
        heading("D3 · the document")
        print(f"  written to {target}")

    heading(f"TOTAL {result.seconds} s")


if __name__ == "__main__":
    main()
