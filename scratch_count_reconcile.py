import sys
sys.path.insert(0, "pylib")
import fitz
import re
import json

doc = fitz.open("sp21_2005.pdf")
print("Total pages in SP 21:", len(doc))

# Let's inspect all section contents pages in SP 21 to get the exact count of listed standards
# Section 1 starts around page 14 (1.2)
# Let's search for "SUMMARY OF" and variations
summaries = []
for pno in range(len(doc)):
    text = doc[pno].get_text("text")
    # check for SUMMARY OF
    matches = list(re.finditer(r"SUMMARY\s+OF\s+([^\n]+)", text, re.IGNORECASE))
    for m in matches:
        summaries.append((pno + 1, m.group(0).strip()))

print(f"Total 'SUMMARY OF' occurrences across all pages: {len(summaries)}")

# Also let's check for any standard titles that might not say "SUMMARY OF" or have a linebreak
banners_any = []
for pno in range(len(doc)):
    text = doc[pno].get_text("text")
    if "SUMMARY" in text.upper():
        m = re.search(r"SUMMARY\s+(?:OF\s+)?([^\n]+)", text, re.IGNORECASE)
        if m and "CONTENTS" not in m.group(1).upper() and "BUILDING" not in m.group(1).upper():
            pass
            
# Let's check the current segmenter's detected banners vs all raw SUMMARY OF
from ingest.parsing.segmenter import segment_compilation_pdf
segs, quars = segment_compilation_pdf("sp21_2005.pdf", "catalogue/catalogue.db")
print(f"Segmenter output: {len(segs)} valid segments, {len(quars)} quarantined, total = {len(segs) + len(quars)}")

