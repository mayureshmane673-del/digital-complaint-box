"""
database/migration_runner.py: Automation and verification for Supabase database migrations.
Executes SQL scripts when direct DB connection is provided, or validates existing schema.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env from root
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

sys.path.insert(0, str(project_root))
from database.supabase_client import check_schema_health, SUPABASE_URL


def run_migrations():
    print("=" * 60)
    print("Digital Complaint Box System - Supabase Migration Utility")
    print("=" * 60)
    print(f"Target Supabase Project: {SUPABASE_URL}")
    print()

    db_url = os.getenv("DATABASE_URL")
    migrations_dir = project_root / "database" / "migrations"
    all_sql_file = migrations_dir / "all_migrations.sql"

    if not all_sql_file.exists():
        print(f"Error: {all_sql_file} not found!")
        return False

    if db_url:
        print(f"DATABASE_URL detected. Attempting direct PostgreSQL execution...")
        try:
            # Try importing psycopg2 or psycopg or asyncpg
            try:
                import psycopg2
                conn = psycopg2.connect(db_url)
                cursor = conn.cursor()
                sql_content = all_sql_file.read_text(encoding="utf-8")
                cursor.execute(sql_content)
                conn.commit()
                cursor.close()
                conn.close()
                print("Successfully executed all migrations via PostgreSQL connection!")
            except ImportError:
                print("Note: psycopg2 is not installed. To execute directly, run: pip install psycopg2-binary")
                print("Alternatively, copy and run the SQL in Supabase Dashboard SQL Editor.")
        except Exception as e:
            print(f"PostgreSQL direct execution error: {e}")
    else:
        print("DATABASE_URL not set in .env.")
        print()
        print("To apply all database migrations to your Supabase project:")
        print("1. Open Supabase Dashboard: https://supabase.com/dashboard/project/trncsmuwxfljkhckoyra")
        print("2. Navigate to 'SQL Editor' in the left sidebar.")
        print(f"3. Open the file: {all_sql_file}")
        print("4. Paste the entire SQL content into the SQL Editor and click 'RUN'.")
        print()

    print("Checking Supabase Schema Health...")
    health = check_schema_health()
    if health["connected"] and health["tables_ready"]:
        print("SUCCESS: Supabase database schema is ready and verified!")
        return True
    elif health["connected"]:
        print("INFO: Supabase endpoint is reachable, but tables are pending creation.")
        print(f"Detail: {health.get('error')}")
        return False
    else:
        print(f"ERROR: Could not connect to Supabase: {health.get('error')}")
        return False


if __name__ == "__main__":
    run_migrations()
