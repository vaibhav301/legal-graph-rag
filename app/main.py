"""
LegalGraph RAG — FastAPI Backend
A vector-less legal document Q&A system powered by Knowledge Graphs + LLM.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import tempfile
import os

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import API_HOST, API_PORT
from app.models import QueryRequest, QueryResponse, DocumentUpload
from app.document_processor import DocumentProcessor
from app.knowledge_graph import LegalKnowledgeGraph
from app.retriever import GraphRetriever
from app.generator import LegalAnswerGenerator


# --- Global State ---
doc_processor = DocumentProcessor()
knowledge_graph = LegalKnowledgeGraph()
retriever = GraphRetriever(knowledge_graph)
generator = LegalAnswerGenerator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    print("🏛️  LegalGraph RAG server starting...")
    print(f"   Graph nodes: {knowledge_graph.graph.number_of_nodes()}")
    print(f"   Graph edges: {knowledge_graph.graph.number_of_edges()}")
    yield
    print("🏛️  LegalGraph RAG server shutting down.")


app = FastAPI(
    title="LegalGraph RAG",
    description="A vector-less legal document Q&A system using Knowledge Graphs",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== DOCUMENT ENDPOINTS ====================

@app.post("/api/documents/upload-text", tags=["Documents"])
async def upload_text_document(doc: DocumentUpload):
    """Upload a legal document as raw text."""
    doc_id = doc_processor.process_text(doc.content, doc.filename)
    chunks = doc_processor.get_chunks(doc_id)

    # Build knowledge graph from chunks
    stats = knowledge_graph.build_from_chunks(chunks)

    return {
        "document_id": doc_id,
        "filename": doc.filename,
        "num_chunks": len(chunks),
        "graph_build_stats": stats,
        "total_graph_stats": knowledge_graph.get_stats(),
    }


@app.post("/api/documents/upload-pdf", tags=["Documents"])
async def upload_pdf_document(file: UploadFile = File(...)):
    """Upload a legal PDF document."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        doc_id = doc_processor.process_pdf(tmp_path)
        chunks = doc_processor.get_chunks(doc_id)
        stats = knowledge_graph.build_from_chunks(chunks)

        return {
            "document_id": doc_id,
            "filename": file.filename,
            "num_chunks": len(chunks),
            "graph_build_stats": stats,
            "total_graph_stats": knowledge_graph.get_stats(),
        }
    finally:
        os.unlink(tmp_path)


@app.get("/api/documents", tags=["Documents"])
async def list_documents():
    """List all ingested documents."""
    docs = doc_processor.get_all_documents()
    return {
        "documents": [
            {
                "id": doc_id,
                "filename": data["filename"],
                "num_chunks": data["num_chunks"],
                "text_preview": data["full_text"][:300] + "...",
            }
            for doc_id, data in docs.items()
        ],
        "total_documents": len(docs),
    }


# ==================== QUERY ENDPOINTS ====================

@app.post("/api/query", tags=["Query"], response_model=QueryResponse)
async def query_legal_knowledge(req: QueryRequest):
    """
    Ask a legal question — the system retrieves context from the knowledge graph
    and generates a grounded answer. No vector database involved!
    """
    if knowledge_graph.graph.number_of_nodes() == 0:
        raise HTTPException(
            status_code=400,
            detail="No documents have been ingested yet. Upload a document first.",
        )

    # Step 1: Retrieve relevant context via graph traversal
    context = retriever.retrieve(
        question=req.question,
        max_hops=req.max_hops,
        max_nodes=req.max_context_nodes,
    )

    # Step 2: Generate answer from context
    result = generator.generate_with_sources(req.question, context)

    return QueryResponse(
        answer=result["answer"],
        retrieved_context=context,
        graph_stats=knowledge_graph.get_stats(),
        sources=[s["entity"] for s in result["sources"]],
    )


# ==================== GRAPH ENDPOINTS ====================

@app.get("/api/graph/stats", tags=["Graph"])
async def get_graph_stats():
    """Get knowledge graph statistics."""
    return knowledge_graph.get_stats()


@app.get("/api/graph/export", tags=["Graph"])
async def export_graph():
    """Export the full knowledge graph for visualization."""
    return knowledge_graph.export_for_visualization()


@app.get("/api/graph/node/{node_id}", tags=["Graph"])
async def get_node(node_id: str):
    """Get details for a specific graph node."""
    info = knowledge_graph.get_node_info(node_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return info


@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "graph_nodes": knowledge_graph.graph.number_of_nodes(),
        "graph_edges": knowledge_graph.graph.number_of_edges(),
        "documents_loaded": len(doc_processor.get_all_documents()),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
