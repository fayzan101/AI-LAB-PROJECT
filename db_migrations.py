from pathlib import Path

from sqlalchemy import create_engine, text

from config import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
engine = create_engine(settings.database_url, future=True)


def run_migrations() -> None:
    with engine.begin() as conn:
        dialect = conn.engine.dialect.name
        if dialect == "sqlite":
            existing_cols = conn.execute(text("PRAGMA table_info(employee_inputs)")).fetchall()
            has_tenant_id = any(str(row[1]) == "tenant_id" for row in existing_cols)
            if existing_cols and not has_tenant_id:
                # Local dev compatibility: reset legacy single-tenant SQLite tables.
                conn.execute(text("DROP TABLE IF EXISTS employee_inputs"))
                conn.execute(text("DROP TABLE IF EXISTS task_inputs"))
                conn.execute(text("DROP TABLE IF EXISTS analytics_reports"))
                conn.execute(text("DROP TABLE IF EXISTS idempotency_keys"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )

        applied_rows = conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
        applied_versions = {row[0] for row in applied_rows}

        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration_file.stem
            if version in applied_versions:
                continue
            sql_text = migration_file.read_text(encoding="utf-8")
            for statement in [s.strip() for s in sql_text.split(";") if s.strip()]:
                conn.execute(text(statement))
            conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": version},
            )
