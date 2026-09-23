"""Table Extraction and Markdown Formatting for Standard Documents.

Detects tables using PyMuPDF table finder, extracts cell contents cleanly,
and renders pipe-delimited Markdown tables to preserve technical requirements.
"""

from typing import List, Tuple, Dict, Any
import fitz


class ExtractedTable:
    def __init__(self, bbox: Tuple[float, float, float, float], markdown: str, raw_rows: List[List[str]]):
        self.bbox = bbox  # (x0, y0, x1, y1)
        self.markdown = markdown
        self.raw_rows = raw_rows


def extract_tables_from_page(page: fitz.Page) -> List[ExtractedTable]:
    """Find tables on a page and render them into structured pipe-delimited Markdown."""
    tables_found: List[ExtractedTable] = []
    
    try:
        tabs = page.find_tables()
        if not tabs or not tabs.tables:
            return []
        
        for tab in tabs.tables:
            bbox = tab.bbox
            rows = tab.extract()
            if not rows or len(rows) < 2:
                continue
            
            # Format as clean markdown table
            header = [str(c or "").strip().replace("\n", " ") for c in rows[0]]
            # If header is completely empty, synthesize col headers
            if not any(header):
                header = [f"Col {idx+1}" for idx in range(len(header))]
            
            md_lines = []
            md_lines.append("| " + " | ".join(header) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            
            for row in rows[1:]:
                row_cells = [str(c or "").strip().replace("\n", " ").replace("|", "\\|") for c in row]
                # Pad or truncate to match header length
                if len(row_cells) < len(header):
                    row_cells.extend([""] * (len(header) - len(row_cells)))
                else:
                    row_cells = row_cells[:len(header)]
                md_lines.append("| " + " | ".join(row_cells) + " |")
            
            md_table = "\n".join(md_lines)
            tables_found.append(ExtractedTable(bbox=bbox, markdown=md_table, raw_rows=rows))
    except Exception:
        # Graceful fallback if table finding fails on atypical page graphics
        pass
    
    return tables_found

