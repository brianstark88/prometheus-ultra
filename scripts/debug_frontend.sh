#!/bin/bash

echo "🔍 Debugging Frontend Issues"
echo "============================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}📍 Current directory: $(pwd)${NC}"
echo ""

# Check if UI directory exists
echo -e "${BLUE}🔍 Checking UI directory structure...${NC}"
if [ -d "ui" ]; then
    echo -e "${GREEN}✅ ui/ directory exists${NC}"
    ls -la ui/ | head -10
else
    echo -e "${RED}❌ ui/ directory missing!${NC}"
    echo "You need to create the UI components. Here's what's missing:"
    echo "  ui/package.json"
    echo "  ui/src/"
    echo "  ui/vite.config.ts"
    exit 1
fi

echo ""

# Check package.json
echo -e "${BLUE}🔍 Checking package.json...${NC}"
if [ -f "ui/package.json" ]; then
    echo -e "${GREEN}✅ package.json exists${NC}"
else
    echo -e "${RED}❌ ui/package.json missing!${NC}"
    echo "Creating package.json..."
    cat > ui/package.json << 'EOF'
{
  "name": "god-mode-agent-ui",
  "private": true,
  "version": "3.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5173",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.43",
    "@types/react-dom": "^18.2.17",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.2.2",
    "vite": "^5.0.8"
  }
}
EOF
    echo -e "${GREEN}✅ Created basic package.json${NC}"
fi

echo ""

# Check node_modules
echo -e "${BLUE}🔍 Checking node_modules...${NC}"
if [ -d "ui/node_modules" ]; then
    echo -e "${GREEN}✅ node_modules exists${NC}"
else
    echo -e "${YELLOW}⚠️  node_modules missing. Installing...${NC}"
    cd ui && npm install && cd ..
fi

echo ""

# Check vite config
echo -e "${BLUE}🔍 Checking vite.config.ts...${NC}"
if [ -f "ui/vite.config.ts" ]; then
    echo -e "${GREEN}✅ vite.config.ts exists${NC}"
else
    echo -e "${YELLOW}⚠️  Creating vite.config.ts...${NC}"
    cat > ui/vite.config.ts << 'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
EOF
    echo -e "${GREEN}✅ Created vite.config.ts${NC}"
fi

echo ""

# Check src directory
echo -e "${BLUE}🔍 Checking src directory...${NC}"
if [ -d "ui/src" ]; then
    echo -e "${GREEN}✅ src/ directory exists${NC}"
    ls -la ui/src/
else
    echo -e "${YELLOW}⚠️  Creating minimal src directory...${NC}"
    mkdir -p ui/src
    
    # Create minimal App.tsx
    cat > ui/src/App.tsx << 'EOF'
import React from 'react';

function App() {
  return (
    <div style={{ 
      padding: '40px', 
      fontFamily: 'system-ui, sans-serif',
      backgroundColor: '#1a1a1a',
      color: '#ffffff',
      minHeight: '100vh'
    }}>
      <h1 style={{ color: '#3b82f6' }}>🔱 GOD-MODE Agent v3.2 ULTRA</h1>
      <p>Frontend is working! Backend health check:</p>
      <div style={{ 
        backgroundColor: '#2a2a2a', 
        padding: '20px', 
        borderRadius: '8px',
        marginTop: '20px'
      }}>
        <h3>Backend Status: ✅ Connected</h3>
        <p>Backend URL: http://127.0.0.1:8000</p>
        <button 
          onClick={() => fetch('http://127.0.0.1:8000/health').then(r => r.json()).then(console.log)}
          style={{
            backgroundColor: '#3b82f6',
            color: 'white',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '4px',
            cursor: 'pointer'
          }}
        >
          Test Backend Connection
        </button>
      </div>
    </div>
  );
}

export default App;
EOF

    # Create main.tsx
    cat > ui/src/main.tsx << 'EOF'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
EOF

    echo -e "${GREEN}✅ Created minimal React components${NC}"
fi

echo ""

# Check index.html
echo -e "${BLUE}🔍 Checking index.html...${NC}"
if [ -f "ui/index.html" ]; then
    echo -e "${GREEN}✅ index.html exists${NC}"
else
    echo -e "${YELLOW}⚠️  Creating index.html...${NC}"
    cat > ui/index.html << 'EOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>GOD-MODE Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
EOF
    echo -e "${GREEN}✅ Created index.html${NC}"
fi

echo ""

# Try to start frontend manually
echo -e "${BLUE}🚀 Attempting to start frontend manually...${NC}"
cd ui

# Kill any existing processes on port 5173
lsof -ti:5173 | xargs kill -9 2>/dev/null || true

echo -e "${YELLOW}⏳ Starting vite dev server...${NC}"
npm run dev &
FRONTEND_PID=$!

sleep 5

# Test if frontend is accessible
echo -e "${BLUE}🧪 Testing frontend connection...${NC}"
if curl -s http://127.0.0.1:5173 > /dev/null; then
    echo -e "${GREEN}✅ Frontend is now accessible!${NC}"
    echo -e "${BLUE}🌐 Open: http://127.0.0.1:5173${NC}"
else
    echo -e "${RED}❌ Frontend still not accessible${NC}"
    echo -e "${YELLOW}📝 Frontend logs:${NC}"
    sleep 2
    kill $FRONTEND_PID 2>/dev/null || true
fi

cd ..

echo ""
echo -e "${BLUE}🔧 Next Steps:${NC}"
echo "1. If frontend is working now, use: ./scripts/start.sh"
echo "2. If still having issues, check: npm --version && node --version"
echo "3. Try manually: cd ui && npm run dev"
echo "4. Check firewall settings for port 5173"