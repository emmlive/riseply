"""
Startup schema migration.

Base.metadata.create_all() alone only creates tables that don't exist
yet -- it never adds new columns to a table that's already there. That's
fine the very first time a database is created, but every subsequent
column added to an existing model (which has happened repeatedly as this
app grew) needs an explicit ALTER TABLE, or a long-running production
database silently drifts out of sync with the code and starts throwing
"column does not exist" errors.

This walks every model's table: for tables that already exist, it adds
any columns present in the model but missing from the live database
(using each Column's own type/server_default so the generated SQL stays
correct as models change); for tables that don't exist yet, it leaves
them for create_all() to create normally.

This is a pragmatic stopgap, not a replacement for a real migration tool
(Alembic) -- it can't handle column renames, type changes, or drops, only
straightforward additive changes. Worth migrating to Alembic before the
schema needs anything more complex than "add a column."
"""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn

from app.database import engine, Base
from app import models  # noqa: F401 -- import registers every model on Base.metadata


def _add_column(conn, table_name: str, column):
    """Adds one missing column, defensively. Tries the column exactly as
    the model defines it (including its default) first -- this is what
    Postgres needs for constant defaults to actually apply to existing
    rows. Some dialects (SQLite notably) reject non-constant defaults
    like CURRENT_TIMESTAMP in ADD COLUMN; if that happens, fall back to
    adding the bare column with no default rather than crashing startup
    over it. A missing default on existing rows is a minor gap; a
    crashed app is not.
    """
    ddl = CreateColumn(column).compile(dialect=conn.dialect)
    full_stmt = f"ALTER TABLE {table_name} ADD COLUMN {ddl}"
    try:
        with conn.begin():
            conn.execute(text(full_stmt))
        print(f"[migrate] {full_stmt}")
        return
    except Exception as e:
        print(f"[migrate] full ADD COLUMN failed ({e}); retrying without default")

    col_type = column.type.compile(dialect=conn.dialect)
    bare_stmt = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}"
    with conn.begin():
        conn.execute(text(bare_stmt))
    print(f"[migrate] {bare_stmt} (added without default -- existing rows are NULL here)")


def run_migration():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand new table -- create_all() below handles it

            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                _add_column(conn, table.name, column)

    Base.metadata.create_all(bind=engine)

    # Backfill: any admin created before role-based access existed had no
    # admin_role value -- treat those as "super" rather than leaving them
    # with an empty role that would fail every permission check below.
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text(
                "UPDATE users SET admin_role = 'super' "
                "WHERE is_admin = true AND (admin_role IS NULL OR admin_role = '')"
                if engine.dialect.name != "sqlite" else
                "UPDATE users SET admin_role = 'super' "
                "WHERE is_admin = 1 AND (admin_role IS NULL OR admin_role = '')"
            ))


if __name__ == "__main__":
    run_migration()
    print("[migrate] done")
