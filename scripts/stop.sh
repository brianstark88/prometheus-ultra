#!/bin/bash

echo "🛑 Stopping GOD-MODE Agent v3.2 ULTRA"
echo "======================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

STOPPED_SOMETHING=false

# Stop backend
if [ -f ".backend.pid" ]; then
    BACKEND_PID=$(cat .backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${YELLOW}🔥 Stopping backend server (PID: $BACKEND_PID)...${NC}"
        kill $BACKEND_PID
        
        # Wait for graceful shutdown
        for i in {1..10}; do
            if ! kill -0 $BACKEND_PID 2>/dev/null; then
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if kill -0 $BACKEND_PID 2>/dev/null; then
            echo -e "${YELLOW}⚡ Force stopping backend...${NC}"
            kill -9 $BACKEND_PID 2>/dev/null || true
        fi
        
        echo -e "${GREEN}✅ Backend stopped${NC}"
        STOPPED_SOMETHING=true
    else
        echo -e "${YELLOW}⚠️  Backend PID file exists but process not running${NC}"
    fi
    rm .backend.pid
else
    echo -e "${BLUE}ℹ️  No backend PID file found${NC}"
fi

# Stop frontend
if [ -f ".frontend.pid" ]; then
    FRONTEND_PID=$(cat .frontend.pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${YELLOW}🎨 Stopping frontend server (PID: $FRONTEND_PID)...${NC}"
        kill $FRONTEND_PID
        
        # Wait for graceful shutdown
        for i in {1..10}; do
            if ! kill -0 $FRONTEND_PID 2>/dev/null; then
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if kill -0 $FRONTEND_PID 2>/dev/null; then
            echo -e "${YELLOW}⚡ Force stopping frontend...${NC}"
            kill -9 $FRONTEND_PID 2>/dev/null || true
        fi
        
        echo -e "${GREEN}✅ Frontend stopped${NC}"
        STOPPED_SOMETHING=true
    else
        echo -e "${YELLOW}⚠️  Frontend PID file exists but process not running${NC}"
    fi
    rm .frontend.pid
else
    echo -e "${BLUE}ℹ️  No frontend PID file found${NC}"
fi

# Stop any remaining uvicorn processes
echo -e "${BLUE}🔍 Checking for remaining uvicorn processes...${NC}"
UVICORN_PIDS=$(pgrep -f "uvicorn.*api.app:app" || true)
if [ ! -z "$UVICORN_PIDS" ]; then
    echo -e "${YELLOW}🔥 Stopping remaining uvicorn processes...${NC}"
    echo "$UVICORN_PIDS" | xargs kill 2>/dev/null || true
    sleep 2
    # Force kill if needed
    UVICORN_PIDS=$(pgrep -f "uvicorn.*api.app:app" || true)
    if [ ! -z "$UVICORN_PIDS" ]; then
        echo "$UVICORN_PIDS" | xargs kill -9 2>/dev/null || true
    fi
    echo -e "${GREEN}✅ Remaining uvicorn processes stopped${NC}"
    STOPPED_SOMETHING=true
fi

# Stop any remaining npm dev processes
echo -e "${BLUE}🔍 Checking for remaining npm dev processes...${NC}"
NPM_PIDS=$(pgrep -f "npm.*run.*dev" || true)
if [ ! -z "$NPM_PIDS" ]; then
    echo -e "${YELLOW}🎨 Stopping remaining npm dev processes...${NC}"
    echo "$NPM_PIDS" | xargs kill 2>/dev/null || true
    sleep 2
    # Force kill if needed
    NPM_PIDS=$(pgrep -f "npm.*run.*dev" || true)
    if [ ! -z "$NPM_PIDS" ]; then
        echo "$NPM_PIDS" | xargs kill -9 2>/dev/null || true
    fi
    echo -e "${GREEN}✅ Remaining npm processes stopped${NC}"
    STOPPED_SOMETHING=true
fi

# Optional: Stop Ollama (commented out by default since it might be used by other apps)
# echo -e "${BLUE}🤖 Ollama service:${NC}"
# if pgrep -f "ollama serve" > /dev/null; then
#     read -p "Stop Ollama service too? (y/N): " -n 1 -r
#     echo
#     if [[ $REPLY =~ ^[Yy]$ ]]; then
#         echo -e "${YELLOW}🤖 Stopping Ollama service...${NC}"
#         pkill -f "ollama serve" || true
#         echo -e "${GREEN}✅ Ollama stopped${NC}"
#         STOPPED_SOMETHING=true
#     else
#         echo -e "${BLUE}ℹ️  Ollama service left running${NC}"
#     fi
# else
#     echo -e "${BLUE}ℹ️  Ollama service not running${NC}"
# fi

# Clean up any stale lock files
if [ -f "ui/.vite/deps/.lock" ]; then
    rm ui/.vite/deps/.lock
fi

echo ""
if [ "$STOPPED_SOMETHING" = true ]; then
    echo -e "${GREEN}🎉 GOD-MODE Agent stopped successfully!${NC}"
    echo ""
    echo -e "${BLUE}📝 Log files preserved:${NC}"
    if [ -f "logs/backend.log" ]; then
        echo "  Backend:  logs/backend.log"
    fi
    if [ -f "logs/frontend.log" ]; then
        echo "  Frontend: logs/frontend.log"
    fi
else
    echo -e "${BLUE}ℹ️  No running processes found${NC}"
fi

echo ""
echo -e "${BLUE}🚀 To restart:${NC} ./scripts/start.sh"
echo -e "${GREEN}✨ GOD-MODE shutdown complete! 🧠⚡${NC}"