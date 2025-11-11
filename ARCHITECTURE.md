# QueueCTL Architecture & Design

This document provides a detailed technical overview of QueueCTL's architecture, design decisions, and implementation details.

## System Overview

QueueCTL is a single-machine job queue system built with simplicity, reliability, and clarity in mind. It uses Python for implementation, SQLite for persistence, and multiprocessing for concurrent job execution.

### High-Level Architecture

```
┌──────────────────────────────────────────────────┐
│                   CLI Layer                       │
│              (Click Framework)                    │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│              Queue Manager                        │
│  (Job Enqueueing, Status, DLQ Management)       │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│           Database Layer (SQLite)                 │
│  (Jobs, Workers, Config, Locking)                │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│            Worker Processes                       │
│  (Job Execution, Retry Logic, Backoff)           │
└──────────────────────────────────────────────────┘
```

## Core Components

### 1. CLI Interface (`cli.py`)

**Responsibility**: User interaction and command routing

**Key Features**:
- Built with Click framework for professional CLI experience
- Command groups: enqueue, worker, status, list, dlq, config
- Input validation and error handling
- Formatted output with tabulate

**Design Decisions**:
- Click over argparse: Better UX, automatic help generation
- Separate command groups for logical organization
- JSON input for jobs: Standard format, easy integration

### 2. Database Layer (`database.py`)

**Responsibility**: Data persistence and transactional integrity

**Schema Design**:

```sql
-- Jobs table
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT,
    next_retry_at TEXT,
    locked_by TEXT,           -- Worker lock
    locked_at TEXT            -- Lock timestamp
)

-- Workers table
CREATE TABLE workers (
    worker_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    last_heartbeat TEXT NOT NULL,
    status TEXT NOT NULL
)

-- Config table
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
```

**Key Features**:
- Thread-local connections for multiprocessing safety
- Job locking mechanism to prevent duplicate processing
- Automatic lock expiration (5 minutes)
- Worker heartbeat tracking

**Design Decisions**:
- SQLite over in-memory: Persistence requirement
- WAL mode: Better concurrent access
- Text timestamps: Simplicity, ISO 8601 format
- Pessimistic locking: Prevent race conditions

### 3. Job Model (`models.py`)

**Job States**:
```
PENDING    → Job waiting to be processed
PROCESSING → Currently being executed by a worker
COMPLETED  → Successfully executed
FAILED     → Failed but retryable
DEAD       → Permanently failed (in DLQ)
```

**Job Structure**:
```python
{
    "id": str,              # Unique identifier
    "command": str,         # Shell command
    "state": str,          # Current state
    "attempts": int,       # Retry count
    "max_retries": int,    # Max retry attempts
    "created_at": str,     # ISO timestamp
    "updated_at": str,     # ISO timestamp
    "error_message": str,  # Error details
    "next_retry_at": str   # Backoff timestamp
}
```

### 4. Queue Manager (`queue.py`)

**Responsibility**: Job lifecycle management

**Operations**:
- `enqueue()`: Add jobs to queue
- `list_jobs()`: Query jobs by state
- `get_status()`: System status snapshot
- `retry_dlq_job()`: Move job from DLQ to pending

**Design Pattern**: Facade pattern - simplifies database interactions

### 5. Worker Process (`worker.py`)

**Responsibility**: Job execution and retry logic

**Worker Lifecycle**:
```
1. Register in database
2. Update heartbeat (every iteration)
3. Poll for next job
4. Acquire lock on job
5. Execute command
6. Update job state based on result
7. Release lock
8. Repeat or shutdown gracefully
```

**Execution Flow**:
```python
def _process_job(job):
    1. Execute command via subprocess
    2. Capture exit code, stdout, stderr
    3. If success (exit_code == 0):
       - Mark as COMPLETED
    4. If failure:
       - Increment attempts
       - If attempts < max_retries:
           - Calculate backoff delay
           - Mark as FAILED with next_retry_at
       - Else:
           - Mark as DEAD (move to DLQ)
```

**Graceful Shutdown**:
- Signal handlers for SIGINT/SIGTERM
- Finish current job before exit
- Release locks and cleanup

### 6. Configuration (`config.py`)

**Responsibility**: System-wide settings management

**Settings**:
- `max_retries`: Default 3
- `backoff_base`: Default 2 (for 2^attempts delay)

**Storage**: Database-backed for persistence

### 7. Utilities (`utils.py`)

**Responsibility**: Helper functions

**Key Functions**:
- `execute_command()`: Safe subprocess execution
- `calculate_backoff_delay()`: Exponential backoff calculation
- `calculate_next_retry_time()`: Schedule next retry
- `format_job_for_display()`: Output formatting

## Data Flow

### Job Enqueueing

```
User Input → CLI → Queue.enqueue() → Database.enqueue_job() → SQLite
```

### Job Processing

```
Worker Poll → Database.get_next_pending_job() 
          → Lock Acquisition
          → Job Execution
          → Result Processing
          → State Update
          → Database.update_job()
```

### Retry Logic

```
Job Fails → Increment attempts
        → Calculate backoff: delay = 2^attempts
        → Set next_retry_at = now + delay
        → Mark as FAILED
        → Wait for next_retry_at
        → Worker picks up again
```

## Concurrency Model

### Multi-Worker Safety

**Problem**: Multiple workers must not process same job

**Solution**: Database-level locking

```sql
UPDATE jobs 
SET locked_by = ?, locked_at = ?, state = 'processing'
WHERE id = ? 
  AND (locked_by IS NULL OR locked_at < datetime('now', '-5 minutes'))
```

**Lock Expiration**: Handles crashed workers (5-minute timeout)

### Thread Safety

- Each worker process has its own database connection
- SQLite WAL mode enables concurrent reads
- Writes are serialized by SQLite

## Retry Mechanism

### Exponential Backoff

**Formula**: `delay = base^attempts` seconds

**Example** (base=2, max_retries=3):
- Attempt 1: Immediate
- Attempt 2: 2 seconds later (2^1)
- Attempt 3: 4 seconds later (2^2)
- Attempt 4: 8 seconds later (2^3)
- After attempt 4: Move to DLQ

**Benefits**:
- Reduces load on failing services
- Gives transient failures time to recover
- Prevents thundering herd

### Dead Letter Queue

**Purpose**: Isolate permanently failed jobs

**Triggers**:
- Attempts exceed max_retries
- Jobs remain in DEAD state

**Operations**:
- List: View all dead jobs
- Retry: Move job back to PENDING (reset attempts)

## Security Considerations

### Command Execution

**Safety Measures**:
1. `shlex.split()`: Prevents shell injection
2. `shell=False`: No shell interpretation
3. Timeout: 5-minute execution limit
4. Capture output: Prevent terminal pollution

**Limitations**:
- No sandboxing (containers)
- Runs with worker user permissions
- Trust required for job commands

## Performance Characteristics

### Throughput

- **Single worker**: ~10-100 jobs/sec (command dependent)
- **Multiple workers**: Linear scaling up to ~10 workers
- **Database**: SQLite handles thousands of jobs easily

### Scalability Limits

- **Jobs**: Millions (SQLite limit: 281 TB)
- **Workers**: ~50 per machine (resource dependent)
- **Throughput**: ~1000 jobs/min (single machine)

### Bottlenecks

1. **SQLite writes**: Serialized in WAL mode
2. **Worker polling**: 1-second sleep when no jobs
3. **Lock contention**: Increases with worker count

## Error Handling

### Job Execution Errors

- **Exit code != 0**: Mark as failed, schedule retry
- **Command not found**: Immediate failure, retry
- **Timeout**: Mark as failed after 5 minutes
- **Exception**: Caught, logged, job marked failed

### System Errors

- **Database locked**: Retry with backoff
- **Disk full**: Graceful error, stop enqueueing
- **Worker crash**: Lock expires, job picked up by another worker

## Monitoring & Observability

### Current State

- `status` command: Job counts, active workers, config
- `list` command: Job details by state
- Worker logs: Stdout/stderr from worker processes

### Metrics Available

- Jobs by state (pending, processing, completed, failed, dead)
- Active worker count
- Worker heartbeat timestamps
- Job attempt counts
- Error messages

## Trade-offs & Limitations

### Chosen Trade-offs

| Choice | Benefit | Cost |
|--------|---------|------|
| SQLite | Simple, no setup | Single machine only |
| Multiprocessing | True parallelism | Higher memory |
| Polling | Simple, reliable | 1-second latency |
| No job priorities | Simple queue | No urgency handling |
| File storage | Persistent | Not distributed |

### Known Limitations

1. **Single Machine**: Cannot distribute across servers
2. **No Priorities**: FIFO only
3. **No Scheduling**: Cannot delay jobs to specific time
4. **No Dependencies**: Jobs are independent
5. **Basic Logging**: No structured logs or metrics
6. **No Authentication**: Filesystem-based security only

## Future Improvements

### Short-term

1. **Job timeout handling**: Kill long-running jobs
2. **Priority queues**: Urgent jobs first
3. **Job output logging**: Store stdout/stderr
4. **Better monitoring**: Prometheus metrics

### Long-term

1. **Distributed mode**: Redis/PostgreSQL backend
2. **Web dashboard**: Real-time monitoring UI
3. **Job dependencies**: DAG execution
4. **Scheduled jobs**: Cron-like functionality
5. **Webhooks**: Notify on completion
6. **Rate limiting**: Throttle job execution

## Testing Strategy

### Unit Tests

- Test each component in isolation
- Mock database for fast execution
- Cover edge cases (empty queue, max retries, etc.)

### Integration Tests

- Test full job lifecycle
- Multi-worker scenarios
- Persistence across restarts
- Retry and DLQ workflows

### Manual Testing

- Demo script for quick validation
- Real commands (echo, sleep, etc.)
- Error scenarios (invalid commands)

## Deployment Considerations

### Installation

```bash
pip install -e .  # Development
pip install .     # Production
```

### Data Location

- Database: `~/.queuectl/queuectl.db`
- No external configuration needed

### Monitoring in Production

```bash
# Check system health
queuectl status

# Monitor job processing
watch -n 5 queuectl status

# Check for failed jobs
queuectl list --state failed
queuectl dlq list
```

### Backup & Recovery

```bash
# Backup database
cp ~/.queuectl/queuectl.db backup.db

# Restore
cp backup.db ~/.queuectl/queuectl.db
```

## Conclusion

QueueCTL is designed as a learning-focused, production-ready job queue system that balances simplicity with robustness. It demonstrates key concepts in distributed systems (locking, retries, persistence) while maintaining a clean, understandable codebase.

The architecture prioritizes:
1. **Reliability**: Persistent storage, automatic retries, graceful failures
2. **Simplicity**: SQLite, standard libraries, minimal dependencies
3. **Clarity**: Clean code structure, comprehensive documentation
4. **Testability**: Unit and integration tests, demo scripts

For high-scale production use, consider more robust solutions (Celery, RabbitMQ, Redis Queue), but QueueCTL serves as an excellent foundation for understanding job queue mechanics.