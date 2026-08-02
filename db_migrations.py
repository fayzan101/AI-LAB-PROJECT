from pathlib import Path

from sqlalchemy import create_engine, text

from config import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
engine = create_engine(settings.database_url, future=True)

# Prefixed so we never collide with the portal backend's `schema_migrations` table
# (same Neon DB is often shared; portal uses column `id`, AI used `version`).
AI_SCHEMA_MIGRATIONS = "ai_schema_migrations"


def _sqlite_init_sql(sql_text: str) -> str:
    """BIGSERIAL is Postgres-only; map to SQLite autoincrement PKs for local/dev."""
    return sql_text.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")


def run_migrations() -> None:
    with engine.begin() as conn:
        dialect = conn.engine.dialect.name
        if dialect == "sqlite":
            existing_cols = conn.execute(text("PRAGMA table_info(employee_inputs)")).fetchall()
            has_tenant_id = any(str(row[1]) == "tenant_id" for row in existing_cols)
            if existing_cols and not has_tenant_id:
                conn.execute(text("DROP TABLE IF EXISTS employee_inputs"))
                conn.execute(text("DROP TABLE IF EXISTS task_inputs"))
                conn.execute(text("DROP TABLE IF EXISTS analytics_reports"))
                conn.execute(text("DROP TABLE IF EXISTS ai_idempotency_keys"))
                conn.execute(text("DROP TABLE IF EXISTS idempotency_keys"))

        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {AI_SCHEMA_MIGRATIONS} (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )

        applied_rows = conn.execute(text(f"SELECT version FROM {AI_SCHEMA_MIGRATIONS}")).fetchall()
        applied_versions = {row[0] for row in applied_rows}

        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration_file.stem
            if version in applied_versions:
                continue
            sql_text = migration_file.read_text(encoding="utf-8")
            if dialect == "sqlite":
                sql_text = _sqlite_init_sql(sql_text)
            for statement in [s.strip() for s in sql_text.split(";") if s.strip()]:
                # Skip pure comment-only chunks
                if all(line.strip().startswith("--") or not line.strip() for line in statement.splitlines()):
                    continue
                conn.execute(text(statement))
            conn.execute(
                text(f"INSERT INTO {AI_SCHEMA_MIGRATIONS} (version) VALUES (:version)"),
                {"version": version},
            )
