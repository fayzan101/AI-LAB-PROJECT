from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class EmployeeInput(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    employee_id: str = Field(..., min_length=1, max_length=64)
    tasks_completed: int = Field(0, ge=0)
    attendance_days: int = Field(0, ge=0)
    idle_hours: float = Field(0, ge=0)
    working_hours: float = Field(0, ge=0)
    task_progress: float = Field(0, ge=0, le=100)
    days_left: int = Field(0, ge=0)
    late_arrivals: int = Field(0, ge=0)
    absent_days: int = Field(0, ge=0)


class BaselinePoint(BaseModel):
    date: date
    productivity_score: float
    working_hours: float = Field(ge=0)
    idle_hours: float = Field(ge=0)


class AnalyticsReportRequest(EmployeeInput):
    history: List[BaselinePoint] = Field(default_factory=list)


class BenchmarkResult(BaseModel):
    status: str
    z_score: float
    baseline_mean: float
    baseline_std: float
    sample_count: int
    message: str


class AnomalyResult(BaseModel):
    is_anomaly: bool
    severity: str
    reasons: List[str]


class ReportResponse(BaseModel):
    tenant_id: str
    employee_id: str
    productivity_score: float
    burnout_risk: str
    task_delay_risk: str
    attendance_pattern: str
    adaptive_benchmark: BenchmarkResult
    anomaly_detection: AnomalyResult
    summary: str
    recommendations: List[str]


class ApiEnvelope(BaseModel):
    status: str = "success"
    message: str = "Request processed successfully"
    data: dict
    meta: Optional[dict] = None


class ErrorEnvelope(BaseModel):
    status: str = "error"
    message: str
    error_code: str
    trace_id: str
    data: dict = {}
    meta: Optional[dict] = None
