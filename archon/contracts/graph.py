from typing import Literal
from pydantic import BaseModel, UUID4
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
    origin: Literal["formula", "vba_write"]
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
    workbook_id: UUID4
    nodes: list[Node]
    edges: list[Edge]
    bugs: list[BugLedgerEntry]  # No default, must be explicitly passed
    cycles: list[Cycle]
    stats: Stats