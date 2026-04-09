# ⚖️ LegalGraph RAG — Vector-less Legal Document Q&A

A Retrieval-Augmented Generation (RAG) system for legal documents that replaces traditional vector databases with **Knowledge Graphs**. Built with FastAPI, NetworkX, Streamlit, and Anthropic Claude.

> **No Pinecone. No Chroma. No Weaviate. No embeddings. Just graphs.**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INGESTION PIPELINE                          │
│                                                                     │
│  📄 Legal Doc ──→ 🔪 Chunker ──→ 🤖 LLM Entity Extraction         │
│     (PDF/Text)     (overlap)       (Claude identifies statutes,    │
│                                     cases, courts, judges, etc.)   │
│                                          │                          │
│                                          ▼                          │
│                                   🕸️ Knowledge Graph               │
│                                     (NetworkX DiGraph)             │
│                                   Nodes: Legal entities            │
│                                   Edges: Legal relationships       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         QUERY PIPELINE                              │
│                                                                     │
│  ❓ Question ──→ 🤖 Entity Identification ──→ 🔍 Graph Traversal   │
│                   (LLM extracts what the       (BFS from matched   │
│                    user is asking about)        nodes, N hops)     │
│                                                     │               │
│                                                     ▼               │
│                                          📋 Context Assembly        │
│                                          (Ranked nodes + edges +   │
│                                           source text)             │
│                                                     │               │
│                                                     ▼               │
│                                          🤖 Answer Generation      │
│                                          (Grounded in graph        │
│                                           context only)            │
└─────────────────────────────────────────────────────────────────────┘
```

## 🤔 Why Vector-less RAG?

| Feature | Vector RAG | Graph RAG (This Project) |
|---------|-----------|-------------------------|
| **Retrieval** | Cosine similarity on embeddings | Graph traversal (BFS/DFS) |
| **Explainability** | Opaque — "these chunks were similar" | Transparent — see exact entities & relationships |
| **Relationships** | Lost in embedding space | Explicitly captured as graph edges |
| **Legal Reasoning** | Struggles with multi-hop reasoning | Natural — follow citation chains, statute hierarchies |
| **Infrastructure** | Needs embedding model + vector DB | Just NetworkX (in-memory Python graph) |
| **Domain Fit** | Generic similarity | Legal-specific entity types & relationships |

## 📦 Project Structure

```
legal-graph-rag/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI server with REST endpoints
│   ├── models.py               # Pydantic data models
│   ├── document_processor.py   # PDF/text ingestion & chunking
│   ├── knowledge_graph.py      # LLM-powered KG construction (NetworkX)
│   ├── retriever.py            # Graph-based retrieval (no vectors!)
│   └── generator.py            # LLM answer generation from graph context
├── frontend/
│   └── streamlit_app.py        # Interactive web UI
├── sample_data/
│   └── indian_penal_code_sample.txt
├── config.py                   # All configuration & constants
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/legal-graph-rag.git
cd legal-graph-rag
pip install -r requirements.txt
```

### 2. Set your API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Start the Backend

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Start the Frontend

```bash
streamlit run frontend/streamlit_app.py --server.port 8501
```

### 5. Try It Out

1. Open `http://localhost:8501` in your browser
2. Go to the **Upload Documents** tab
3. Paste the sample legal text from `sample_data/indian_penal_code_sample.txt`
4. Switch to **Ask Questions** and try:
   - *"What is the punishment for murder under Section 302?"*
   - *"What is the rarest of rare doctrine?"*
   - *"How does the BNS replace the IPC?"*

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/upload-text` | Upload legal text |
| `POST` | `/api/documents/upload-pdf` | Upload a PDF file |
| `GET` | `/api/documents` | List all documents |
| `POST` | `/api/query` | Ask a legal question |
| `GET` | `/api/graph/stats` | Get graph statistics |
| `GET` | `/api/graph/export` | Export graph as JSON |
| `GET` | `/api/graph/node/{id}` | Inspect a specific node |
| `GET` | `/api/health` | Health check |

### Example API Usage

```bash
# Upload a document
curl -X POST http://localhost:8000/api/documents/upload-text \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.txt", "content": "Section 302 IPC prescribes death penalty for murder..."}'

# Ask a question
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the punishment for murder?", "max_hops": 2}'
```

## 🧠 How the Knowledge Graph Works

### Entity Extraction
The system uses Claude to extract typed entities from legal text:

- **STATUTE** — Laws, sections, articles (e.g., *Section 302 IPC*)
- **CASE** — Case citations (e.g., *Bachan Singh v. State of Punjab*)
- **COURT** — Courts (e.g., *Supreme Court of India*)
- **JUDGE** — Judge names
- **PARTY** — Parties in cases
- **LEGAL_CONCEPT** — Doctrines, principles (e.g., *rarest of rare*)
- **PENALTY** — Punishments, sentences
- **JURISDICTION** — Geographical/subject jurisdiction
- **DATE** — Dates of decisions, filings

### Relationship Extraction
Relationships are captured as directed edges:

```
Section 302 IPC ──[INTERPRETED_BY]──→ Bachan Singh v. State of Punjab
Bachan Singh     ──[DECIDED_BY]──→ Justice Chandrachud
Bachan Singh     ──[FILED_IN]──→ Supreme Court of India
Section 302 IPC  ──[PENALIZES_WITH]──→ Death Penalty / Life Imprisonment
BNS Section 101  ──[AMENDS]──→ Section 302 IPC
```

### Graph Retrieval (No Vectors!)
When you ask a question:
1. **Entity Identification** — LLM extracts what entities you're asking about
2. **Fuzzy Matching** — Entities are matched to graph nodes via string similarity
3. **BFS Traversal** — The graph is traversed N hops from matched nodes
4. **Ranking** — Nodes are ranked by centrality, proximity, and type importance
5. **Context Assembly** — Top nodes + edges + source text are assembled into context

## ⚙️ Configuration

All settings are in `config.py`:

```python
MAX_RETRIEVAL_HOPS = 3      # How deep to traverse the graph
MAX_CONTEXT_NODES = 15       # Max nodes in retrieval context
CHUNK_SIZE = 1500            # Characters per document chunk
CHUNK_OVERLAP = 200          # Overlap between chunks
```

## 🧪 Testing with Sample Data

A sample Indian Penal Code document is included at `sample_data/indian_penal_code_sample.txt`. It covers Sections 299–304A (homicide offenses) with landmark case law including *Bachan Singh*, *Machhi Singh*, *Nanavati*, and relevant constitutional provisions.

## 📈 Future Enhancements

- [ ] Graph persistence (SQLite / Neo4j backend)
- [ ] PyVis interactive graph visualization in browser
- [ ] Multi-document cross-referencing
- [ ] Temporal reasoning (tracking how laws change over time)
- [ ] Hybrid retrieval (Graph + BM25 keyword search)
- [ ] Support for more legal systems (US, UK, EU)
- [ ] Evaluation benchmarks on legal QA datasets

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend API | FastAPI |
| Knowledge Graph | NetworkX (directed graph) |
| LLM | Anthropic Claude |
| NLP Pipeline | LLM-powered (no spaCy/NLTK dependency) |
| Frontend | Streamlit |
| Document Processing | PyPDF2 + custom chunker |
| Vector Database | **None!** ✅ |

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built as a demonstration that RAG doesn't need vectors — sometimes a graph is all you need.* 🕸️
