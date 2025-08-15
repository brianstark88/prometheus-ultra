#!/bin/bash
set -e

echo "🚀 GOD-MODE Agent v3.2 ULTRA - Development Bootstrap"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}❌ This script is designed for macOS. Exiting.${NC}"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python 3.11
echo -e "${BLUE}🔍 Checking Python 3.11...${NC}"
if ! command_exists python3.11; then
    echo -e "${RED}❌ Python 3.11 not found. Please install it first.${NC}"
    echo "   brew install python@3.11"
    exit 1
fi
echo -e "${GREEN}✅ Python 3.11 found${NC}"

# Check/Install Ollama
echo -e "${BLUE}🔍 Checking Ollama...${NC}"
if ! command_exists ollama; then
    echo -e "${YELLOW}⚠️  Ollama not found. Installing...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo -e "${GREEN}✅ Ollama found${NC}"
fi

# Start Ollama service
echo -e "${BLUE}🚀 Starting Ollama service...${NC}"
if ! pgrep -f "ollama serve" > /dev/null; then
    ollama serve &
    sleep 3
    echo -e "${GREEN}✅ Ollama service started${NC}"
else
    echo -e "${GREEN}✅ Ollama service already running${NC}"
fi

# Pull primary model
echo -e "${BLUE}📦 Pulling gpt-oss:20b model...${NC}"
if ! ollama list | grep -q "gpt-oss:20b"; then
    echo -e "${YELLOW}⚠️  Model not found. This may take a while...${NC}"
    ollama pull gpt-oss:20b
    echo -e "${GREEN}✅ Model pulled successfully${NC}"
else
    echo -e "${GREEN}✅ Model already available${NC}"
fi

# Pull fallback models
echo -e "${BLUE}📦 Pulling fallback models...${NC}"
for model in "llama2:7b" "mistral:7b"; do
    if ! ollama list | grep -q "$model"; then
        echo -e "${YELLOW}⚠️  Pulling $model...${NC}"
        ollama pull "$model" || echo -e "${YELLOW}⚠️  Failed to pull $model (optional)${NC}"
    else
        echo -e "${GREEN}✅ $model already available${NC}"
    fi
done

# Check Node.js
echo -e "${BLUE}🔍 Checking Node.js...${NC}"
if ! command_exists node || ! command_exists npm; then
    echo -e "${RED}❌ Node.js/npm not found. Please install it first.${NC}"
    echo "   brew install node"
    exit 1
fi
echo -e "${GREEN}✅ Node.js found: $(node --version)${NC}"

# Setup Python environment
echo -e "${BLUE}🐍 Setting up Python environment...${NC}"
if [ ! -d "venv" ]; then
    python3.11 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${GREEN}✅ Virtual environment exists${NC}"
fi

# Activate virtual environment and install dependencies
source venv/bin/activate
echo -e "${BLUE}📦 Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✅ Python dependencies installed${NC}"

# Setup environment file
if [ ! -f ".env" ]; then
    echo -e "${BLUE}⚙️  Creating .env file...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✅ .env file created${NC}"
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Setup UI
echo -e "${BLUE}🎨 Setting up UI...${NC}"
cd ui

if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}📦 Installing UI dependencies...${NC}"
    npm install
    echo -e "${GREEN}✅ UI dependencies installed${NC}"
else
    echo -e "${GREEN}✅ UI dependencies already installed${NC}"
fi

cd ..

# Create necessary directories
echo -e "${BLUE}📁 Creating directories...${NC}"
mkdir -p dashboards/grafana
mkdir -p .ultra
echo -e "${GREEN}✅ Directories created${NC}"

# Start backend
echo -e "${BLUE}🔥 Starting backend server...${NC}"
source venv/bin/activate
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
sleep 3

# Check if backend is running
if curl -s http://127.0.0.1:8000/health > /dev/null; then
    echo -e "${GREEN}✅ Backend server started on port 8000${NC}"
else
    echo -e "${RED}❌ Backend server failed to start${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

# Start frontend
echo -e "${BLUE}🎨 Starting frontend server...${NC}"
cd ui
npm run dev &
FRONTEND_PID=$!
sleep 3
cd ..

# Check if frontend is running
if curl -s http://127.0.0.1:5173 > /dev/null; then
    echo -e "${GREEN}✅ Frontend server started on port 5173${NC}"
else
    echo -e "${YELLOW}⚠️  Frontend server may still be starting...${NC}"
fi

# Save PIDs for cleanup
echo $BACKEND_PID > .backend.pid
echo $FRONTEND_PID > .frontend.pid

# Final instructions
echo ""
echo -e "${GREEN}🎉 GOD-MODE Agent is now running!${NC}"
echo "==============================================="
echo -e "${BLUE}🌐 Frontend:${NC} http://127.0.0.1:5173"
echo -e "${BLUE}🔧 Backend:${NC}  http://127.0.0.1:8000"
echo -e "${BLUE}📊 Health:${NC}   http://127.0.0.1:8000/health"
echo ""
echo -e "${YELLOW}💡 Quick Setup Tips:${NC}"
echo "• Set backend URL in UI settings to: http://127.0.0.1:8000"
echo "• Try asking: 'Count files in my home directory'"
echo "• Check the Thinking Panel for live agent reasoning"
echo "• Use Ctrl+C to stop the servers"
echo ""
echo -e "${BLUE}🧪 Run tests with:${NC}"
echo "  ./scripts/smoke_tests.sh"
echo ""
echo -e "${GREEN}Ready for GOD-MODE! 🧠⚡${NC}"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down servers...${NC}"
    if [ -f .backend.pid ]; then
        kill $(cat .backend.pid) 2>/dev/null || true
        rm .backend.pid
    fi
    if [ -f .frontend.pid ]; then
        kill $(cat .frontend.pid) 2>/dev/null || true
        rm .frontend.pid
    fi
    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

# Set trap to cleanup on script exit
trap cleanup EXIT

# Keep script running
echo -e "${BLUE}📡 Monitoring servers... Press Ctrl+C to stop.${NC}"
wait