# Worker implementation for QueueCTL
import time
import signal
import sys
from datetime import datetime
from typing import Optional
import uuid


class Worker:
    def __init__(self, db, config, worker_id: Optional[str] = None):
        self.db = db
        self.config = config
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.running = False
        self.current_job = None
        
        # Register signal handlers for graceful shutdown (only in main thread)
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            # Signal handling only works in main thread, ignore in worker threads
            pass
    
    def _signal_handler(self, signum, frame):
        print(f"\n[{self.worker_id}] Received shutdown signal. Finishing current job...")
        self.running = False
    
    def start(self):
        from .models import JobState
        from .utils import execute_command, calculate_next_retry_time
        
        self.running = True
        self.db.register_worker(self.worker_id)
        
        print(f"[{self.worker_id}] Worker started")
        
        try:
            while self.running:
                # Update heartbeat
                self.db.update_worker_heartbeat(self.worker_id)
                
                # Get next job
                job = self.db.get_next_pending_job(self.worker_id)
                
                if job:
                    self.current_job = job
                    self._process_job(job)
                    self.current_job = None
                else:
                    # No jobs available, sleep briefly
                    time.sleep(1)
        
        except Exception as e:
            print(f"[{self.worker_id}] Error: {e}")
        
        finally:
            # Cleanup
            if self.current_job:
                from .models import JobState
                # Release lock on current job if still processing
                self.current_job.state = JobState.FAILED.value
                self.current_job.error_message = "Worker shutdown during processing"
                self.db.update_job(self.current_job)
            
            self.db.remove_worker(self.worker_id)
            print(f"[{self.worker_id}] Worker stopped")
    
    def _process_job(self, job):
        from .models import JobState
        from .utils import execute_command, calculate_next_retry_time
        
        print(f"[{self.worker_id}] Processing job {job.id}: {job.command}")
        
        # Execute the command
        exit_code, stdout, stderr = execute_command(job.command)
        
        # Update job based on result
        job.attempts += 1
        
        if exit_code == 0:
            # Success
            job.state = JobState.COMPLETED.value
            job.error_message = None
            print(f"[{self.worker_id}] Job {job.id} completed successfully")
        else:
            # Failure
            error_msg = stderr.strip() if stderr else f"Command exited with code {exit_code}"
            job.error_message = error_msg
            
            if job.attempts >= job.max_retries:
                # Move to DLQ
                job.state = JobState.DEAD.value
                print(f"[{self.worker_id}] Job {job.id} moved to DLQ after {job.attempts} attempts")
            else:
                # Schedule retry with exponential backoff
                job.state = JobState.FAILED.value
                backoff_base = self.config.get_backoff_base()
                job.next_retry_at = calculate_next_retry_time(job.attempts, backoff_base)
                print(f"[{self.worker_id}] Job {job.id} failed (attempt {job.attempts}/{job.max_retries}). "
                      f"Next retry at: {job.next_retry_at}")
        
        # Save job state
        self.db.update_job(job)


def _worker_process(worker_num):
    from .database import Database
    from .config import Config
    
    db = Database()
    config = Config(db)
    worker = Worker(db, config, worker_id=f"worker-{worker_num}")
    worker.start()


def start_workers(count: int = 1):
    import multiprocessing
    
    processes = []
    
    try:
        for i in range(count):
            p = multiprocessing.Process(target=_worker_process, args=(i + 1,))
            p.start()
            processes.append(p)
            print(f"Started worker {i + 1}/{count}")
        
        print(f"\n{count} worker(s) running. Press Ctrl+C to stop.\n")
        
        # Wait for all processes
        for p in processes:
            p.join()
    
    except KeyboardInterrupt:
        print("\nShutting down workers...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.join()
        print("All workers stopped")