from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, model_validator

from archon.contracts.bugs import BugLedgerEntry


class Risk(BaseModel):
    model_config = {"extra": "forbid"}
    score: int
    flags: list[str]


class VbaRef(BaseModel):
    model_config = {"extra": "forbid"}
    module: str
    line: int


class Node(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    kind: Literal["cluster", "cell", "input", "vba_target"]
    sheet: str
    r1c1: str
    anchor: str
    member_count: int | None = None
    member_ranges: list[str] | None = None
    ast_hash: str | None = None
    header: str | None = None
    risk: Risk | None = None


class Edge(BaseModel):
    model_config = {"extra": "forbid"}
    source: str
    target: str
    origin: Literal["formula", "vba_write", "vba_read"]
    confidence: Literal["static", "dynamic"]
    vba_ref: VbaRef | None = None


class Cycle(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    nodes: list[str]
    classification: Literal["intentional_iterative", "user_error", "unclassified"]
    evidence: str


class Stats(BaseModel):
    model_config = {"extra": "forbid"}
    cells_in: int
    nodes_out: int
    compression_ratio: float


class DagGraph(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: Literal["1.0"]
    workbook_id: UUID
    nodes: list[Node]
    edges: list[Edge]
    bugs: list[BugLedgerEntry]  # No default, must be explicitly passed
    cycles: list[Cycle]
    stats: Stats

    @model_validator(mode="after")
    def edges_must_reference_known_nodes(self) -> Self:
        """Reject duplicate node ids, then reject any edge whose source or
        target id is not present among the (now confirmed unique) nodes."""
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"duplicate node id '{node.id}'")
            seen.add(node.id)

        node_ids = seen
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"edge source '{edge.source}' is not a known node id")
            if edge.target not in node_ids:
                raise ValueError(f"edge target '{edge.target}' is not a known node id")
        return self