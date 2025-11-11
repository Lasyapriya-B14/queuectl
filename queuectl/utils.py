#Utility functions for QueueCTL
import subprocess
import shlex
from datetime import datetime, timezone, timedelta
from typing import Tuple


def execute_command(command: str) -> Tuple[int, str, str]:
    try:
        # Parse command safely
        args = shlex.split(command)
        
        # Execute command with timeout
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            shell=False
        )
        
        return result.returncode, result.stdout, result.stderr
    
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out after 300 seconds"
    
    except FileNotFoundError:
        return 127, "", f"Command not found: {command.split()[0]}"
    
    except Exception as e:
        return -1, "", f"Error executing command: {str(e)}"


def calculate_backoff_delay(attempts: int, base: int = 2) -> int:
    return base ** attempts


def calculate_next_retry_time(attempts: int, base: int = 2) -> str:
    delay_seconds = calculate_backoff_delay(attempts, base)
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    return next_retry.isoformat()


def format_job_for_display(job) -> dict:

    return {
        "ID": job.id[:20] + "..." if len(job.id) > 20 else job.id,
        "Command": job.command[:40] + "..." if len(job.command) > 40 else job.command,
        "State": job.state,
        "Attempts": f"{job.attempts}/{job.max_retries}",
        "Created": job.created_at.split("T")[0] if "T" in job.created_at else job.created_at,
        "Error": (job.error_message[:30] + "...") if job.error_message and len(job.error_message) > 30 else (job.error_message or "")
    }