#Basic tests for QueueCTL 
import pytest
import os
import tempfile
from queuectl.database import Database
from queuectl.config import Config
from queuectl.queue import Queue
from queuectl.models import Job, JobState
from queuectl.utils import execute_command, calculate_backoff_delay


class TestDatabase:
    #Test database operations
    
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
    
    def teardown_method(self):
        self.db.close()
        os.unlink(self.temp_db.name)
    
    def test_enqueue_job(self):
        job = Job(id="test1", command="echo hello")
        assert self.db.enqueue_job(job) is True
        
        # Test duplicate
        assert self.db.enqueue_job(job) is False
    
    def test_get_job(self):
        job = Job(id="test2", command="echo world")
        self.db.enqueue_job(job)
        
        retrieved = self.db.get_job("test2")
        assert retrieved is not None
        assert retrieved.id == "test2"
        assert retrieved.command == "echo world"
    
    def test_update_job(self):
        job = Job(id="test3", command="echo test")
        self.db.enqueue_job(job)
        
        job.state = JobState.COMPLETED.value
        job.attempts = 1
        assert self.db.update_job(job) is True
        
        retrieved = self.db.get_job("test3")
        assert retrieved.state == JobState.COMPLETED.value
        assert retrieved.attempts == 1


class TestUtils:
    #Test utility functions
    
    def test_execute_command_success(self):
        exit_code, stdout, stderr = execute_command("echo hello")
        assert exit_code == 0
        assert "hello" in stdout
    
    def test_execute_command_failure(self):
        exit_code, stdout, stderr = execute_command("nonexistentcommand")
        assert exit_code != 0
    
    def test_calculate_backoff_delay(self):
        assert calculate_backoff_delay(0, 2) == 1  # 2^0
        assert calculate_backoff_delay(1, 2) == 2  # 2^1
        assert calculate_backoff_delay(2, 2) == 4  # 2^2
        assert calculate_backoff_delay(3, 2) == 8  # 2^3


class TestConfig:
    #Test configuration management
    
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
        self.config = Config(self.db)
    
    def teardown_method(self):
        self.db.close()
        os.unlink(self.temp_db.name)
    
    def test_default_config(self):
        assert self.config.get_max_retries() == 3
        assert self.config.get_backoff_base() == 2
    
    def test_set_config(self):
        self.config.set_max_retries(5)
        assert self.config.get_max_retries() == 5
        
        self.config.set_backoff_base(3)
        assert self.config.get_backoff_base() == 3


class TestQueue:
    #Test queue operations
    
    def setup_method(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
        self.config = Config(self.db)
        self.queue = Queue(self.db, self.config)
    
    def teardown_method(self):
        self.db.close()
        os.unlink(self.temp_db.name)
    
    def test_enqueue(self):
        job = Job(id="q1", command="echo test")
        assert self.queue.enqueue(job) is True
    
    def test_list_jobs(self):
        job1 = Job(id="q2", command="echo 1")
        job2 = Job(id="q3", command="echo 2")
        
        self.queue.enqueue(job1)
        self.queue.enqueue(job2)
        
        jobs = self.queue.list_jobs()
        assert len(jobs) == 2
    
    def test_dlq_operations(self):
        job = Job(id="q4", command="echo dead", state=JobState.DEAD.value)
        self.db.enqueue_job(job)
        
        dlq_jobs = self.queue.list_dlq_jobs()
        assert len(dlq_jobs) == 1
        
        # Retry
        assert self.queue.retry_dlq_job("q4") is True
        retrieved = self.db.get_job("q4")
        assert retrieved.state == JobState.PENDING.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])