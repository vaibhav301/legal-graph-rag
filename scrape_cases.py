"""
Indian Kanoon Criminal Case Scraper + PDF Compiler
===================================================
Scrapes criminal cases from indiankanoon.org and compiles them into a single PDF
for use with the LegalGraph RAG system.

Usage:
    python scrape_cases.py --query "Section 302 IPC murder" --max-cases 10
    python scrape_cases.py --query "criminal appeal Supreme Court 2023" --max-cases 5
    python scrape_cases.py --section 302 --court supreme --max-cases 15

Requirements:
    pip install requests beautifulsoup4 reportlab lxml
"""

import argparse
import os
import re
import time
import json
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    TableOfContents, Table, TableStyle
)
from reportlab.lib import colors


# ───────────────────────── Configuration ─────────────────────────

BASE_URL = "https://indiankanoon.org"
SEARCH_URL = f"{BASE_URL}/search/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
DELAY_BETWEEN_REQUESTS = 3  # seconds — be respectful to the server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ───────────────────────── Scraper ─────────────────────────

class IndianKanoonScraper:
    """Scrapes case documents from Indian Kanoon."""

    def __init__(self, delay: float = DELAY_BETWEEN_REQUESTS):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay
        self.cases: list[dict] = []

    def search(self, query: str, max_cases: int = 10, page_num: int = 0) -> list[dict]:
        """
        Search Indian Kanoon and return a list of case metadata.
        Each result has: title, url, snippet, court, date.
        """
        results = []
        cases_collected = 0
        current_page = page_num

        while cases_collected < max_cases:
            logger.info(f"Fetching search page {current_page + 1} for: '{query}'")

            params = {
                "formInput": query,
                "pagenum": current_page,
            }

            try:
                resp = self.session.get(SEARCH_URL, params=params, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"Search request failed: {e}")
                break

            soup = BeautifulSoup(resp.text, "lxml")
            result_blocks = soup.select(".result")

            if not result_blocks:
                logger.info("No more results found.")
                break

            for block in result_blocks:
                if cases_collected >= max_cases:
                    break

                # Extract case title and URL
                title_tag = block.select_one(".result_title a")
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                url = f"{BASE_URL}{href}" if href.startswith("/") else href

                # Extract snippet
                snippet_tag = block.select_one(".result_text")
                snippet = snippet_tag.get_text(strip=True)[:300] if snippet_tag else ""

                # Extract court and date from the headline area
                headline = block.select_one(".docsource")
                court = headline.get_text(strip=True) if headline else "Unknown Court"

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "court": court,
                    "doc_id": href.strip("/").split("/")[-1] if href else "",
                })
                cases_collected += 1

            current_page += 1
            time.sleep(self.delay)

        logger.info(f"Found {len(results)} cases.")
        return results

    def fetch_case_text(self, url: str) -> str:
        """Fetch the full text of a case from its URL."""
        logger.info(f"Fetching case: {url}")

        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch case: {e}")
            return ""

        soup = BeautifulSoup(resp.text, "lxml")

        # Indian Kanoon stores the judgment text in div#judgments or div.judgments
        judgment_div = soup.select_one("#judgments") or soup.select_one(".judgments")

        if judgment_div:
            # Remove script/style tags
            for tag in judgment_div.find_all(["script", "style"]):
                tag.decompose()

            # Get clean text, preserving paragraph breaks
            paragraphs = []
            for element in judgment_div.find_all(["p", "pre", "blockquote", "div"]):
                text = element.get_text(strip=True)
                if text and len(text) > 10:
                    paragraphs.append(text)

            if paragraphs:
                return "\n\n".join(paragraphs)

        # Fallback: get all text from the page body
        body = soup.select_one("body")
        if body:
            for tag in body.find_all(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            return body.get_text(separator="\n\n", strip=True)

        return ""

    def collect_cases(self, query: str, max_cases: int = 10) -> list[dict]:
        """Search and fetch full text for all matching cases."""
        search_results = self.search(query, max_cases)

        for case in search_results:
            time.sleep(self.delay)
            full_text = self.fetch_case_text(case["url"])
            case["full_text"] = full_text
            case["char_count"] = len(full_text)
            logger.info(f"  Collected: {case['title'][:60]}... ({case['char_count']} chars)")

        self.cases = [c for c in search_results if c.get("full_text")]
        logger.info(f"Successfully collected {len(self.cases)} cases with full text.")
        return self.cases


# ───────────────────────── PDF Compiler ─────────────────────────

class LegalPDFCompiler:
    """Compiles collected cases into a single structured PDF."""

    def __init__(self, output_path: str = "criminal_cases.pdf"):
        self.output_path = output_path
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Set up custom paragraph styles for the PDF."""
        self.styles.add(ParagraphStyle(
            "CaseTitle",
            parent=self.styles["Heading1"],
            fontSize=16,
            spaceAfter=6,
            textColor=colors.HexColor("#1a1a2e"),
        ))
        self.styles.add(ParagraphStyle(
            "CaseMeta",
            parent=self.styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=12,
            italic=True,
        ))
        self.styles.add(ParagraphStyle(
            "CaseBody",
            parent=self.styles["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ))
        self.styles.add(ParagraphStyle(
            "CaseSeparator",
            parent=self.styles["Normal"],
            fontSize=10,
            alignment=TA_CENTER,
            spaceBefore=20,
            spaceAfter=20,
            textColor=colors.HexColor("#999999"),
        ))
        self.styles.add(ParagraphStyle(
            "CoverTitle",
            parent=self.styles["Title"],
            fontSize=26,
            spaceAfter=20,
            textColor=colors.HexColor("#1a1a2e"),
        ))
        self.styles.add(ParagraphStyle(
            "CoverSubtitle",
            parent=self.styles["Normal"],
            fontSize=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#555555"),
            spaceAfter=8,
        ))

    def _sanitize_text(self, text: str) -> str:
        """Clean text for reportlab (escape XML special chars, etc.)."""
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        # Remove non-printable characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        return text

    def compile(self, cases: list[dict], query: str = "Criminal Cases"):
        """Compile all cases into a single PDF with cover page and TOC."""
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=A4,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.8 * inch,
            rightMargin=0.8 * inch,
        )

        story = []

        # ── Cover Page ──
        story.append(Spacer(1, 2 * inch))
        story.append(Paragraph("Indian Legal Case Compendium", self.styles["CoverTitle"]))
        story.append(Paragraph(f"Search Query: {self._sanitize_text(query)}", self.styles["CoverSubtitle"]))
        story.append(Paragraph(f"Cases Collected: {len(cases)}", self.styles["CoverSubtitle"]))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
            self.styles["CoverSubtitle"],
        ))
        story.append(Paragraph(
            "Source: indiankanoon.org | For use with LegalGraph RAG",
            self.styles["CoverSubtitle"],
        ))
        story.append(PageBreak())

        # ── Table of Contents (Manual) ──
        story.append(Paragraph("Table of Contents", self.styles["Heading1"]))
        story.append(Spacer(1, 12))
        for i, case in enumerate(cases, 1):
            title = self._sanitize_text(case["title"][:80])
            court = self._sanitize_text(case.get("court", ""))
            toc_line = f"{i}. {title}"
            if court:
                toc_line += f" — <i>{court}</i>"
            story.append(Paragraph(toc_line, self.styles["Normal"]))
            story.append(Spacer(1, 4))
        story.append(PageBreak())

        # ── Individual Cases ──
        for i, case in enumerate(cases, 1):
            title = self._sanitize_text(case["title"])
            court = self._sanitize_text(case.get("court", "Unknown Court"))
            url = case.get("url", "")

            # Case header
            story.append(Paragraph(f"Case {i}: {title}", self.styles["CaseTitle"]))
            story.append(Paragraph(f"Court: {court} | Source: {url}", self.styles["CaseMeta"]))
            story.append(Spacer(1, 8))

            # Case body — split into paragraphs
            full_text = case.get("full_text", "No text available.")
            paragraphs = full_text.split("\n\n")

            for para in paragraphs:
                para = para.strip()
                if not para or len(para) < 5:
                    continue
                safe_para = self._sanitize_text(para)
                try:
                    story.append(Paragraph(safe_para, self.styles["CaseBody"]))
                except Exception:
                    # Skip paragraphs that cause encoding issues
                    continue

            # Separator between cases
            if i < len(cases):
                story.append(Paragraph("— — — — — — — — — — —", self.styles["CaseSeparator"]))
                story.append(PageBreak())

        # Build the PDF
        logger.info(f"Building PDF: {self.output_path}")
        doc.build(story)
        file_size = os.path.getsize(self.output_path)
        logger.info(f"PDF created: {self.output_path} ({file_size / 1024:.1f} KB)")

        return self.output_path


# ───────────────────────── Also Save Raw Text ─────────────────────────

def save_raw_text(cases: list[dict], output_path: str = "criminal_cases_raw.txt"):
    """
    Save all cases as a plain text file — this is the fastest way to
    ingest into the LegalGraph RAG system via the paste-text method.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for i, case in enumerate(cases, 1):
            f.write(f"{'='*80}\n")
            f.write(f"CASE {i}: {case['title']}\n")
            f.write(f"COURT: {case.get('court', 'Unknown')}\n")
            f.write(f"SOURCE: {case.get('url', '')}\n")
            f.write(f"{'='*80}\n\n")
            f.write(case.get("full_text", "No text available."))
            f.write(f"\n\n{'─'*80}\n\n")

    logger.info(f"Raw text saved: {output_path}")
    return output_path


def save_json(cases: list[dict], output_path: str = "criminal_cases.json"):
    """Save cases as structured JSON for programmatic use."""
    export = []
    for case in cases:
        export.append({
            "title": case["title"],
            "court": case.get("court", ""),
            "url": case.get("url", ""),
            "full_text": case.get("full_text", ""),
            "char_count": case.get("char_count", 0),
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON saved: {output_path}")
    return output_path


# ───────────────────────── Predefined Searches ─────────────────────────

CRIMINAL_SEARCHES = {
    "murder": "Section 302 IPC murder criminal appeal",
    "dowry_death": "Section 304B IPC dowry death",
    "rape": "Section 376 IPC criminal appeal",
    "theft": "Section 379 380 IPC theft robbery",
    "cheating": "Section 420 IPC cheating fraud",
    "kidnapping": "Section 363 364 IPC kidnapping abduction",
    "attempt_murder": "Section 307 IPC attempt murder",
    "culpable_homicide": "Section 304 IPC culpable homicide not amounting murder",
    "cruelty": "Section 498A IPC cruelty husband relatives",
    "criminal_conspiracy": "Section 120B IPC criminal conspiracy",
    "sedition": "Section 124A IPC sedition",
    "defamation": "Section 499 500 IPC defamation",
    "bns_murder": "Section 101 BNS murder punishment",
    "sc_criminal_2024": "criminal appeal Supreme Court 2024",
    "landmark_criminal": "landmark criminal law Constitution Article 21",
}


# ───────────────────────── CLI ─────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape criminal cases from Indian Kanoon and compile into a single PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_cases.py --query "Section 302 IPC murder" --max-cases 10
  python scrape_cases.py --preset murder --max-cases 15
  python scrape_cases.py --preset dowry_death --max-cases 5 --output dowry_cases.pdf
  python scrape_cases.py --query "criminal appeal 2024 Supreme Court" --max-cases 20

Available presets:
  murder, dowry_death, rape, theft, cheating, kidnapping,
  attempt_murder, culpable_homicide, cruelty, criminal_conspiracy,
  sedition, defamation, bns_murder, sc_criminal_2024, landmark_criminal
        """,
    )
    parser.add_argument("--query", "-q", type=str, help="Custom search query")
    parser.add_argument("--preset", "-p", type=str, choices=list(CRIMINAL_SEARCHES.keys()),
                        help="Use a predefined criminal law search")
    parser.add_argument("--max-cases", "-n", type=int, default=10, help="Max cases to collect (default: 10)")
    parser.add_argument("--output", "-o", type=str, default="criminal_cases.pdf", help="Output PDF filename")
    parser.add_argument("--delay", "-d", type=float, default=3.0, help="Delay between requests in seconds")
    parser.add_argument("--text-only", action="store_true", help="Save as .txt instead of PDF")
    parser.add_argument("--json", action="store_true", help="Also save as JSON")

    args = parser.parse_args()

    # Determine search query
    if args.preset:
        query = CRIMINAL_SEARCHES[args.preset]
        logger.info(f"Using preset '{args.preset}': {query}")
    elif args.query:
        query = args.query
    else:
        parser.error("Either --query or --preset is required.")

    # Scrape
    scraper = IndianKanoonScraper(delay=args.delay)
    cases = scraper.collect_cases(query, max_cases=args.max_cases)

    if not cases:
        logger.error("No cases collected. Check your query or internet connection.")
        return

    # Save outputs
    if args.text_only:
        txt_path = args.output.replace(".pdf", ".txt")
        save_raw_text(cases, txt_path)
        print(f"\n✅ Saved {len(cases)} cases to: {txt_path}")
    else:
        compiler = LegalPDFCompiler(output_path=args.output)
        compiler.compile(cases, query)
        print(f"\n✅ Saved {len(cases)} cases to: {args.output}")

        # Also save raw text for easy RAG ingestion
        txt_path = args.output.replace(".pdf", "_raw.txt")
        save_raw_text(cases, txt_path)
        print(f"📄 Raw text also saved to: {txt_path}")

    if args.json:
        json_path = args.output.replace(".pdf", ".json")
        save_json(cases, json_path)
        print(f"📋 JSON saved to: {json_path}")

    print(f"\n🏛️  Next steps:")
    print(f"   1. Start the LegalGraph RAG server: uvicorn app.main:app --reload")
    print(f"   2. Open the Streamlit UI: streamlit run frontend/streamlit_app.py")
    print(f"   3. Upload the PDF or paste the raw text")
    print(f"   4. Ask questions about the cases!")


if __name__ == "__main__":
    main()
