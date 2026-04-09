"""
Document Processor Module
Handles document ingestion, text extraction, and chunking for the legal RAG system.
"""

import re
import hashlib
from pathlib import Path
from typing import Optional

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import CHUNK_SIZE, CHUNK_OVERLAP


class DocumentProcessor:
    """Processes legal documents into chunks for knowledge graph extraction."""

    def __init__(self, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.documents: dict[str, dict] = {}  # doc_id -> {filename, full_text, chunks}

    def process_text(self, text: str, filename: str = "manual_input.txt") -> str:
        """Process raw text input and return a document ID."""
        doc_id = hashlib.md5(f"{filename}:{text[:200]}".encode()).hexdigest()[:12]
        cleaned = self._clean_legal_text(text)
        chunks = self._create_chunks(cleaned)

        self.documents[doc_id] = {
            "filename": filename,
            "full_text": cleaned,
            "chunks": chunks,
            "num_chunks": len(chunks),
        }
        return doc_id

    def process_pdf(self, pdf_path: str) -> str:
        """Extract text from a PDF file and process it."""
        if PdfReader is None:
            raise ImportError("PyPDF2 is required for PDF processing. Install it with: pip install PyPDF2")

        reader = PdfReader(pdf_path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)
        filename = Path(pdf_path).name
        return self.process_text(full_text, filename)

    def get_chunks(self, doc_id: str) -> list[dict]:
        """Return chunks for a given document."""
        if doc_id not in self.documents:
            raise ValueError(f"Document {doc_id} not found")
        return self.documents[doc_id]["chunks"]

    def get_document(self, doc_id: str) -> dict:
        """Return full document metadata."""
        if doc_id not in self.documents:
            raise ValueError(f"Document {doc_id} not found")
        return self.documents[doc_id]

    def get_all_documents(self) -> dict[str, dict]:
        """Return all stored documents."""
        return self.documents

    # --- Private Methods ---

    def _clean_legal_text(self, text: str) -> str:
        """Clean and normalize legal text."""
        # Normalize whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        # Remove page numbers / headers that are just numbers
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        # Normalize legal section references
        text = re.sub(r'[Ss]ection\s+', 'Section ', text)
        text = re.sub(r'[Aa]rticle\s+', 'Article ', text)
        return text.strip()

    def _create_chunks(self, text: str) -> list[dict]:
        """
        Split text into overlapping chunks, trying to break at paragraph
        or sentence boundaries for better context preservation.
        """
        chunks = []
        # Split by paragraphs first
        paragraphs = re.split(r'\n\n+', text)

        current_chunk = ""
        chunk_idx = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph exceeds chunk size, save current and start new
            if len(current_chunk) + len(para) + 2 > self.chunk_size and current_chunk:
                chunks.append({
                    "chunk_id": f"chunk_{chunk_idx}",
                    "text": current_chunk.strip(),
                    "char_start": max(0, len(text) - len(current_chunk) - 100),
                    "index": chunk_idx,
                })
                chunk_idx += 1

                # Keep overlap from end of current chunk
                overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else current_chunk
                current_chunk = overlap_text + "\n\n" + para
            else:
                current_chunk = current_chunk + "\n\n" + para if current_chunk else para

        # Don't forget the last chunk
        if current_chunk.strip():
            chunks.append({
                "chunk_id": f"chunk_{chunk_idx}",
                "text": current_chunk.strip(),
                "index": chunk_idx,
            })

        return chunks
