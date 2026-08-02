"""Export training rows from analytics_reports / employee_inputs (best-effort)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Export labeled rows for ML training")
    parser.add_argument("--out", type=Path, default=ROOT / "ml" / "datasets" / "export.csv")
    args = parser.parse_args()

    try:
        from database import engine
        from sqlalchemy import text
    except Exception as exc:  # noqa: BLE001
        print(f"DB unavailable: {exc}", file=sys.stderr)
        return 1

    sql = text(
        """
        SELECT e.employee_id, e.tasks_completed, e.attendance_days, e.idle_hours, e.working_hours,
               e.task_progress, e.days_left, e.extra_json, a.productivity_score AS label
        FROM employee_inputs e
        LEFT JOIN analytics_reports a
          ON a.employee_id = e.employee_id AND a.tenant_id = e.tenant_id
        WHERE a.productivity_score IS NOT NULL
        LIMIT 5000
        """
    )
    rows_out = []
    with engine.connect() as conn:
        for row in conn.execute(sql):
            extra = {}
            if row.extra_json:
                try:
                    extra = json.loads(row.extra_json) if isinstance(row.extra_json, str) else (row.extra_json or {})
                except Exception:  # noqa: BLE001
                    extra = {}
            rows_out.append(
                {
                    "employee_id": row.employee_id,
                    "working_hours": row.working_hours,
                    "idle_hours": row.idle_hours,
                    "attendance_days": row.attendance_days,
                    "segment_count": extra.get("segment_count", 0),
                    "focus_fragmentation_index": extra.get("focus_fragmentation_index", 0),
                    "task_progress": row.task_progress,
                    "tasks_completed": row.tasks_completed,
                    "active_seconds": extra.get("active_seconds", 0),
                    "idle_seconds": extra.get("idle_seconds", 0),
                    "label": row.label,
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not rows_out:
        print("No rows exported", file=sys.stderr)
        return 1
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"Wrote {len(rows_out)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
