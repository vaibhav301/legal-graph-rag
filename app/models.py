from pydantic import BaseModel, Field
from typing import Optional


class DocumentUpload(BaseModel):
    filename: str
    content: str


class QueryRequest(BaseModel):
    question: str
    max_hops: int = Field(default=2, ge=1, le=5)
    max_context_nodes: int = Field(default=15, ge=5, le=50)


class Entity(BaseModel):
    id: str
    name: str
    entity_type: str
    description: Optional[str] = None
    source_chunk: Optional[str] = None


class Relationship(BaseModel):
    source: str
    target: str
    relation_type: str
    description: Optional[str] = None


class GraphExtractionResult(BaseModel):
    entities: list[Entity]
    relationships: list[Relationship]


class RetrievalResult(BaseModel):
    relevant_nodes: list[dict]
    relevant_edges: list[dict]
    subgraph_summary: str


class QueryResponse(BaseModel):
    answer: str
    retrieved_context: RetrievalResult
    graph_stats: dict
    sources: list[str]
