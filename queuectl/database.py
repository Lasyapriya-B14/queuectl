# Database operations for QueueCTL
import sqlite3
import os
from typing import List, Optional
from datetime import datetime, timezone
from .models import Job, JobState
import threading


class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Store in user's home directory
            home = os.path.expanduser("~")
            db_dir = os.path.join(home, ".queuectl")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "queuectl.db")
        
        self.db_path = db_path
        self.local = threading.local()
        self.init_db()
    
    def get_connection(self):
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.local.conn.row_factory = sqlite3.Row
        return self.local.conn
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT,
                next_retry_at TEXT,
                locked_by TEXT,
                locked_at TEXT
            )
        """)
        
        # Config table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Worker tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)
        
        conn.commit()
    
    def enqueue_job(self, job: Job) -> bool:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO jobs (id, command, state, attempts, max_retries, 
                                created_at, updated_at, error_message, next_retry_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id, job.command, job.state, job.attempts, job.max_retries,
                job.created_at, job.updated_at, job.error_message, job.next_retry_at
            ))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def get_job(self, job_id: str) -> Optional[Job]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        
        if row:
            return self._row_to_job(row)
        return None
    
    def get_next_pending_job(self, worker_id: str) -> Optional[Job]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Get a pending job that's not locked and ready for retry
        cursor.execute("""
            SELECT * FROM jobs 
            WHERE state IN (?, ?) 
            AND (locked_by IS NULL OR locked_at < datetime('now', '-5 minutes'))
            AND (next_retry_at IS NULL OR next_retry_at <= ?)
            ORDER BY created_at ASC
            LIMIT 1
        """, (JobState.PENDING.value, JobState.FAILED.value, now))
        
        row = cursor.fetchone()
        
        if row:
            job = self._row_to_job(row)
            
            # Lock the job
            cursor.execute("""
                UPDATE jobs 
                SET locked_by = ?, locked_at = ?, state = ?, updated_at = ?
                WHERE id = ? AND (locked_by IS NULL OR locked_at < datetime('now', '-5 minutes'))
            """, (worker_id, now, JobState.PROCESSING.value, now, job.id))
            
            conn.commit()
            
            if cursor.rowcount > 0:
                job.state = JobState.PROCESSING.value
                return job
        
        return None
    
    def update_job(self, job: Job) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        job.updated_at = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            UPDATE jobs 
            SET state = ?, attempts = ?, updated_at = ?, 
                error_message = ?, next_retry_at = ?, locked_by = NULL, locked_at = NULL
            WHERE id = ?
        """, (
            job.state, job.attempts, job.updated_at,
            job.error_message, job.next_retry_at, job.id
        ))
        
        conn.commit()
        return cursor.rowcount > 0
    
    def list_jobs(self, state: Optional[str] = None) -> List[Job]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if state:
            cursor.execute("SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC", (state,))
        else:
            cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        
        return [self._row_to_job(row) for row in cursor.fetchall()]
    
    def get_job_counts(self) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT state, COUNT(*) as count 
            FROM jobs 
            GROUP BY state
        """)
        
        counts = {state.value: 0 for state in JobState}
        for row in cursor.fetchall():
            counts[row[0]] = row[1]
        
        return counts
    
    def delete_job(self, job_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
        
        return cursor.rowcount > 0
    
    def _row_to_job(self, row) -> Job:
        return Job(
            id=row["id"],
            command=row["command"],
            state=row["state"],
            attempts=row["attempts"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_message=row["error_message"],
            next_retry_at=row["next_retry_at"]
        )
    
    def register_worker(self, worker_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO workers (worker_id, started_at, last_heartbeat, status)
            VALUES (?, ?, ?, ?)
        """, (worker_id, now, now, "running"))
        
        conn.commit()
        return True
    
    def update_worker_heartbeat(self, worker_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            UPDATE workers 
            SET last_heartbeat = ?
            WHERE worker_id = ?
        """, (now, worker_id))
        
        conn.commit()
        return cursor.rowcount > 0
    
    def remove_worker(self, worker_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,))
        conn.commit()
        
        return cursor.rowcount > 0
    
    def get_active_workers(self) -> List[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Workers active in last 30 seconds
        cursor.execute("""
            SELECT * FROM workers 
            WHERE last_heartbeat >= datetime('now', '-30 seconds')
            ORDER BY started_at DESC
        """)
        
        workers = []
        for row in cursor.fetchall():
            workers.append({
                "worker_id": row["worker_id"],
                "started_at": row["started_at"],
                "last_heartbeat": row["last_heartbeat"],
                "status": row["status"]
            })
        
        return workers
    
    def set_config(self, key: str, value: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO config (key, value)
            VALUES (?, ?)
        """, (key, value))
        
        conn.commit()
        return True
    
    def get_config(self, key: str, default: str = None) -> Optional[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        
        if row:
            return row["value"]
        return default
    
    def close(self):
        if hasattr(self.local, 'conn'):
            self.local.conn.close()