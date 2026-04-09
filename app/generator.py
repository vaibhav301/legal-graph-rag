"""
Generator Module
Uses the LLM to generate grounded legal answers from knowledge graph context.
"""

from anthropic import Anthropic

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import ANTHROPIC_API_KEY, LLM_MODEL, MAX_TOKENS
from app.models import RetrievalResult


class LegalAnswerGenerator:
    """
    Generates grounded legal answers using retrieved knowledge graph context.
    Ensures answers are faithful to the source material and cite specific entities.
    """

    def __init__(self, api_key: str = ANTHROPIC_API_KEY):
        self.client = Anthropic(api_key=api_key)

    def generate(self, question: str, context: RetrievalResult) -> str:
        """Generate a legal answer grounded in the retrieved graph context."""

        system_prompt = """You are an expert legal research assistant. Your job is to answer legal questions 
using ONLY the knowledge graph context provided. 

Rules:
1. ONLY use information present in the provided context. Do NOT hallucinate or add external legal knowledge.
2. Reference specific entities (statutes, cases, courts, legal concepts) from the context.
3. If the context doesn't contain enough information to fully answer the question, say so explicitly.
4. Structure your answer clearly with relevant legal reasoning.
5. Cite the relationships between entities when explaining legal connections.
6. Use precise legal language but explain complex concepts clearly.
7. If multiple interpretations exist based on the context, present all of them.
"""

        user_prompt = f"""QUESTION: {question}

KNOWLEDGE GRAPH CONTEXT:
{context.subgraph_summary}

Based ONLY on the above context, provide a comprehensive answer to the question. 
Reference specific entities and relationships from the knowledge graph in your answer.
If the context is insufficient, clearly state what information is missing."""

        response = self.client.messages.create(
            model=LLM_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        return response.content[0].text

    def generate_with_sources(self, question: str, context: RetrievalResult) -> dict:
        """Generate answer with explicit source attribution."""

        answer = self.generate(question, context)

        # Extract source references from the context nodes
        sources = []
        for node in context.relevant_nodes:
            if node.get("source_text"):
                sources.append({
                    "entity": node["name"],
                    "type": node["type"],
                    "text_preview": node["source_text"][:200] + "..."
                    if len(node.get("source_text", "")) > 200 else node.get("source_text", ""),
                })

        return {
            "answer": answer,
            "sources": sources,
            "entities_used": len(context.relevant_nodes),
            "relationships_used": len(context.relevant_edges),
        }
