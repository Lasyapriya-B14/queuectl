# Integration test scenarios for QueueCTL = These tests validate the expected test scenarios from the assignment
import pytest
import os
import tempfile
import time
from queuectl.database import Database
from queuectl.config import Config
from queuectl.queue import Queue
from queuectl.worker import Worker
from queuectl.models import Job, JobState
import threading


class TestScenarios:    
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
        self.config = Config(self.db)
        self.queue = Queue(self.db, self.config)
    
    def teardown_method(self):
        self.db.close()
        os.unlink(self.temp_db.name)
    
    def test_scenario_1_basic_job_completes(self):
        #Scenario 1: Basic job completes successfully
        # Enqueue job
        job = Job(id="success-job", command="echo 'Test Success'")
        self.queue.enqueue(job)
        
        # Process with worker
        worker = Worker(self.db, self.config, "test-worker-1")
        job_to_process = self.db.get_next_pending_job("test-worker-1")
        
        assert job_to_process is not None
        assert job_to_process.id == "success-job"
        
        worker._process_job(job_to_process)
        
        # Verify completion
        completed_job = self.db.get_job("success-job")
        assert completed_job.state == JobState.COMPLETED.value
        assert completed_job.attempts == 1
        assert completed_job.error_message is None
    
    def test_scenario_2_failed_job_retries_and_dlq(self):
        #Scenario 2: Failed job retries with backoff and moves to DLQ
        # Configure for faster testing
        self.config.set_max_retries(3)
        self.config.set_backoff_base(2)
        
        # Enqueue failing job
        job = Job(id="fail-job", command="exit 1", max_retries=3)
        self.queue.enqueue(job)
        
        worker = Worker(self.db, self.config, "test-worker-2")
        
        # Attempt 1
        job_attempt1 = self.db.get_next_pending_job("test-worker-2")
        assert job_attempt1.state == JobState.PROCESSING.value
        worker._process_job(job_attempt1)
        
        failed_job = self.db.get_job("fail-job")
        assert failed_job.state == JobState.FAILED.value
        assert failed_job.attempts == 1
        assert failed_job.next_retry_at is not None
        
        # Simulate time passing (set next_retry_at to past)
        failed_job.next_retry_at = "2020-01-01T00:00:00"
        self.db.update_job(failed_job)
        
        # Attempt 2
        job_attempt2 = self.db.get_next_pending_job("test-worker-2")
        worker._process_job(job_attempt2)
        failed_job = self.db.get_job("fail-job")
        assert failed_job.attempts == 2
        
        # Simulate time passing
        failed_job.next_retry_at = "2020-01-01T00:00:00"
        self.db.update_job(failed_job)
        
        # Attempt 3 (final)
        job_attempt3 = self.db.get_next_pending_job("test-worker-2")
        worker._process_job(job_attempt3)
        
        # Verify moved to DLQ
        dead_job = self.db.get_job("fail-job")
        assert dead_job.state == JobState.DEAD.value
        assert dead_job.attempts == 3
        
        # Verify in DLQ
        dlq_jobs = self.queue.list_dlq_jobs()
        assert len(dlq_jobs) == 1
        assert dlq_jobs[0].id == "fail-job"
    
    def test_scenario_3_multiple_workers_no_overlap(self):
        #Scenario 3: Multiple workers process jobs without overlap
        # Enqueue multiple jobs
        for i in range(5):
            job = Job(id=f"multi-job-{i}", command=f"echo Job {i}")
            self.queue.enqueue(job)
        
        # Track processed jobs
        processed_jobs = []
        lock = threading.Lock()
        
        def worker_thread(worker_id):
            """Worker thread function"""
            worker = Worker(self.db, self.config, f"test-worker-{worker_id}")
            
            for _ in range(3):  # Try to get 3 jobs
                job = self.db.get_next_pending_job(f"test-worker-{worker_id}")
                if job:
                    with lock:
                        # Ensure no duplicate processing
                        assert job.id not in processed_jobs
                        processed_jobs.append(job.id)
                    
                    worker._process_job(job)
                time.sleep(0.1)
        
        # Start 3 workers
        threads = []
        for i in range(3):
            t = threading.Thread(target=worker_thread, args=(i,))
            t.start()
            threads.append(t)
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Verify all jobs processed exactly once
        assert len(processed_jobs) == 5
        assert len(set(processed_jobs)) == 5  # No duplicates
    
    def test_scenario_4_invalid_commands_fail_gracefully(self):
        #Scenario 4: Invalid commands fail gracefully
        # Enqueue invalid command
        job = Job(id="invalid-cmd", command="thisisnotarealcommand123", max_retries=2)
        self.queue.enqueue(job)
        
        worker = Worker(self.db, self.config, "test-worker-4")
        job_to_process = self.db.get_next_pending_job("test-worker-4")
        
        # Process invalid command
        worker._process_job(job_to_process)
        
        # Verify failed gracefully
        failed_job = self.db.get_job("invalid-cmd")
        assert failed_job.state == JobState.FAILED.value
        assert failed_job.error_message is not None
        assert "not found" in failed_job.error_message.lower() or "exit" in failed_job.error_message.lower()
    
    def test_scenario_5_job_data_survives_restart(self):
        # Scenario 5: Job data survives restart
        # Create and enqueue jobs
        job1 = Job(id="persist-1", command="echo Test 1")
        job2 = Job(id="persist-2", command="echo Test 2", state=JobState.COMPLETED.value)
        
        self.queue.enqueue(job1)
        self.queue.enqueue(job2)
        
        # Close database (simulate restart)
        self.db.close()
        
        # Reconnect to same database
        new_db = Database(self.temp_db.name)
        new_queue = Queue(new_db, Config(new_db))
        
        # Verify jobs still exist
        retrieved_job1 = new_db.get_job("persist-1")
        retrieved_job2 = new_db.get_job("persist-2")
        
        assert retrieved_job1 is not None
        assert retrieved_job1.id == "persist-1"
        assert retrieved_job1.command == "echo Test 1"
        
        assert retrieved_job2 is not None
        assert retrieved_job2.state == JobState.COMPLETED.value
        
        new_db.close()
    
    def test_retry_from_dlq(self):
        # Test retrying a job from DLQ
        # Create dead job
        job = Job(id="dlq-retry", command="echo Retry me", state=JobState.DEAD.value, attempts=3)
        self.db.enqueue_job(job)
        
        # Verify in DLQ
        dlq_jobs = self.queue.list_dlq_jobs()
        assert len(dlq_jobs) == 1
        
        # Retry from DLQ
        success = self.queue.retry_dlq_job("dlq-retry")
        assert success is True
        
        # Verify back in queue
        retried_job = self.db.get_job("dlq-retry")
        assert retried_job.state == JobState.PENDING.value
        assert retried_job.attempts == 0
        assert retried_job.error_message is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])