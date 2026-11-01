from typing import Literal

from pydantic import BaseModel, Field


class BugLedgerEntry(BaseModel):
    model_config = {"extra": "forbid"}
    
    bug_id: str
    type: Literal[
        "HARDCODED_OVERRIDE", 
        "BROKEN_RANGE", 
        "SUPPRESSED_ERROR", 
        "VOLATILE_CHAIN", 
        "ORPHAN_REFERENCE", 
        "DYNAMIC_VBA_WRITE"
    ]
    sheet: str
    address: str
    expected_r1c1: str
    observed: float | str | bool | None
    cluster_id: str
    downstream_node_count: int
    downstream_sample: list[str]
    
    # Bounded 1-5 to align with standard 5-point risk scorecards
    severity: int = Field(ge=1, le=5)