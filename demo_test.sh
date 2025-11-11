# Demo test script for QueueCTL = This script demonstrates all the core functionality

set -e

echo "========================================="
echo "QueueCTL Demo Test Script"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Cleanup function
cleanup_db() {
    print_warning "Cleaning up old database..."
    rm -rf ~/.queuectl/queuectl.db
    print_success "Database cleaned"
    echo ""
}

# Check if user wants to clean database
if [ -f ~/.queuectl/queuectl.db ]; then
    print_warning "Database already exists. Cleaning up for fresh demo..."
    cleanup_db
fi

# Test 1: Basic job completion
print_test "Test 1: Basic job completes successfully"
queuectl enqueue '{"id":"job-success","command":"echo Hello World"}'
queuectl status
sleep 1
print_success "Basic job enqueued"
echo ""

# Test 2: Failed job with retries
print_test "Test 2: Failed job retries with backoff"
queuectl enqueue '{"id":"job-fail","command":"exit 1","max_retries":3}'
print_success "Failed job enqueued"
echo ""

# Test 3: Invalid command
print_test "Test 3: Invalid command fails gracefully"
queuectl enqueue '{"id":"job-invalid","command":"nonexistentcommand123","max_retries":2}'
print_success "Invalid command job enqueued"
echo ""

# Test 4: Multiple jobs
print_test "Test 4: Enqueue multiple jobs"
queuectl enqueue '{"id":"job-multi-1","command":"sleep 1 && echo Job 1"}'
queuectl enqueue '{"id":"job-multi-2","command":"sleep 1 && echo Job 2"}'
queuectl enqueue '{"id":"job-multi-3","command":"sleep 1 && echo Job 3"}'
print_success "Multiple jobs enqueued"
echo ""

# Test 5: Configuration
print_test "Test 5: Configuration management"
queuectl config get
queuectl config set max-retries 5
queuectl config set backoff-base 3
queuectl config get
print_success "Configuration updated"
echo ""

# Test 6: List jobs
print_test "Test 6: List jobs by state"
queuectl list --state pending
print_success "Listed pending jobs"
echo ""

# Test 7: Status check
print_test "Test 7: Check system status"
queuectl status
print_success "Status retrieved"
echo ""

echo "========================================="
echo "Starting worker to process jobs..."
echo "========================================="
echo ""
echo "Run in another terminal:"
echo "  queuectl worker start --count 3"
echo ""
echo "Then monitor with:"
echo "  queuectl status"
echo "  queuectl list --state completed"
echo "  queuectl dlq list"
echo ""
echo "After jobs are processed, check DLQ:"
echo "  queuectl dlq list"
echo "  queuectl dlq retry job-fail"
echo ""
echo "Demo setup complete!"