"""SQLite integration for job management."""

import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger


class SQLiteManager:
    """Manager for SQLite job database."""

    JOB_BOARD_MAPPING = {
        "seek.com.au": "seek",
        "linkedin.com": "linkedin",
        "indeed.com": "indeed",
        "boards.greenhouse.io": "greenhouse",
        "jobs.lever.co": "lever",
    }

    def __init__(self, db_path: Optional[str] = None):
        """Initialize SQLite database connection."""
        if db_path is None:
            # Check RONIN_HOME first, then fallback to project root
            from ronin.config import get_ronin_home

            ronin_home = str(get_ronin_home())
            user_db = os.path.join(ronin_home, "data", "ronin.db")
            project_db = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "ronin.db",
            )
            # Prefer user dir if it exists, otherwise use project root
            if os.path.exists(os.path.dirname(user_db)):
                db_path = user_db
            elif os.path.exists(os.path.dirname(project_db)):
                db_path = project_db
            else:
                db_path = user_db  # Will be created

        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        logger.info(f"Connected to SQLite database: {db_path}")

        self._init_schema()
        self.existing_companies = {}

    def _init_schema(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                website TEXT,
                linkedin_ref TEXT,
                description TEXT,
                type TEXT,
                created_at TEXT NOT NULL,
                has_active_job INTEGER DEFAULT 0
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                score INTEGER DEFAULT 0,
                key_tools TEXT,
                recommendation TEXT,
                overview TEXT,
                url TEXT,
                source TEXT,
                quick_apply INTEGER DEFAULT 0,
                created_at TEXT,
                pay TEXT,
                type TEXT,
                location TEXT,
                status TEXT DEFAULT 'DISCOVERED',
                keywords TEXT,
                company_id INTEGER,
                recruiter_id INTEGER,
                open_job INTEGER DEFAULT 0,
                last_modified TEXT,
                job_classification TEXT DEFAULT 'SHORT_TERM',
                resume_profile TEXT DEFAULT 'default',
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        """
        )

        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name)"
        )
        # Compound index for pending jobs query (status + quick_apply + score)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_pending ON jobs(status, quick_apply, score DESC)"
        )
        # Index for job classification
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_classification ON jobs(job_classification)"
        )

        # Migrations: add columns if they don't exist on older databases
        for col, default in [
            ("job_classification", "'SHORT_TERM'"),
            ("resume_profile", "'default'"),
            ("key_tools", "''"),
        ]:
            try:
                cursor.execute(f"SELECT {col} FROM jobs LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute(
                    f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT {default}"
                )
                logger.info(f"Migrated database: added {col} column")

        # Migrate data from old tech_stack column to key_tools
        try:
            cursor.execute("SELECT tech_stack FROM jobs LIMIT 1")
            # Old column exists — copy data to new column if key_tools is empty
            cursor.execute(
                "UPDATE jobs SET key_tools = tech_stack "
                "WHERE key_tools IS NULL OR key_tools = ''"
            )
            logger.info("Migrated tech_stack data to key_tools column")
        except sqlite3.OperationalError:
            pass  # tech_stack column doesn't exist (fresh DB)

        self.conn.commit()
        logger.debug("Database schema initialized")

    def _get_job_source(self, url: str) -> str:
        """Determine job source from URL."""
        try:
            domain = urlparse(url).netloc.lower()
            for board_domain, source in self.JOB_BOARD_MAPPING.items():
                if board_domain in domain:
                    return source
            return "unknown"
        except Exception:
            return "unknown"

    def job_exists(self, job_id: str) -> bool:
        """Check if a job ID already exists in the database using EXISTS query."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM jobs WHERE job_id = ? LIMIT 1", (job_id,))
        return cursor.fetchone() is not None

    def _get_or_create_company(self, company_name: str) -> Optional[int]:
        """Get existing company ID or create a new one."""
        if not company_name:
            return None

        company_lower = company_name.lower()
        if company_lower in self.existing_companies:
            return self.existing_companies[company_lower]

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (company_name,)
            )
            row = cursor.fetchone()

            if row:
                company_id = row[0]
                self.existing_companies[company_lower] = company_id
                return company_id

            cursor.execute(
                "INSERT INTO companies (name, created_at) VALUES (?, ?)",
                (company_name, datetime.now().isoformat()),
            )
            self.conn.commit()

            company_id = cursor.lastrowid
            self.existing_companies[company_lower] = company_id
            logger.debug(f"Created company: {company_name} (ID: {company_id})")

            return company_id

        except sqlite3.Error as e:
            logger.error(f"Error getting/creating company '{company_name}': {e}")
            return None

    def insert_job(self, job_data: Dict) -> bool:
        """Insert a job into database if it doesn't exist."""
        job_id = job_data.get("job_id")

        if not job_id:
            logger.error("Missing job_id in job_data")
            return False

        # Use EXISTS query instead of in-memory set
        if self.job_exists(job_id):
            logger.debug(f"Job {job_id} already exists, skipping")
            return False

        try:
            company_name = job_data.get("company", "")
            analysis_data = job_data.get("analysis", {})
            url = job_data.get("url", "")
            source = job_data.get("source") or self._get_job_source(url)
            company_id = self._get_or_create_company(company_name)

            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO jobs (
                    job_id, title, description, score, key_tools, recommendation,
                    overview, url, source, quick_apply, created_at, pay, type,
                    location, status, keywords, company_id, job_classification,
                    resume_profile
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    job_data.get("title", ""),
                    job_data.get("description", ""),
                    analysis_data.get("score", 0),
                    analysis_data.get("key_tools")
                    or analysis_data.get("tech_stack", "N/A"),
                    analysis_data.get("recommendation", ""),
                    analysis_data.get("overview", ""),
                    url,
                    source,
                    1 if job_data.get("quick_apply", False) else 0,
                    job_data.get("created_at"),
                    job_data.get("pay_rate", ""),
                    job_data.get("work_type", ""),
                    job_data.get("location", ""),
                    "DISCOVERED",
                    ", ".join(analysis_data.get("tech_keywords", [])),
                    company_id,
                    analysis_data.get("job_classification", "SHORT_TERM"),
                    analysis_data.get("resume_profile", "default"),
                ),
            )
            self.conn.commit()

            logger.info(f"Added job {job_id}: {job_data.get('title', '')[:50]}")
            return True

        except sqlite3.IntegrityError:
            # Race condition: job was inserted between check and insert
            logger.debug(f"Job {job_id} already exists (race condition)")
            return False
        except sqlite3.Error as e:
            logger.error(f"Error adding job {job_id} to database: {e}")
            self.conn.rollback()
            return False

    def batch_insert_jobs(self, jobs_data: List[Dict]) -> Dict[str, int]:
        """Insert multiple jobs into database."""
        new_jobs_count = 0
        duplicate_count = 0
        error_count = 0

        for job in jobs_data:
            try:
                if self.insert_job(job):
                    new_jobs_count += 1
                else:
                    duplicate_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to insert job: {e}")

        return {
            "new_jobs": new_jobs_count,
            "duplicates": duplicate_count,
            "errors": error_count,
        }

    def get_pending_jobs(self, limit: int = 10) -> List[Dict]:
        """Get jobs that are ready to apply to."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT j.*, c.name as company_name
                FROM jobs j
                LEFT JOIN companies c ON j.company_id = c.id
                WHERE j.status IN ('DISCOVERED', 'APP_ERROR')
                AND j.quick_apply = 1
                ORDER BY j.score DESC, j.created_at DESC
                LIMIT ?
            """,
                (limit,),
            )

            jobs = []
            for row in cursor.fetchall():
                job_dict = dict(row)
                job_dict["fields"] = {
                    "Title": job_dict.get("title"),
                    "Company Name": job_dict.get("company_name"),
                    "URL": job_dict.get("url"),
                    "Description": job_dict.get("description"),
                    "Score": job_dict.get("score", 0),
                    "Key Tools": job_dict.get("key_tools", ""),
                    "Job Classification": job_dict.get(
                        "job_classification", "SHORT_TERM"
                    ),
                    "Resume Profile": job_dict.get("resume_profile", "default"),
                }
                jobs.append(job_dict)

            return jobs

        except sqlite3.Error as e:
            logger.error(f"Error getting pending jobs: {e}")
            return []

    def update_job_status(self, job_id: str, status: str) -> bool:
        """Update the status of a job by job_id."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE jobs
                SET status = ?, last_modified = ?
                WHERE job_id = ?
            """,
                (status, datetime.now().isoformat(), job_id),
            )

            self.conn.commit()

            if cursor.rowcount > 0:
                logger.debug(f"Updated job {job_id} status to {status}")
                return True
            else:
                logger.warning(f"Job {job_id} not found for status update")
                return False

        except sqlite3.Error as e:
            logger.error(f"Error updating job status: {e}")
            self.conn.rollback()
            return False

    def update_record(self, record_id: int, fields: dict):
        """Update an existing job record by database ID."""
        if not fields:
            return

        # Whitelist allowed field names to prevent SQL injection
        allowed_fields = {
            "status",
            "score",
            "key_tools",
            "recommendation",
            "overview",
            "last_modified",
            "job_classification",
            "resume_profile",
            "title",
            "description",
            "url",
            "pay",
            "type",
            "location",
            "keywords",
        }

        safe_fields = {k: v for k, v in fields.items() if k in allowed_fields}
        if not safe_fields:
            logger.warning(f"No valid fields to update for record {record_id}")
            return

        try:
            set_clause = ", ".join([f"{key} = ?" for key in safe_fields.keys()])
            values = list(safe_fields.values()) + [record_id]

            cursor = self.conn.cursor()
            cursor.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
            self.conn.commit()

            logger.debug(f"Updated record {record_id}")
        except sqlite3.Error as e:
            logger.error(f"Error updating record {record_id}: {e}")
            self.conn.rollback()

    def get_jobs_stats(self) -> Dict:
        """Get statistics about jobs in the database."""
        try:
            cursor = self.conn.cursor()
            stats = {}

            cursor.execute("SELECT COUNT(*) FROM jobs")
            stats["total_jobs"] = cursor.fetchone()[0]

            cursor.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
            stats["by_status"] = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT source, COUNT(*) FROM jobs GROUP BY source ORDER BY COUNT(*) DESC"
            )
            stats["by_source"] = {row[0]: row[1] for row in cursor.fetchall()}

            return stats

        except sqlite3.Error as e:
            logger.error(f"Error getting job stats: {e}")
            return {}

    def get_existing_job_ids(self) -> set:
        """Get all existing job IDs. Use sparingly - prefer job_exists() for single checks."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT job_id FROM jobs")
        return {row[0] for row in cursor.fetchall()}

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.debug("Database connection closed")

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except Exception:
            pass
