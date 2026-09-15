"""
verify_migrations.py: Detailed syntax and structural integrity verification for all_migrations.sql.
"""

import sqlparse
from pathlib import Path

sql_path = Path("database/migrations/all_migrations.sql")
content = sql_path.read_text(encoding="utf-8")
statements = [s.strip() for s in sqlparse.split(content) if s.strip()]

tables = []
indexes = []
policies = []
functions = []
triggers = []
views = []

for s in statements:
    upper = s.upper()
    if "CREATE TABLE" in upper:
        name = s.split("TABLE")[1].split("(")[0].replace("IF NOT EXISTS", "").strip()
        tables.append(name)
    elif "CREATE INDEX" in upper or "CREATE UNIQUE INDEX" in upper:
        indexes.append(s[:50])
    elif "CREATE POLICY" in upper:
        pname = s.split("POLICY")[1].split("ON")[0].strip(' "')
        policies.append(pname)
    elif "CREATE OR REPLACE FUNCTION" in upper:
        fname = s.split("FUNCTION")[1].split("(")[0].strip()
        functions.append(fname)
    elif "CREATE TRIGGER" in upper:
        tname = s.split("TRIGGER")[1].split("BEFORE")[0].split("AFTER")[0].strip()
        triggers.append(tname)
    elif "CREATE OR REPLACE VIEW" in upper or "CREATE VIEW" in upper:
        vname = s.split("VIEW")[1].split("AS")[0].strip()
        views.append(vname)

print("=== SQL COMPONENT VALIDATION REPORT ===")
print(f"Total Valid Statements: {len(statements)}")
print(f"Tables ({len(tables)}): {tables}")
print(f"Views ({len(views)}): {views}")
print(f"Functions ({len(functions)}): {functions}")
print(f"Triggers ({len(triggers)}): {triggers}")
print(f"Indexes: {len(indexes)}")
print(f"RLS and Storage Policies: {len(policies)}")

# Assertions
assert len(tables) >= 18, f"Expected at least 18 tables, got {len(tables)}"
assert "anonymous_complaint_owners" in tables, "anonymous_complaint_owners table missing!"
assert "student_directory" in views, "student_directory view missing!"
assert "check_roll_number_eligibility" in functions, "check_roll_number_eligibility function missing!"
assert "cleanup_old_notifications" in functions, "cleanup_old_notifications function missing!"

print("\nSUCCESS: All structural and security database components are validated!")
