"""
Knowledge Graph Module
Builds and manages a legal knowledge graph using NetworkX.
Uses Groq LLM for entity and relationship extraction from legal text.
"""

import json
import re
import networkx as nx
from typing import Optional
from groq import Groq

import sys
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import ENTITY_TYPES, RELATIONSHIP_TYPES
from app.models import Entity, Relationship, GraphExtractionResult

# ──────────────────────────────────────────────
# Groq Configuration
# ──────────────────────────────────────────────

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = "llama-3.3-70b-versatile"  # alternatives: "llama3-8b-8192", "mixtral-8x7b-32768"


class LegalKnowledgeGraph:
    """
    A knowledge graph specifically designed for legal documents.
    Uses LLM-powered extraction to build a graph of legal entities and relationships.
    """

    def __init__(self, api_key: str = GROQ_API_KEY):
        self.graph = nx.DiGraph()

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Add it to your .env file as:\n"
                "GROQ_API_KEY=gsk_your_key_here"
            )

        print(f"KEY LOADED: '{api_key[:20]}...' | length={len(api_key)}")
        self.client = Groq(api_key=api_key)
        self.chunk_map: dict[str, str] = {}  # entity_id -> source_chunk_text

    def extract_from_chunk(self, chunk_text: str, chunk_id: str) -> GraphExtractionResult:
        """
        Use the LLM to extract legal entities and relationships from a text chunk.
        This is the core NLP step — no vector embeddings involved.
        """
        extraction_prompt = f"""You are a legal NLP system. Extract ALL entities and relationships from this legal text.

ENTITY TYPES: {json.dumps(ENTITY_TYPES)}
RELATIONSHIP TYPES: {json.dumps(RELATIONSHIP_TYPES)}

TEXT:
\"\"\"
{chunk_text}
\"\"\"

Respond ONLY with valid JSON (no markdown fences, no preamble):
{{
  "entities": [
    {{
      "id": "<unique_snake_case_id>",
      "name": "<display name>",
      "entity_type": "<one of the entity types>",
      "description": "<brief description from the text>"
    }}
  ],
  "relationships": [
    {{
      "source": "<source entity id>",
      "target": "<target entity id>",
      "relation_type": "<one of the relationship types>",
      "description": "<brief description>"
    }}
  ]
}}

Rules:
- Extract EVERY legal entity you can find (statutes, cases, courts, judges, parties, dates, concepts, penalties).
- Create relationships between entities where the text implies a connection.
- Use descriptive snake_case IDs (e.g., "section_302_ipc", "supreme_court_india").
- If two entities from different chunks refer to the same real-world entity, use the SAME id.
- Be thorough — missing an entity is worse than including a borderline one.
"""

        # ── Groq uses OpenAI-style chat completions ──
        response = self.client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": extraction_prompt}],
        )

        # ── Groq response format (OpenAI-style) ──
        raw_text = response.choices[0].message.content.strip()

        # Clean potential markdown fences
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
        raw_text = re.sub(r'\s*```$', '', raw_text)

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            print(f"[WARN] Failed to parse extraction JSON for {chunk_id}. Raw: {raw_text[:300]}")
            return GraphExtractionResult(entities=[], relationships=[])

        entities = [
            Entity(
                id=e["id"],
                name=e["name"],
                entity_type=e["entity_type"],
                description=e.get("description", ""),
                source_chunk=chunk_id,
            )
            for e in data.get("entities", [])
            if e.get("id") and e.get("name") and e.get("entity_type")
        ]

        relationships = [
            Relationship(
                source=r["source"],
                target=r["target"],
                relation_type=r["relation_type"],
                description=r.get("description", ""),
            )
            for r in data.get("relationships", [])
            if r.get("source") and r.get("target") and r.get("relation_type")
        ]

        return GraphExtractionResult(entities=entities, relationships=relationships)

    def add_extraction(self, result: GraphExtractionResult, chunk_text: str = ""):
        """Add extracted entities and relationships to the graph."""
        for entity in result.entities:
            if self.graph.has_node(entity.id):
                # Merge: append descriptions, keep all source chunks
                existing = self.graph.nodes[entity.id]
                if entity.description and entity.description not in existing.get("description", ""):
                    existing["description"] = f"{existing.get('description', '')} | {entity.description}"
                existing.setdefault("source_chunks", []).append(entity.source_chunk)
            else:
                self.graph.add_node(
                    entity.id,
                    name=entity.name,
                    entity_type=entity.entity_type,
                    description=entity.description or "",
                    source_chunks=[entity.source_chunk],
                )
            if chunk_text:
                self.chunk_map[entity.id] = chunk_text

        for rel in result.relationships:
            if rel.source in self.graph and rel.target in self.graph:
                self.graph.add_edge(
                    rel.source,
                    rel.target,
                    relation_type=rel.relation_type,
                    description=rel.description or "",
                )

    def build_from_chunks(self, chunks: list[dict]) -> dict:
        """
        Process all document chunks and build the knowledge graph.
        Returns stats about the constructed graph.
        """
        total_entities = 0
        total_relationships = 0

        for chunk in chunks:
            result = self.extract_from_chunk(chunk["text"], chunk["chunk_id"])
            self.add_extraction(result, chunk["text"])
            total_entities += len(result.entities)
            total_relationships += len(result.relationships)

        return {
            "chunks_processed": len(chunks),
            "entities_extracted": total_entities,
            "relationships_extracted": total_relationships,
            "unique_nodes": self.graph.number_of_nodes(),
            "unique_edges": self.graph.number_of_edges(),
        }

    def get_node_info(self, node_id: str) -> Optional[dict]:
        """Get full info for a node."""
        if node_id not in self.graph:
            return None
        data = dict(self.graph.nodes[node_id])
        data["id"] = node_id
        data["in_degree"] = self.graph.in_degree(node_id)
        data["out_degree"] = self.graph.out_degree(node_id)
        data["neighbors"] = list(self.graph.successors(node_id)) + list(self.graph.predecessors(node_id))
        return data

    def get_subgraph(self, center_node: str, max_hops: int = 2) -> nx.DiGraph:
        """Extract a subgraph centered on a node, up to max_hops away."""
        if center_node not in self.graph:
            return nx.DiGraph()

        visited = {center_node}
        frontier = {center_node}

        for _ in range(max_hops):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(self.graph.successors(node))
                next_frontier.update(self.graph.predecessors(node))
            next_frontier -= visited
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break

        return self.graph.subgraph(visited).copy()

    def get_stats(self) -> dict:
        """Return summary statistics of the knowledge graph."""
        if self.graph.number_of_nodes() == 0:
            return {"nodes": 0, "edges": 0, "entity_types": {}, "relationship_types": {}}

        entity_type_counts = {}
        for _, data in self.graph.nodes(data=True):
            etype = data.get("entity_type", "UNKNOWN")
            entity_type_counts[etype] = entity_type_counts.get(etype, 0) + 1

        rel_type_counts = {}
        for _, _, data in self.graph.edges(data=True):
            rtype = data.get("relation_type", "UNKNOWN")
            rel_type_counts[rtype] = rel_type_counts.get(rtype, 0) + 1

        degree_centrality = nx.degree_centrality(self.graph)
        top_nodes = sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "entity_types": entity_type_counts,
            "relationship_types": rel_type_counts,
            "most_connected": [
                {"id": nid, "name": self.graph.nodes[nid].get("name", nid), "centrality": round(score, 4)}
                for nid, score in top_nodes
            ],
            "is_connected": nx.is_weakly_connected(self.graph) if self.graph.number_of_nodes() > 0 else False,
            "connected_components": nx.number_weakly_connected_components(self.graph),
        }

    def export_for_visualization(self) -> dict:
        """Export graph data in a format suitable for frontend visualization."""
        nodes = []
        for nid, data in self.graph.nodes(data=True):
            nodes.append({
                "id": nid,
                "name": data.get("name", nid),
                "type": data.get("entity_type", "UNKNOWN"),
                "description": data.get("description", ""),
            })

        edges = []
        for src, tgt, data in self.graph.edges(data=True):
            edges.append({
                "source": src,
                "target": tgt,
                "relation": data.get("relation_type", "RELATES_TO"),
                "description": data.get("description", ""),
            })

        return {"nodes": nodes, "edges": edges}