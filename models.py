from dataclasses import dataclass


@dataclass
class EmployeeRecord:
    employee_id: str
    tasks_completed: int
    attendance_days: int
    idle_hours: float
    working_hours: float
    task_progress: float
    days_left: int
    late_arrivals: int
    absent_days: int


@dataclass
class TaskRecord:
    employee_id: str
    task_id: str
    progress_percent: float
    days_left: int
