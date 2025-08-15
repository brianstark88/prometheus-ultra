#!/bin/bash
set -e

echo "🚀 Starting GOD-MODE Agent v3.2 ULTRA"
echo "====================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Check if already running
if [ -f ".backend.pid" ] && kill -0 $(cat .backend.pid) 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Backend already running (PID: $(cat .backend.pid))${NC}"
    BACKEND_RUNNING=true
else
    BACKEND_RUNNING=false
fi

if [ -f ".frontend.pid" ] && kill -0 $(cat .frontend.pid) 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Frontend already running (PID: $(cat .frontend.pid))${NC}"
    FRONTEND_RUNNING=true
else
    FRONTEND_RUNNING=false
fi

# If both are running, just open browser
if [ "$BACKEND_RUNNING" = true ] && [ "$FRONTEND_RUNNING" = true ]; then
    echo -e "${GREEN}✅ Both services already running!${NC}"
    echo -e "${BLUE}🌐 Opening browser...${NC}"
    open "http://127.0.0.1:5173"
    exit 0
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Virtual environment not found. Run dev_bootstrap.sh first.${NC}"
    exit 1
fi

# Check if UI dependencies are installed
if [ ! -d "ui/node_modules" ]; then
    echo -e "${RED}❌ UI dependencies not found. Run dev_bootstrap.sh first.${NC}"
    exit 1
fi

# Check if Ollama is running
if ! pgrep -f "ollama serve" > /dev/null; then
    echo -e "${YELLOW}⚠️  Starting Ollama service...${NC}"
    ollama serve &
    sleep 3
fi

# Start backend if not running
if [ "$BACKEND_RUNNING" = false ]; then
    echo -e "${BLUE}🔥 Starting backend server...${NC}"
    
    # Activate virtual environment and start backend
    source venv/bin/activate
    nohup uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload > logs/backend.log 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > .backend.pid
    
    # Wait for backend to be ready
    echo -e "${YELLOW}⏳ Waiting for backend to start...${NC}"
    for i in {1..30}; do
        if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Backend ready!${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}❌ Backend failed to start within 30 seconds${NC}"
            cat logs/backend.log
            exit 1
        fi
        sleep 1
    done
fi

# Start frontend if not running
if [ "$FRONTEND_RUNNING" = false ]; then
    echo -e "${BLUE}🎨 Starting frontend server...${NC}"
    
    cd ui
    nohup npm run dev > ../logs/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > ../.frontend.pid
    cd ..
    
    # Wait for frontend to be ready
    echo -e "${YELLOW}⏳ Waiting for frontend to start...${NC}"
    for i in {1..20}; do
        if curl -s http://127.0.0.1:5173 > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Frontend ready!${NC}"
            break
        fi
        if [ $i -eq 20 ]; then
            echo -e "${YELLOW}⚠️  Frontend may still be starting...${NC}"
            break
        fi
        sleep 1
    done
fi

# Create logs directory if it doesn't exist
mkdir -p logs

echo ""
echo -e "${GREEN}🎉 GOD-MODE Agent is running!${NC}"
echo "==============================="
echo -e "${BLUE}🌐 Frontend:${NC} http://127.0.0.1:5173"
echo -e "${BLUE}🔧 Backend:${NC}  http://127.0.0.1:8000"
echo -e "${BLUE}📊 Health:${NC}   http://127.0.0.1:8000/health"
echo ""
echo -e "${YELLOW}📋 Process IDs:${NC}"
if [ -f ".backend.pid" ]; then
    echo -e "  Backend:  $(cat .backend.pid)"
fi
if [ -f ".frontend.pid" ]; then
    echo -e "  Frontend: $(cat .frontend.pid)"
fi
echo ""
echo -e "${YELLOW}📝 Logs:${NC}"
echo "  Backend:  logs/backend.log"
echo "  Frontend: logs/frontend.log"
echo ""
echo -e "${BLUE}🛑 To stop:${NC} ./scripts/stop.sh"

# Open browser after a short delay
echo -e "${BLUE}🌐 Opening browser in 3 seconds...${NC}"
sleep 3
open "http://127.0.0.1:5173"

echo -e "${GREEN}✨ Ready for GOD-MODE! 🧠⚡${NC}"