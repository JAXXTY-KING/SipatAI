from pathlib import Path

from app.db.session import get_connection

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"


def apply_migrations() -> None:
    """Apply each unapplied SQL migration in filename order."""
    migration_files = sorted(MIGRATIONS_DIRECTORY.glob("[0-9]*.sql"))
    if not migration_files:
        raise RuntimeError("No SQL migrations were found.")

    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        for migration_file in migration_files:
            version = migration_file.name
            already_applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s",
                (version,),
            ).fetchone()
            if already_applied:
                continue

            connection.execute(migration_file.read_text(encoding="utf-8"), prepare=False)
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )
            print(f"Applied database migration {version}.")


if __name__ == "__main__":
    apply_migrations()
