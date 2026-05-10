CREATE TABLE IF NOT EXISTS employee_inputs (
    id INTEGER PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    employee_id VARCHAR(64) NOT NULL,
    tasks_completed INTEGER NOT NULL,
    attendance_days INTEGER NOT NULL,
    idle_hours DOUBLE PRECISION NOT NULL,
    working_hours DOUBLE PRECISION NOT NULL,
    task_progress DOUBLE PRECISION NOT NULL,
    days_left INTEGER NOT NULL,
    late_arrivals INTEGER NOT NULL,
    absent_days INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_inputs (
    id INTEGER PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    employee_id VARCHAR(64) NOT NULL,
    task_id VARCHAR(128) NOT NULL,
    progress_percent DOUBLE PRECISION NOT NULL,
    days_left INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analytics_reports (
    id INTEGER PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    employee_id VARCHAR(64) NOT NULL,
    report_json TEXT NOT NULL,
    productivity_score DOUBLE PRECISION NOT NULL,
    burnout_risk VARCHAR(32) NOT NULL,
    task_delay_risk VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_employee_inputs_tenant_employee_created
    ON employee_inputs (tenant_id, employee_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_inputs_tenant_employee_created
    ON task_inputs (tenant_id, employee_id, created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_reports_tenant_employee_created
    ON analytics_reports (tenant_id, employee_id, created_at);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id INTEGER PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    endpoint VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, endpoint, idempotency_key)
);
