from pydantic import BaseModel, Field
from typing import Any, Literal

class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)

class AnalyzeRequest(BaseModel):
    logs: str = Field(min_length=1, max_length=1_000_000)
    repository: str = Field(default="local", min_length=1, max_length=240)
    branch: str = Field(default="unknown", min_length=1, max_length=240)
    step_name: str = Field(default="CI workflow", min_length=1, max_length=240)

class Diagnosis(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    likely_cause: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    suggested_fix: str = Field(min_length=1, max_length=4000)
    is_flaky: bool = False
    source: Literal["deterministic", "ai"] = "deterministic"

class SpecRequest(BaseModel):
    spec: dict[str, Any]
    path: str = Field(min_length=1, max_length=500)
    method: str = Field(default="GET", min_length=1, max_length=10)
    status_code: int = Field(ge=100, le=599)
    payload: Any = None

class IssueUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved"]
