from pydantic import BaseModel, Field
from typing import Any, Literal

class AnalyzeRequest(BaseModel):
    logs: str = Field(min_length=1, max_length=1_000_000)
    repository: str = Field(default="local", max_length=240)
    branch: str = Field(default="unknown", max_length=240)
    step_name: str = Field(default="CI workflow", max_length=240)

class Diagnosis(BaseModel):
    summary: str
    likely_cause: str
    confidence: float = Field(ge=0, le=1)
    suggested_fix: str
    is_flaky: bool = False
    source: Literal["deterministic", "ai"] = "deterministic"

class SpecRequest(BaseModel):
    spec: dict[str, Any]
    path: str
    method: str = "GET"
    status_code: int
    payload: Any = None

class IssueUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved"]
