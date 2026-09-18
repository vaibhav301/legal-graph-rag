import os

# --- API Configuration ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "your-api-key-here")
LLM_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

# --- Knowledge Graph Settings ---
ENTITY_TYPES = [
    "STATUTE",        # Laws, acts, sections (e.g., "Section 302 IPC")
    "CASE",           # Case names (e.g., "Kesavananda Bharati v. State of Kerala")
    "COURT",          # Courts (e.g., "Supreme Court of India")
    "PARTY",          # Parties involved (plaintiff, defendant, petitioner)
    "JUDGE",          # Judge names
    "DATE",           # Dates of judgments, filings
    "LEGAL_CONCEPT",  # Legal doctrines, principles (e.g., "due process", "habeas corpus")
    "PENALTY",        # Punishments, fines, sentences
    "JURISDICTION",   # Geographical or subject-matter jurisdiction
]

RELATIONSHIP_TYPES = [
    "CITES",              # Case/statute cites another case/statute
    "OVERRULES",          # Case overrules a previous case
    "AMENDS",             # Statute amends another statute
    "INTERPRETED_BY",     # Statute interpreted by a court/case
    "FILED_IN",           # Case filed in a court
    "DECIDED_BY",         # Case decided by a judge
    "PENALIZES_WITH",     # Statute prescribes a penalty
    "INVOLVES_PARTY",     # Case involves a party
    "RELATES_TO",         # General relationship
    "DECIDED_ON",         # Case decided on a date
    "FALLS_UNDER",        # Entity falls under a jurisdiction or statute
]

# --- Retrieval Settings ---
MAX_RETRIEVAL_HOPS = 3          # Max graph traversal depth
MAX_CONTEXT_NODES = 15          # Max nodes to include in context
RELEVANCE_SCORE_THRESHOLD = 0.3 # Min relevance score for inclusion

# --- Document Processing ---
CHUNK_SIZE = 1500       # Characters per chunk
CHUNK_OVERLAP = 200     # Overlap between chunks

# --- Server ---
API_HOST = "0.0.0.0"
API_PORT = 8000
STREAMLIT_PORT = 8501
