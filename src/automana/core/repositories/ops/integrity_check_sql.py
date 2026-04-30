"""
Module-level SQL loaders for the read-only integrity-check scripts.

Each variable holds the full text of its corresponding .sql file, read once at
import time.  The pattern mirrors scryfall_data.py in this package.

SQL file locations (relative to the project root):
  src/automana/database/SQL/maintenance/scryfall_run_diff.sql
  src/automana/database/SQL/maintenance/scryfall_integrity_checks.sql
  src/automana/database/SQL/maintenance/public_schema_leak_check.sql
  src/automana/database/SQL/maintenance/pricing_run_diff.sql
  src/automana/database/SQL/maintenance/pricing_integrity_checks.sql
  src/automana/database/SQL/maintenance/mtgjson_run_diff.sql
  src/automana/database/SQL/maintenance/mtgjson_integrity_checks.sql
"""

import pathlib

_SQL_DIR = (
    pathlib.Path(__file__)
    .resolve()
    .parents[3]  # src/automana/
    .joinpath("database", "SQL", "maintenance")
)

scryfall_run_diff_sql: str = (
    _SQL_DIR / "scryfall_run_diff.sql"
).read_text(encoding="utf-8")

scryfall_integrity_checks_sql: str = (
    _SQL_DIR / "scryfall_integrity_checks.sql"
).read_text(encoding="utf-8")

public_schema_leak_check_sql: str = (
    _SQL_DIR / "public_schema_leak_check.sql"
).read_text(encoding="utf-8")

pricing_run_diff_sql: str = (
    _SQL_DIR / "pricing_run_diff.sql"
).read_text(encoding="utf-8")

pricing_integrity_checks_sql: str = (
    _SQL_DIR / "pricing_integrity_checks.sql"
).read_text(encoding="utf-8")

mtgjson_run_diff_sql: str = (
    _SQL_DIR / "mtgjson_run_diff.sql"
).read_text(encoding="utf-8")

mtgjson_integrity_checks_sql: str = (
    _SQL_DIR / "mtgjson_integrity_checks.sql"
).read_text(encoding="utf-8")
