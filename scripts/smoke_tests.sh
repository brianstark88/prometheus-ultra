#!/bin/bash
set -e

echo "🧪 GOD-MODE Agent - Smoke Tests"
echo "==============================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BACKEND_URL="http://127.0.0.1:8000"
FRONTEND_URL="http://127.0.0.1:5173"

passed=0
failed=0

# Test function
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "${BLUE}🔄 Testing: $test_name${NC}"
    
    if eval "$test_command"; then
        echo -e "${GREEN}✅ PASS: $test_name${NC}"
        ((passed++))
    else
        echo -e "${RED}❌ FAIL: $test_name${NC}"
        ((failed++))
    fi
    echo ""
}

# Health check test
test_health() {
    local response=$(curl -s "$BACKEND_URL/health")
    echo "$response" | grep -q '"ok": *true'
}

# Tools endpoint test
test_tools() {
    local response=$(curl -s "$BACKEND_URL/tools")
    echo "$response" | grep -q '"count":'
}

# Metrics endpoint test
test_metrics() {
    local response=$(curl -s "$BACKEND_URL/metrics")
    echo "$response" | grep -q '"cpu_percent":'
}

# SSE stream test (basic connectivity)
test_sse_basic() {
    local url="$BACKEND_URL/auto/stream?goal=test%20connection"
    timeout 10s curl -s "$url" | head -n 5 | grep -q "event:"
}

# SSE stream test (count files)
test_sse_count_files() {
    local url="$BACKEND_URL/auto/stream?goal=Count%20files%20in%20~"
    timeout 30s curl -s "$url" | grep -q "final"
}

# Frontend accessibility
test_frontend() {
    curl -s "$FRONTEND_URL" | grep -q "GOD-MODE"
}

echo -e "${BLUE}🏁 Starting smoke tests...${NC}"
echo ""

# Backend tests
run_test "Backend Health Check" test_health
run_test "Tools API" test_tools
run_test "System Metrics API" test_metrics
run_test "SSE Basic Connectivity" test_sse_basic

# Comprehensive workflow test
echo -e "${YELLOW}🔬 Running comprehensive workflow test...${NC}"
run_test "File Count Workflow" test_sse_count_files

# Frontend test
run_test "Frontend Accessibility" test_frontend

# Summary
echo -e "${BLUE}📊 Test Results Summary${NC}"
echo "======================="
echo -e "${GREEN}✅ Passed: $passed${NC}"
echo -e "${RED}❌ Failed: $failed${NC}"
echo -e "Total: $((passed + failed))"

if [ $failed -eq 0 ]; then
    echo -e "\n${GREEN}🎉 All tests passed! GOD-MODE Agent is ready!${NC}"
    exit 0
else
    echo -e "\n${RED}⚠️  Some tests failed. Check the output above.${NC}"
    exit 1
fi