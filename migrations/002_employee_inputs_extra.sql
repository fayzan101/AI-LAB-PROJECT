-- Forward-compatible telemetry payload snapshot (normalized agent aggregates).
ALTER TABLE employee_inputs ADD COLUMN extra_json TEXT NOT NULL DEFAULT '{}';
