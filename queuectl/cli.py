# CLI interface for QueueCTL
import click
import json
import sys
from tabulate import tabulate
from .database import Database
from .config import Config
from .queue import Queue
from .models import Job, JobState
from .worker import start_workers
from .utils import format_job_for_display


# Initialize core components
db = Database()
config = Config(db)
queue = Queue(db, config)


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """
    QueueCTL - A CLI-based background job queue system
    
    Manage background jobs with worker processes, automatic retries, and a Dead Letter Queue for permanently failed jobs.
    """
    pass

@cli.command()
@click.argument('job_data')
def enqueue(job_data):
    try:
        # Parse JSON data
        data = json.loads(job_data)
        
        # Validate required fields
        if 'id' not in data or 'command' not in data:
            click.echo("Error: Job must have 'id' and 'command' fields", err=True)
            sys.exit(1)
        
        # Create job
        job = Job.from_dict(data)
        
        # Enqueue
        if queue.enqueue(job):
            click.echo(f"✓ Job '{job.id}' enqueued successfully")
            click.echo(f"  Command: {job.command}")
            click.echo(f"  Max retries: {job.max_retries}")
        else:
            click.echo(f"Error: Job '{job.id}' already exists", err=True)
            sys.exit(1)
    
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON - {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

@cli.group()
def worker():
    pass

@worker.command()
@click.option('--count', '-c', default=1, help='Number of workers to start')
def start(count):
    click.echo(f"Starting {count} worker(s)...")
    try:
        start_workers(count)
    except KeyboardInterrupt:
        click.echo("\nWorkers stopped")

@worker.command()
def stop():
    click.echo("To stop workers, use Ctrl+C in the worker terminal")
    click.echo("Workers will finish their current jobs before stopping")


@cli.command()
def status():
    status_data = queue.get_status()
    
    click.echo("\n=== Queue Status ===\n")
    
    # Job counts
    click.echo("Jobs by State:")
    job_table = []
    for state, count in status_data['jobs'].items():
        job_table.append([state.upper(), count])
    click.echo(tabulate(job_table, headers=['State', 'Count'], tablefmt='simple'))
    
    # Workers
    click.echo(f"\nActive Workers: {status_data['workers']['active']}")
    if status_data['workers']['details']:
        worker_table = []
        for w in status_data['workers']['details']:
            worker_table.append([
                w['worker_id'],
                w['started_at'].split('T')[1].split('.')[0],
                w['status']
            ])
        click.echo(tabulate(worker_table, headers=['Worker ID', 'Started At', 'Status'], tablefmt='simple'))
    
    # Config
    click.echo("\nConfiguration:")
    config_table = [
        ['Max Retries', status_data['config']['max_retries']],
        ['Backoff Base', status_data['config']['backoff_base']]
    ]
    click.echo(tabulate(config_table, headers=['Setting', 'Value'], tablefmt='simple'))
    click.echo()

@cli.command()
@click.option('--state', '-s', help='Filter by state (pending, processing, completed, failed, dead)')
@click.option('--limit', '-l', default=20, help='Maximum number of jobs to display')
def list(state, limit):
    # Validate state
    if state and state not in [s.value for s in JobState]:
        click.echo(f"Error: Invalid state '{state}'", err=True)
        click.echo(f"Valid states: {', '.join([s.value for s in JobState])}")
        sys.exit(1)
    
    jobs = queue.list_jobs(state)
    
    if not jobs:
        if state:
            click.echo(f"No jobs found with state '{state}'")
        else:
            click.echo("No jobs found")
        return
    
    # Limit results
    jobs = jobs[:limit]
    
    # Format for display
    table_data = [format_job_for_display(job) for job in jobs]
    
    click.echo(f"\n=== Jobs {'(' + state.upper() + ')' if state else ''} ===\n")
    click.echo(tabulate(table_data, headers='keys', tablefmt='grid'))
    
    if len(jobs) == limit:
        click.echo(f"\nShowing first {limit} jobs. Use --limit to see more.")


@cli.group()
def dlq():
    pass


@dlq.command('list')
@click.option('--limit', '-l', default=20, help='Maximum number of jobs to display')
def dlq_list(limit):
    jobs = queue.list_dlq_jobs()
    
    if not jobs:
        click.echo("Dead Letter Queue is empty")
        return
    
    # Limit results
    jobs = jobs[:limit]
    
    # Format for display
    table_data = [format_job_for_display(job) for job in jobs]
    
    click.echo("\n=== Dead Letter Queue ===\n")
    click.echo(tabulate(table_data, headers='keys', tablefmt='grid'))
    
    if len(jobs) == limit:
        click.echo(f"\nShowing first {limit} jobs. Use --limit to see more.")


@dlq.command('retry')
@click.argument('job_id')
def dlq_retry(job_id):
    job = queue.get_job(job_id)
    
    if not job:
        click.echo(f"Error: Job '{job_id}' not found", err=True)
        sys.exit(1)
    
    if job.state != JobState.DEAD.value:
        click.echo(f"Error: Job '{job_id}' is not in DLQ (current state: {job.state})", err=True)
        sys.exit(1)
    
    if queue.retry_dlq_job(job_id):
        click.echo(f"✓ Job '{job_id}' moved back to queue for retry")
    else:
        click.echo(f"Error: Failed to retry job '{job_id}'", err=True)
        sys.exit(1)


@cli.group()
def config_cmd():
    pass


@config_cmd.command('set')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    key = key.replace('-', '_')
    
    if key == 'max_retries':
        try:
            val = int(value)
            if val < 0:
                raise ValueError("Must be non-negative")
            config.set_max_retries(val)
            click.echo(f"✓ Set max_retries to {val}")
        except ValueError as e:
            click.echo(f"Error: Invalid value for max-retries - {e}", err=True)
            sys.exit(1)
    
    elif key == 'backoff_base':
        try:
            val = int(value)
            if val < 1:
                raise ValueError("Must be at least 1")
            config.set_backoff_base(val)
            click.echo(f"✓ Set backoff_base to {val}")
        except ValueError as e:
            click.echo(f"Error: Invalid value for backoff-base - {e}", err=True)
            sys.exit(1)
    
    else:
        click.echo(f"Error: Unknown configuration key '{key}'", err=True)
        click.echo("Valid keys: max-retries, backoff-base")
        sys.exit(1)


@config_cmd.command('get')
@click.argument('key', required=False)
def config_get(key):
    if key:
        key = key.replace('-', '_')
        
        if key == 'max_retries':
            click.echo(f"max_retries: {config.get_max_retries()}")
        elif key == 'backoff_base':
            click.echo(f"backoff_base: {config.get_backoff_base()}")
        else:
            click.echo(f"Error: Unknown configuration key '{key}'", err=True)
            sys.exit(1)
    else:
        # Show all config
        all_config = config.get_all()
        click.echo("\n=== Configuration ===\n")
        for k, v in all_config.items():
            click.echo(f"{k}: {v}")


@cli.command()
@click.option('--force', '-f', is_flag=True, help='Force cleanup without confirmation')
def cleanup(force):
    if not force:
        click.confirm('This will delete ALL jobs and reset the database. Continue?', abort=True)
    
    import os
    db_path = os.path.join(os.path.expanduser("~"), ".queuectl", "queuectl.db")
    
    if os.path.exists(db_path):
        try:
            # Close existing connection
            db.close()
            
            # Remove database files
            os.remove(db_path)
            
            # Remove WAL files if they exist
            wal_path = db_path + "-wal"
            shm_path = db_path + "-shm"
            if os.path.exists(wal_path):
                os.remove(wal_path)
            if os.path.exists(shm_path):
                os.remove(shm_path)
            
            click.echo("✓ Database cleaned up successfully")
            click.echo(f"  Removed: {db_path}")
        except Exception as e:
            click.echo(f"Error cleaning up database: {e}", err=True)
            sys.exit(1)
    else:
        click.echo("No database found to clean up")


def main():
    import multiprocessing
    if sys.platform == 'win32':
        multiprocessing.freeze_support()
    cli()

if __name__ == '__main__':
    main()