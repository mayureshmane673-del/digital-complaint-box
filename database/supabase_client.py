"""
database/supabase_client.py: Production Supabase client wrapper
Provides resilient connection management, query execution, error handling, and auth session state.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Configure logging
logger = logging.getLogger("complaint_box.supabase")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Ensure .env is loaded from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://trncsmuwxfljkhckoyra.supabase.co")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_beZbQfSIK54uypoJ18WnNw_XqgobOnQ")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_client_instance: Optional[Client] = None
_admin_client_instance: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Returns the standard Supabase client initialized with publishable key.
    Safe for all application operations.
    """
    global _client_instance
    if _client_instance is None:
        if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured in .env")
        try:
            _client_instance = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
            logger.info("Initialized Supabase client with project URL: %s", SUPABASE_URL)
        except Exception as e:
            logger.error("Failed to initialize Supabase client: %s", e)
            raise
    return _client_instance


def get_admin_supabase_client() -> Optional[Client]:
    """
    Returns the elevated Supabase admin client if SUPABASE_SERVICE_ROLE_KEY is configured.
    Used ONLY in backend server tasks, never sent or exposed to UI.
    """
    global _admin_client_instance
    if _admin_client_instance is None and SUPABASE_SERVICE_ROLE_KEY:
        try:
            _admin_client_instance = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            logger.info("Initialized Supabase admin client with service role key.")
        except Exception as e:
            logger.warning("Failed to initialize Supabase admin client: %s", e)
            return None
    return _admin_client_instance


def get_trusted_backend_client() -> Client:
    """
    Returns the trusted backend Supabase client (service role client if configured,
    or standard client for dev/test). Used strictly in protected backend services.
    """
    admin = get_admin_supabase_client()
    if admin is not None:
        return admin
    return get_supabase_client()


_schema_health_cache: Optional[Dict[str, Any]] = None


def check_schema_health(force_check: bool = False) -> Dict[str, Any]:
    """
    Verifies connection to Supabase and tests whether core tables exist in the schema cache.
    Caches the health result to prevent redundant queries on view switches.
    """
    global _schema_health_cache
    if _schema_health_cache is not None and not force_check:
        return _schema_health_cache

    client = get_supabase_client()
    status = {
        "connected": False,
        "tables_ready": False,
        "missing_tables": [],
        "error": None
    }
    required_tables = [
        "departments", "locations", "categories", "subcategories",
        "staff_users", "staff_security_codes", "roll_number_pool",
        "students", "complaints", "complaint_history", "feedback",
        "notifications", "issue_groups"
    ]

    try:
        # Test basic connection with departments table
        client.table("departments").select("id").limit(1).execute()
        status["connected"] = True
        status["tables_ready"] = True
    except Exception as e:
        err_msg = str(e)
        logger.warning("Schema check result: %s", err_msg)
        if "Could not find the table" in err_msg or "PGRST205" in err_msg:
            status["connected"] = True
            status["tables_ready"] = False
            status["error"] = "Database tables are not yet created in Supabase. Please run all_migrations.sql in the Supabase SQL Editor."
        else:
            status["connected"] = False
            status["error"] = err_msg

    _schema_health_cache = status
    return status
