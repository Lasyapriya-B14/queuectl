#Queue management for QueueCTL 
from typing import List, Optional
from .database import Database
from .config import Config
from .models import Job, JobState


class Queue:
    #Queue manager for job operations
    
    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
    
    def enqueue(self, job: Job) -> bool:
        # Apply default max_retries from config if not set
        if job.max_retries is None or job.max_retries == 0:
            job.max_retries = self.config.get_max_retries()
        
        return self.db.enqueue_job(job)
    
    def get_job(self, job_id: str) -> Optional[Job]:
        return self.db.get_job(job_id)
    
    def list_jobs(self, state: Optional[str] = None) -> List[Job]:
        return self.db.list_jobs(state)
    
    def list_dlq_jobs(self) -> List[Job]:
        return self.db.list_jobs(JobState.DEAD.value)
    
    def retry_dlq_job(self, job_id: str) -> bool:
        job = self.db.get_job(job_id)
        if not job:
            return False
        if job.state != JobState.DEAD.value:
            return False
        
        # Reset job state for retry
        job.state = JobState.PENDING.value
        job.attempts = 0
        job.error_message = None
        job.next_retry_at = None
        
        return self.db.update_job(job)
    
    def get_status(self) -> dict:
        job_counts = self.db.get_job_counts()
        active_workers = self.db.get_active_workers()
        
        return {
            "jobs": job_counts,
            "workers": {
                "active": len(active_workers),
                "details": active_workers
            },
            "config": self.config.get_all()
        }
    
    def delete_job(self, job_id: str) -> bool:
        return self.db.delete_job(job_id)