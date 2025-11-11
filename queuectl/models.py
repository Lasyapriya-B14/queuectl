# Data models for QueueCTL
from enum import Enum
from datetime import datetime, timezone
from typing import Optional
import json


class JobState(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


class Job:    
    def __init__(
        self,
        id: str,
        command: str,
        state: str = JobState.PENDING.value,
        attempts: int = 0,
        max_retries: int = 3,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        error_message: Optional[str] = None,
        next_retry_at: Optional[str] = None
    ):
        self.id = id
        self.command = command
        self.state = state
        self.attempts = attempts
        self.max_retries = max_retries
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.updated_at = updated_at or datetime.now(timezone.utc).isoformat()
        self.error_message = error_message
        self.next_retry_at = next_retry_at
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "command": self.command,
            "state": self.state,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error_message": self.error_message,
            "next_retry_at": self.next_retry_at
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Job':
        return cls(
            id=data["id"],
            command=data["command"],
            state=data.get("state", JobState.PENDING.value),
            attempts=data.get("attempts", 0),
            max_retries=data.get("max_retries", 3),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            error_message=data.get("error_message"),
            next_retry_at=data.get("next_retry_at")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Job':
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def __repr__(self) -> str:
        return f"Job(id={self.id}, state={self.state}, attempts={self.attempts})"