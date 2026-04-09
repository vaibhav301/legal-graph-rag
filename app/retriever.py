"""
Graph-Based Retriever Module
Retrieves relevant context from the knowledge graph using graph traversal — NO vectors needed.
Uses LLM to identify entry-point entities from the user's question, then traverses the graph.
"""

import json
import re
import networkx as nx
from anthropic import Anthropic

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import ANTHROPIC_API_KEY, LLM_MODEL, MAX_RETRIEVAL_HOPS, MAX_CONTEXT_NODES
from app.knowledge_graph import LegalKnowledgeGraph
from app.models import RetrievalResult


class GraphRetriever:
    """
    Retrieves relevant legal context from the knowledge graph.

    Pipeline:
    1. LLM identifies key entities from the user's question
    2. Fuzzy-match those entities to graph nodes
    3. Traverse the graph (BFS) to collect related nodes
    4. Rank and select the most relevant context
    5. Return structured context for the generator
    """

    def __init__(self, kg: LegalKnowledgeGraph, api_key: str = ANTHROPIC_API_KEY):
        self.kg = kg
        self.client = Anthropic(api_key=api_key)

    def retrieve(self, question: str, max_hops: int = MAX_RETRIEVAL_HOPS,
                 max_nodes: int = MAX_CONTEXT_NODES) -> RetrievalResult:
        """
        Main retrieval pipeline: question -> entities -> graph traversal -> context.
        """
        # Step 1: Extract entity mentions from the question
        target_entities = self._identify_entities_in_question(question)

        # Step 2: Match to graph nodes
        matched_nodes = self._match_to_graph(target_entities)

        if not matched_nodes:
            # Fallback: keyword search across all node names/descriptions
            matched_nodes = self._keyword_fallback(question)

        # Step 3: Traverse graph from matched nodes
        relevant_nodes = []
        relevant_edges = []
        visited = set()

        for start_node in matched_nodes:
            subgraph = self.kg.get_subgraph(start_node, max_hops=max_hops)
            for nid, data in subgraph.nodes(data=True):
                if nid not in visited:
                    visited.add(nid)
                    relevant_nodes.append({
                        "id": nid,
                        "name": data.get("name", nid),
                        "type": data.get("entity_type", ""),
                        "description": data.get("description", ""),
                        "source_text": self.kg.chunk_map.get(nid, ""),
                    })

            for src, tgt, data in subgraph.edges(data=True):
                relevant_edges.append({
                    "source": src,
                    "target": tgt,
                    "relation": data.get("relation_type", ""),
                    "description": data.get("description", ""),
                })

        # Step 4: Rank by relevance (degree centrality + proximity to seed nodes)
        relevant_nodes = self._rank_nodes(relevant_nodes, matched_nodes)[:max_nodes]

        # Step 5: Build summary
        subgraph_summary = self._build_context_summary(relevant_nodes, relevant_edges)

        return RetrievalResult(
            relevant_nodes=relevant_nodes,
            relevant_edges=relevant_edges,
            subgraph_summary=subgraph_summary,
        )

    def _identify_entities_in_question(self, question: str) -> list[dict]:
        """Use LLM to extract entity references from the user's question."""
        prompt = f"""From this legal question, extract the key entities the user is asking about.

QUESTION: "{question}"

Respond ONLY with valid JSON (no markdown, no preamble):
{{
  "entities": [
    {{
      "name": "<entity name as mentioned>",
      "likely_type": "<STATUTE|CASE|COURT|PARTY|JUDGE|LEGAL_CONCEPT|PENALTY|JURISDICTION|DATE>",
      "search_terms": ["<alternative names or keywords to find this entity>"]
    }}
  ]
}}
"""
        response = self.client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        try:
            data = json.loads(raw)
            return data.get("entities", [])
        except json.JSONDecodeError:
            # Fallback: treat the whole question as a search term
            return [{"name": question, "likely_type": "LEGAL_CONCEPT", "search_terms": question.split()}]

    def _match_to_graph(self, target_entities: list[dict]) -> list[str]:
        """Fuzzy-match extracted entities to actual graph nodes."""
        matched = []

        for entity in target_entities:
            search_terms = [entity["name"].lower()]
            search_terms.extend([t.lower() for t in entity.get("search_terms", [])])

            best_match = None
            best_score = 0

            for nid, data in self.kg.graph.nodes(data=True):
                node_name = data.get("name", nid).lower()
                node_desc = data.get("description", "").lower()
                node_id_lower = nid.lower()

                for term in search_terms:
                    score = 0
                    term_lower = term.lower()

                    # Exact match
                    if term_lower == node_name or term_lower == node_id_lower:
                        score = 1.0
                    # Substring match
                    elif term_lower in node_name or term_lower in node_id_lower:
                        score = 0.8
                    elif node_name in term_lower:
                        score = 0.7
                    # Word overlap
                    else:
                        term_words = set(term_lower.split())
                        name_words = set(node_name.split())
                        overlap = term_words & name_words
                        if overlap:
                            score = 0.5 * len(overlap) / max(len(term_words), len(name_words))

                    # Bonus for description match
                    if term_lower in node_desc:
                        score += 0.2

                    if score > best_score:
                        best_score = score
                        best_match = nid

            if best_match and best_score >= 0.3:
                matched.append(best_match)

        return list(set(matched))

    def _keyword_fallback(self, question: str) -> list[str]:
        """Fallback: search all nodes by keyword overlap with the question."""
        question_words = set(re.findall(r'\b\w{3,}\b', question.lower()))
        # Remove common stop words
        stop_words = {"the", "what", "which", "how", "does", "can", "are", "was", "were",
                       "this", "that", "for", "with", "from", "about", "under", "between"}
        question_words -= stop_words

        scored_nodes = []
        for nid, data in self.kg.graph.nodes(data=True):
            node_text = f"{data.get('name', '')} {data.get('description', '')} {nid}".lower()
            node_words = set(re.findall(r'\b\w{3,}\b', node_text))
            overlap = question_words & node_words
            if overlap:
                scored_nodes.append((nid, len(overlap)))

        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        return [nid for nid, _ in scored_nodes[:5]]

    def _rank_nodes(self, nodes: list[dict], seed_nodes: list[str]) -> list[dict]:
        """Rank retrieved nodes by relevance."""
        for node in nodes:
            nid = node["id"]
            score = 0.0

            # Higher score if it's a seed node (directly matched)
            if nid in seed_nodes:
                score += 5.0

            # Degree centrality (well-connected nodes are usually important)
            if nid in self.kg.graph:
                degree = self.kg.graph.degree(nid)
                score += min(degree * 0.5, 3.0)

            # Bonus for nodes with source text (more context available)
            if node.get("source_text"):
                score += 1.0

            # Bonus for important entity types
            important_types = {"STATUTE", "CASE", "LEGAL_CONCEPT", "COURT"}
            if node.get("type") in important_types:
                score += 1.0

            node["relevance_score"] = round(score, 2)

        nodes.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return nodes

    def _build_context_summary(self, nodes: list[dict], edges: list[dict]) -> str:
        """Build a text summary of the retrieved subgraph for the generator."""
        lines = ["=== RETRIEVED LEGAL KNOWLEDGE GRAPH CONTEXT ===\n"]

        lines.append("## Entities Found:")
        for node in nodes:
            desc = f" — {node['description']}" if node.get("description") else ""
            lines.append(f"  [{node['type']}] {node['name']}{desc}")

        lines.append("\n## Relationships:")
        for edge in edges:
            desc = f" ({edge['description']})" if edge.get("description") else ""
            lines.append(f"  {edge['source']} --[{edge['relation']}]--> {edge['target']}{desc}")

        lines.append("\n## Source Texts:")
        seen_texts = set()
        for node in nodes:
            if node.get("source_text") and node["source_text"] not in seen_texts:
                seen_texts.add(node["source_text"])
                lines.append(f"\n--- Source for {node['name']} ---")
                lines.append(node["source_text"][:500])

        return "\n".join(lines)
