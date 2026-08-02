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
    # Optional agent telemetry (see backend telemetry rollups)
    active_seconds: Optional[int] = Field(default=None, ge=0)
    idle_seconds: Optional[int] = Field(default=None, ge=0)
    telemetry_days_with_data: Optional[int] = Field(default=None, ge=0)
    segment_count: Optional[int] = Field(default=None, ge=0)
    focus_fragmentation_index: Optional[float] = Field(default=None, ge=0)
    first_seen_offset_minutes: Optional[int] = Field(default=None, ge=0)
    last_seen_offset_minutes: Optional[int] = Field(default=None, ge=0)


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


class SmartAttendanceAnalysis(BaseModel):
    """K-Means cluster label + Decision Tree reliability (see services/attendance_smart.py)."""

    attendance_category: str
    reliability_score: float = Field(..., ge=0, le=100)
    kmeans_cluster_id: int
    category_rank: int = Field(..., ge=0, le=3)
    algorithms_used: List[str]
    features: dict
    history_points_for_consistency: int = Field(ge=0)


class ExplanationItem(BaseModel):
    factor: str
    direction: str
    weight: float
    evidence: str
    contribution: float = 0.0


class DataQualityResult(BaseModel):
    status: str
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checked_fields: List[str] = Field(default_factory=list)


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
    telemetry_signal_quality: Optional[str] = None
    presence_consistency: Optional[str] = None
    smart_attendance: Optional[SmartAttendanceAnalysis] = None
    rule_engine_version: Optional[str] = None
    scoring_mode: Optional[str] = "rules"
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    data_quality: Optional[DataQualityResult] = None
    explanations: Optional[List[ExplanationItem]] = None
    working_hours: Optional[float] = Field(default=None, ge=0)
    idle_hours: Optional[float] = Field(default=None, ge=0)
    created_at: Optional[str] = None
    model_version: Optional[str] = None


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


class RankingEmployeeMetric(BaseModel):
    """Per-employee pillars (0–100) assembled by the portal from Postgres facts."""

    employee_id: str = Field(..., min_length=1, max_length=64)
    display_name: Optional[str] = Field(None, max_length=200)
    department_id: Optional[str] = Field(None, max_length=64)
    department_name: Optional[str] = Field(None, max_length=200)
    productivity: float = Field(..., ge=0, le=100)
    task_completion: float = Field(..., ge=0, le=100)
    attendance: float = Field(..., ge=0, le=100)
    efficiency: float = Field(..., ge=0, le=100)
    collaboration: float = Field(..., ge=0, le=100)


class PerformanceRankingRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    employees: List[RankingEmployeeMetric] = Field(..., min_length=1, max_length=500)
