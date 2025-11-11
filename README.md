# QueueCTL - CLI-Based Background Job Queue System

A production-grade, CLI-based job queue system with worker processes, automatic retries using exponential backoff, and a Dead Letter Queue (DLQ) for permanently failed jobs.

## Features

- ✅ **CLI Interface** - Simple, intuitive command-line interface
- ✅ **Persistent Storage** - SQLite-based job storage that survives restarts
- ✅ **Multiple Workers** - Run concurrent worker processes for parallel job execution
- ✅ **Automatic Retries** - Exponential backoff retry mechanism
- ✅ **Dead Letter Queue** - Isolate permanently failed jobs
- ✅ **Job Locking** - Prevent duplicate job processing across workers
- ✅ **Graceful Shutdown** - Workers finish current jobs before exiting
- ✅ **Configuration Management** - Customizable retry and backoff settings
- ✅ **State Tracking** - Monitor job lifecycle (pending → processing → completed/failed/dead)

## Installation
### Prerequisites
- Python 3.7 or higher
- pip (Python package manager)

### Quick Install
# Clone the repository
git clone https://github.com/Lasyapriya-B14/queuectl.git
cd queuectl

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .

# Verify installation
queuectl --version


## Quick Start
### 1. Enqueue a Job
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'

### 2. Start Workers
# Start 3 worker processes
queuectl worker start --count 3

### 3. Check Status
queuectl status

### 4. List Jobs
# List all jobs
queuectl list

# List by state
queuectl list --state pending
queuectl list --state completed


## Usage Examples
### Enqueuing Jobs

# Simple job
queuectl enqueue '{"id":"job1","command":"echo Hello"}'

# Job with custom retries
queuectl enqueue '{"id":"job2","command":"sleep 5","max_retries":5}'

# Job that will fail
queuectl enqueue '{"id":"job3","command":"exit 1"}'

# Complex command
queuectl enqueue '{"id":"job4","command":"python script.py --arg value"}'


### Worker Management
# Start single worker
queuectl worker start

# Start multiple workers
queuectl worker start --count 5

# Stop workers (send Ctrl+C to worker terminal)
# Workers will finish current jobs before stopping


### Monitoring
# View overall status
queuectl status

# List all jobs
queuectl list

# Filter by state
queuectl list --state pending
queuectl list --state processing
queuectl list --state completed
queuectl list --state failed
queuectl list --state dead

# Limit results
queuectl list --limit 10


### Dead Letter Queue (DLQ)
# List jobs in DLQ
queuectl dlq list

# Retry a failed job
queuectl dlq retry job1

# After retry, the job goes back to pending state


### Configuration
# View all configuration
queuectl config get

# View specific setting
queuectl config get max-retries

# Set max retries
queuectl config set max-retries 5

# Set backoff base (for exponential backoff: base^attempts)
queuectl config set backoff-base 3


## CLI Commands Reference

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `enqueue` | Add job to queue | `queuectl enqueue '{"id":"j1","command":"echo hi"}'` |
| `worker start` | Start worker(s) | `queuectl worker start --count 3` |
| `worker stop` | Stop workers | Send `Ctrl+C` to worker process |
| `status` | Show queue status | `queuectl status` |
| `list` | List jobs | `queuectl list --state pending` |
| `dlq list` | View DLQ jobs | `queuectl dlq list` |
| `dlq retry` | Retry DLQ job | `queuectl dlq retry job1` |
| `config get` | View config | `queuectl config get max-retries` |
| `config set` | Set config | `queuectl config set max-retries 5` |

### Job Data Format

json
{
  "id": "unique-job-id",           // Required: Unique identifier
  "command": "echo 'Hello'",       // Required: Shell command to execute
  "state": "pending",              // Auto-set: Job state
  "attempts": 0,                   // Auto-set: Retry attempts
  "max_retries": 3,                // Optional: Override default retries
  "created_at": "2025-11-04T...",  // Auto-set: Creation timestamp
  "updated_at": "2025-11-04T..."   // Auto-set: Last update timestamp
}


## Architecture Overview

### Components


┌─────────────┐
│     CLI     │  User interface (Click-based)
└──────┬──────┘
       │
┌──────▼──────┐
│    Queue    │  Job management & orchestration
└──────┬──────┘
       │
┌──────▼──────┐
│  Database   │  SQLite persistence layer
└─────────────┘
       │
┌──────▼──────┐
│   Workers   │  Job execution processes
└─────────────┘


### Job Lifecycle


┌─────────┐
│ PENDING │──────┐
└────┬────┘      │
     │           │
     ▼           │
┌────────────┐   │
│ PROCESSING │   │
└─────┬──────┘   │
      │          │
      ├──────────┼─────► Success ──► COMPLETED
      │          │
      └──────────┼─────► Failure ──► FAILED ──► Retry
                 │                      │
                 │                      │ (max retries exceeded)
                 │                      ▼
                 └─────────────────► DEAD (DLQ)


### Data Persistence

- **Storage**: SQLite database at `~/.queuectl/queuectl.db`
- **Tables**:
  - `jobs` - Job data and state
  - `workers` - Active worker tracking
  - `config` - System configuration

### Worker Mechanism

1. **Job Locking**: Workers acquire locks on jobs to prevent duplicate processing
2. **Heartbeat**: Workers update heartbeat every second
3. **Graceful Shutdown**: SIGINT/SIGTERM handlers allow current job completion
4. **Parallel Execution**: Multiple workers process jobs concurrently

### Retry & Backoff

- **Strategy**: Exponential backoff
- **Formula**: `delay = base ^ attempts` seconds
- **Default**: Base=2, Max Retries=3
- **Example**: Attempt 1: 2s, Attempt 2: 4s, Attempt 3: 8s
- **After max retries**: Job moves to DLQ

## Testing

### Run Unit Tests
# Install test dependencies
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_basic.py -v


### Run Demo Script
# Make script executable
chmod +x demo_test.sh

# Run demo
./demo_test.sh


### Manual Testing Scenarios

#### Test 1: Basic Job Success
# Terminal 1: Start worker
queuectl worker start
# Terminal 2: Enqueue job
queuectl enqueue '{"id":"test1","command":"echo Success"}'
# Verify completion
queuectl list --state completed


#### Test 2: Failed Job Retry
# Enqueue failing job
queuectl enqueue '{"id":"test2","command":"exit 1","max_retries":3}'
# Watch it retry (check attempts in status)
queuectl status
# Eventually moves to DLQ
queuectl dlq list


#### Test 3: Multiple Workers
# Start 3 workers
queuectl worker start --count 3
# Enqueue multiple jobs
for i in {1..10}; do
  queuectl enqueue "{\"id\":\"job$i\",\"command\":\"sleep 2 && echo Job $i\"}"
done
# Watch parallel processing
watch -n 1 queuectl status


#### Test 4: Persistence
# Enqueue jobs
queuectl enqueue '{"id":"persist1","command":"echo Test"}'
queuectl list
# Stop everything (Ctrl+C workers)
# Restart worker
queuectl worker start
# Jobs are still there!
queuectl list


#### Test 5: Invalid Command
queuectl enqueue '{"id":"invalid","command":"notarealcommand"}'
# Worker will handle gracefully and retry
queuectl list --state failed


## Design Decisions & Trade-offs

### Technology Choices

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| **Python** | Rich ecosystem, easy CLI tools | Slower than Go/Rust |
| **SQLite** | Zero-config, embedded, ACID | Not for high-scale distributed systems |
| **Click** | Professional CLI framework | Extra dependency |
| **Multiprocessing** | True parallelism | More memory than threading |

### Architecture Decisions

1. **File-based Locking via SQLite**: Simple, reliable, no external dependencies
   - Trade-off: Limited to single machine

2. **Exponential Backoff**: Reduces load on failing systems
   - Trade-off: Failed jobs take longer to move to DLQ

3. **Worker Heartbeat**: Detect dead workers, prevent lock starvation
   - Trade-off: Small overhead per worker

4. **Command Execution via subprocess**: Secure, isolated
   - Trade-off: Cannot execute Python functions directly

### Assumptions

- Jobs are shell commands (not Python functions)
- Single machine deployment (not distributed)
- Jobs complete within 5 minutes (timeout)
- Low-to-medium throughput (< 1000 jobs/min)
- Workers are trusted (no sandbox)

### Simplifications

- No job priorities
- No scheduled jobs (run_at)
- No job dependencies
- No worker pools (manual start/stop)
- Basic error messages (no detailed logs)

## Project Structure


queuectl/
├── queuectl/
│   ├── __init__.py       # Package initialization
│   ├── cli.py            # CLI interface (Click)
│   ├── models.py         # Job data models
│   ├── database.py       # SQLite operations
│   ├── queue.py          # Queue management
│   ├── worker.py         # Worker implementation
│   ├── config.py         # Configuration
│   └── utils.py          # Utilities (backoff, exec)
├── tests/
│   ├── test_basic.py     # Unit tests
│   └── test_scenarios.py # Integration tests
├── requirements.txt      # Dependencies
├── setup.py              # Package setup
├── README.md             # This file
├── demo_test.sh          # Demo script
└── .gitignore            # Git ignore rules


##  Configuration
### Files

- **Database**: `~/.queuectl/queuectl.db`
- **No config file needed**: All config stored in database

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `max_retries` | 3 | Maximum retry attempts before DLQ |
| `backoff_base` | 2 | Base for exponential backoff |

##  Troubleshooting
### Jobs not processing
# Check if workers are running
queuectl status

# Check job state
queuectl list --state pending

# Start workers if none running
queuectl worker start --count 3


### Job stuck in processing
- Worker may have crashed
- Lock expires after 5 minutes automatically
- Job will be picked up by another worker

### Database locked errors
- Multiple workers are safe due to SQLite WAL mode
- If issues persist, check file permissions on `~/.queuectl/`

### Commands not found
# Ensure queuectl is installed
pip install -e .

# Verify installation
which queuectl


## Future Enhancements
- [ ] Job priorities
- [ ] Scheduled jobs (cron-like)
- [ ] Job dependencies
- [ ] Web dashboard
- [ ] Metrics & monitoring
- [ ] Job output logging
- [ ] Timeout handling
- [ ] Worker pools
- [ ] REST API

##  Development

### Setup Development Environment
# Clone repo
git clone https://github.com/yourusername/queuectl.git
cd queuectl

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Install dev dependencies
pip install pytest black flake8


### Code Style


# Format code
black queuectl/

# Lint
flake8 queuectl/


### Running Tests


pytest tests/ -v --cov=queuectl


## Support
For issues, questions, or contributions:
- Open an issue on GitHub
- Check existing issues first
- Include relevant error messages and steps to reproduce

---
