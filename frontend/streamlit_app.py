"""
LegalGraph RAG — Streamlit Frontend
Interactive UI for uploading legal documents, visualizing the knowledge graph, and asking questions.
"""

import streamlit as st
import requests
import json
import time

# --- Configuration ---
API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="LegalGraph RAG",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.3rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.2rem;
        border-radius: 10px;
        text-align: center;
    }
    .metric-card h3 { margin: 0; font-size: 2rem; }
    .metric-card p { margin: 0; font-size: 0.85rem; opacity: 0.9; }
    .source-box {
        background-color: #f0f2f6;
        border-left: 4px solid #667eea;
        padding: 0.8rem 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
        font-size: 0.9rem;
    }
    .answer-box {
        background-color: #f8f9fc;
        border: 1px solid #e0e0e0;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        line-height: 1.7;
    }
    .graph-stat {
        display: inline-block;
        background: #eef2ff;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        margin: 0.2rem;
        font-size: 0.85rem;
        color: #4338ca;
    }
</style>
""", unsafe_allow_html=True)


def api_call(method: str, endpoint: str, **kwargs) -> dict | None:
    """Make an API call to the FastAPI backend."""
    try:
        url = f"{API_BASE}{endpoint}"
        resp = getattr(requests, method)(url, timeout=120, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to the API server. Make sure it's running: `uvicorn app.main:app --reload`")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ API Error: {e.response.text}")
        return None


# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("## ⚖️ LegalGraph RAG")
    st.markdown("*Vector-less Legal Q&A*")
    st.divider()

    # Health check
    health = api_call("get", "/api/health")
    if health:
        st.success("🟢 API Connected")
        col1, col2 = st.columns(2)
        col1.metric("📄 Docs", health["documents_loaded"])
        col2.metric("🔗 Nodes", health["graph_nodes"])
    else:
        st.error("🔴 API Offline")

    st.divider()
    st.markdown("### How it works")
    st.markdown("""
    1. **Upload** legal documents (PDF/text)
    2. **Extract** entities & relationships via LLM
    3. **Build** a knowledge graph (no vectors!)
    4. **Query** using graph traversal + LLM generation
    """)

    st.divider()
    st.markdown("### Settings")
    max_hops = st.slider("Graph traversal depth", 1, 5, 2)
    max_context = st.slider("Max context nodes", 5, 50, 15)


# ==================== MAIN CONTENT ====================
st.markdown('<div class="main-header">⚖️ LegalGraph RAG</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">A vector-less legal document Q&A system powered by Knowledge Graphs + LLM</div>',
    unsafe_allow_html=True,
)

tab_upload, tab_query, tab_graph, tab_about = st.tabs(
    ["📄 Upload Documents", "❓ Ask Questions", "🕸️ Knowledge Graph", "ℹ️ About"]
)

# ==================== TAB: UPLOAD ====================
with tab_upload:
    st.markdown("### Upload Legal Documents")
    st.markdown("Upload legal texts to build the knowledge graph. Supports **PDF** and **raw text**.")

    upload_method = st.radio("Input method:", ["📝 Paste Text", "📎 Upload PDF"], horizontal=True)

    if upload_method == "📝 Paste Text":
        col_input, col_meta = st.columns([3, 1])
        with col_meta:
            filename = st.text_input("Document name", value="legal_document.txt")
        with col_input:
            text_input = st.text_area(
                "Paste your legal document here:",
                height=300,
                placeholder="Paste the text of a legal document, statute, case law, contract, etc...",
            )

        if st.button("🚀 Process Document", type="primary", disabled=not text_input):
            with st.spinner("Processing document & building knowledge graph..."):
                result = api_call("post", "/api/documents/upload-text", json={
                    "filename": filename,
                    "content": text_input,
                })

            if result:
                st.success(f"✅ Document processed: **{result['filename']}**")
                st.markdown("#### Extraction Results")
                stats = result["graph_build_stats"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Chunks", stats["chunks_processed"])
                c2.metric("Entities", stats["entities_extracted"])
                c3.metric("Relations", stats["relationships_extracted"])
                c4.metric("Graph Nodes", stats["unique_nodes"])

    else:
        uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
        if uploaded_file and st.button("🚀 Process PDF", type="primary"):
            with st.spinner("Extracting text & building knowledge graph..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                result = api_call("post", "/api/documents/upload-pdf", files=files)

            if result:
                st.success(f"✅ PDF processed: **{result['filename']}**")
                stats = result["graph_build_stats"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Chunks", stats["chunks_processed"])
                c2.metric("Entities", stats["entities_extracted"])
                c3.metric("Relations", stats["relationships_extracted"])
                c4.metric("Graph Nodes", stats["unique_nodes"])


# ==================== TAB: QUERY ====================
with tab_query:
    st.markdown("### Ask a Legal Question")
    st.markdown("The system traverses the knowledge graph to find relevant context, then generates a grounded answer.")

    question = st.text_input(
        "Your question:",
        placeholder="e.g., What are the penalties under Section 302 of the IPC?",
    )

    example_questions = [
        "What statutes are referenced in the document?",
        "Which courts have jurisdiction over this matter?",
        "What are the key legal concepts discussed?",
        "How are the parties related to the cases mentioned?",
        "What penalties are prescribed in the uploaded document?",
    ]

    st.markdown("**Example questions:**")
    cols = st.columns(3)
    for i, eq in enumerate(example_questions[:3]):
        if cols[i].button(eq, key=f"eq_{i}", use_container_width=True):
            question = eq

    if question:
        with st.spinner("🔍 Searching knowledge graph & generating answer..."):
            start = time.time()
            result = api_call("post", "/api/query", json={
                "question": question,
                "max_hops": max_hops,
                "max_context_nodes": max_context,
            })
            elapsed = time.time() - start

        if result:
            st.markdown(f"*Answered in {elapsed:.1f}s*")

            # Answer
            st.markdown("#### 📋 Answer")
            st.markdown(f'<div class="answer-box">{result["answer"]}</div>', unsafe_allow_html=True)

            # Sources
            if result.get("sources"):
                st.markdown("#### 📚 Sources Referenced")
                for source in result["sources"]:
                    st.markdown(f'<div class="source-box">📌 {source}</div>', unsafe_allow_html=True)

            # Retrieved Context Details
            with st.expander("🔍 Retrieved Graph Context (Debug)"):
                ctx = result["retrieved_context"]
                st.markdown(f"**Nodes retrieved:** {len(ctx['relevant_nodes'])}")
                st.markdown(f"**Edges retrieved:** {len(ctx['relevant_edges'])}")

                if ctx["relevant_nodes"]:
                    st.markdown("**Top Entities:**")
                    for node in ctx["relevant_nodes"][:10]:
                        score = node.get("relevance_score", "N/A")
                        st.markdown(
                            f'<span class="graph-stat">[{node["type"]}] {node["name"]} (score: {score})</span>',
                            unsafe_allow_html=True,
                        )

                if ctx["relevant_edges"]:
                    st.markdown("**Relationships:**")
                    for edge in ctx["relevant_edges"][:10]:
                        st.text(f"  {edge['source']} --[{edge['relation']}]--> {edge['target']}")


# ==================== TAB: KNOWLEDGE GRAPH ====================
with tab_graph:
    st.markdown("### Knowledge Graph Explorer")

    stats = api_call("get", "/api/graph/stats")
    if stats and stats.get("nodes", 0) > 0:
        # Stats overview
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔵 Nodes", stats["nodes"])
        c2.metric("🔗 Edges", stats["edges"])
        c3.metric("🧩 Components", stats["connected_components"])
        c4.metric("🔄 Connected", "Yes" if stats["is_connected"] else "No")

        # Entity type breakdown
        st.markdown("#### Entity Types")
        if stats.get("entity_types"):
            for etype, count in sorted(stats["entity_types"].items(), key=lambda x: x[1], reverse=True):
                st.progress(count / max(stats["entity_types"].values()), text=f"{etype}: {count}")

        # Most connected entities
        if stats.get("most_connected"):
            st.markdown("#### Most Connected Entities (Legal Hubs)")
            for mc in stats["most_connected"]:
                st.markdown(f'<span class="graph-stat">🏛️ {mc["name"]} (centrality: {mc["centrality"]})</span>',
                            unsafe_allow_html=True)

        # Graph data export
        st.markdown("#### Graph Data")
        graph_data = api_call("get", "/api/graph/export")
        if graph_data:
            st.json(graph_data, expanded=False)

    else:
        st.info("📭 No knowledge graph data yet. Upload a document in the **Upload Documents** tab to get started.")


# ==================== TAB: ABOUT ====================
with tab_about:
    st.markdown("### About LegalGraph RAG")
    st.markdown("""
    **LegalGraph RAG** is a Retrieval-Augmented Generation (RAG) system for legal documents that uses 
    **knowledge graphs instead of vector databases** for retrieval.

    #### Architecture
    ```
    📄 Document → 🔪 Chunking → 🤖 LLM Entity Extraction → 🕸️ Knowledge Graph (NetworkX)
                                                                     ↓
    ❓ Question → 🤖 Entity Identification → 🔍 Graph Traversal → 📋 Context Assembly → 🤖 Answer Generation
    ```

    #### Why Vector-less?
    - **No embedding model needed** — saves compute and avoids embedding quality issues
    - **Explainable retrieval** — you can see exactly which entities and relationships were used
    - **Structured knowledge** — captures relationships between legal concepts, not just similarity
    - **Better for legal domain** — legal reasoning follows graph-like structures (precedent chains, statute hierarchies)

    #### Tech Stack
    - **Backend:** FastAPI + Python
    - **Knowledge Graph:** NetworkX (directed graph)
    - **NLP/LLM:** Anthropic Claude (entity extraction + answer generation)
    - **Frontend:** Streamlit
    - **No Vector DB** — no Pinecone, no Chroma, no Weaviate!

    #### Key Components
    | Module | Purpose |
    |--------|---------|
    | `document_processor.py` | Text extraction, cleaning, chunking |
    | `knowledge_graph.py` | LLM-powered entity/relationship extraction, graph management |
    | `retriever.py` | Graph-based retrieval via entity matching + BFS traversal |
    | `generator.py` | LLM-powered answer generation from graph context |
    | `main.py` | FastAPI server with REST endpoints |
    | `streamlit_app.py` | Interactive web UI |
    """)
