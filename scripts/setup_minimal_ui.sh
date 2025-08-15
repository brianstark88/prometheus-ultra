#!/bin/bash

echo "🎨 Setting up Minimal Working UI"
echo "================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Create UI directory structure
echo -e "${BLUE}📁 Creating UI directory structure...${NC}"
mkdir -p ui/src

# Create package.json
echo -e "${BLUE}📦 Creating package.json...${NC}"
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

# Create vite.config.ts
echo -e "${BLUE}⚙️ Creating vite.config.ts...${NC}"
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

# Create tsconfig.json
echo -e "${BLUE}📝 Creating tsconfig.json...${NC}"
cat > ui/tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
EOF

# Create tsconfig.node.json
cat > ui/tsconfig.node.json << 'EOF'
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
EOF

# Create index.html
echo -e "${BLUE}🌐 Creating index.html...${NC}"
cat > ui/index.html << 'EOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>GOD-MODE Agent v3.2 ULTRA</title>
    <style>
      body {
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        background: #0f172a;
        color: #f1f5f9;
      }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
EOF

# Create App.tsx
echo -e "${BLUE}⚛️ Creating App.tsx...${NC}"
cat > ui/src/App.tsx << 'EOF'
import React, { useState, useEffect } from 'react';

interface HealthStatus {
  ok: boolean;
  tools_loaded: number;
  models: {
    healthy_models: string[];
    system_healthy: boolean;
  };
}

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [goal, setGoal] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState('');

  useEffect(() => {
    // Check backend health on load
    fetch('http://127.0.0.1:8000/health')
      .then(res => res.json())
      .then(setHealth)
      .catch(console.error);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;

    setIsLoading(true);
    setResponse('');

    try {
      const url = `http://127.0.0.1:8000/auto/stream?goal=${encodeURIComponent(goal)}`;
      const eventSource = new EventSource(url);

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setResponse(prev => prev + '\n' + JSON.stringify(data, null, 2));
        } catch (e) {
          setResponse(prev => prev + '\n' + event.data);
        }
      };

      eventSource.addEventListener('final', (event) => {
        eventSource.close();
        setIsLoading(false);
      });

      eventSource.onerror = () => {
        eventSource.close();
        setIsLoading(false);
        setResponse(prev => prev + '\n[Connection error]');
      };

    } catch (error) {
      setIsLoading(false);
      setResponse('Error: ' + String(error));
    }
  };

  return (
    <div style={{ 
      minHeight: '100vh',
      padding: '20px',
      maxWidth: '1200px',
      margin: '0 auto'
    }}>
      {/* Header */}
      <div style={{
        textAlign: 'center',
        marginBottom: '40px',
        borderBottom: '1px solid #334155',
        paddingBottom: '20px'
      }}>
        <h1 style={{ 
          fontSize: '2.5rem',
          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          margin: '0 0 10px 0'
        }}>
          🔱 GOD-MODE Agent
        </h1>
        <div style={{
          fontSize: '0.875rem',
          backgroundColor: '#1e293b',
          padding: '8px 16px',
          borderRadius: '20px',
          display: 'inline-block',
          color: '#94a3b8'
        }}>
          v3.2 Prometheus ULTRA
        </div>
      </div>

      {/* Status */}
      <div style={{
        backgroundColor: '#1e293b',
        padding: '20px',
        borderRadius: '12px',
        marginBottom: '30px',
        border: '1px solid #334155'
      }}>
        <h3 style={{ margin: '0 0 15px 0', color: '#e2e8f0' }}>System Status</h3>
        {health ? (
          <div>
            <div style={{ marginBottom: '10px' }}>
              <span style={{ 
                backgroundColor: health.ok ? '#059669' : '#dc2626',
                color: 'white',
                padding: '4px 12px',
                borderRadius: '20px',
                fontSize: '0.875rem',
                fontWeight: 'bold'
              }}>
                {health.ok ? '✅ ONLINE' : '❌ OFFLINE'}
              </span>
            </div>
            <div style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
              Tools Loaded: {health.tools_loaded} | 
              Models: {health.models.healthy_models.join(', ')} |
              System: {health.models.system_healthy ? 'Healthy' : 'Issues'}
            </div>
          </div>
        ) : (
          <div style={{ color: '#fbbf24' }}>🔄 Checking backend connection...</div>
        )}
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} style={{ marginBottom: '30px' }}>
        <div style={{
          backgroundColor: '#1e293b',
          padding: '20px',
          borderRadius: '12px',
          border: '1px solid #334155'
        }}>
          <label style={{ 
            display: 'block', 
            marginBottom: '10px',
            fontWeight: 'bold',
            color: '#e2e8f0'
          }}>
            What would you like me to help you with?
          </label>
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="e.g., Count files in my home directory, Get latest news headlines, Analyze my Desktop files..."
            style={{
              width: '100%',
              minHeight: '80px',
              padding: '12px',
              border: '1px solid #475569',
              borderRadius: '8px',
              backgroundColor: '#0f172a',
              color: '#f1f5f9',
              fontSize: '1rem',
              resize: 'vertical',
              fontFamily: 'inherit'
            }}
          />
          <button
            type="submit"
            disabled={isLoading || !goal.trim()}
            style={{
              marginTop: '15px',
              backgroundColor: isLoading ? '#475569' : '#3b82f6',
              color: 'white',
              border: 'none',
              padding: '12px 24px',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              transition: 'background-color 0.2s'
            }}
          >
            {isLoading ? '🧠 Thinking...' : '🚀 Execute Goal'}
          </button>
        </div>
      </form>

      {/* Response */}
      {response && (
        <div style={{
          backgroundColor: '#1e293b',
          padding: '20px',
          borderRadius: '12px',
          border: '1px solid #334155'
        }}>
          <h3 style={{ margin: '0 0 15px 0', color: '#e2e8f0' }}>Agent Response</h3>
          <pre style={{
            backgroundColor: '#0f172a',
            padding: '15px',
            borderRadius: '8px',
            overflow: 'auto',
            fontSize: '0.875rem',
            color: '#94a3b8',
            border: '1px solid #334155',
            maxHeight: '400px',
            whiteSpace: 'pre-wrap'
          }}>
            {response}
          </pre>
        </div>
      )}

      {/* Quick Test Examples */}
      <div style={{
        marginTop: '30px',
        backgroundColor: '#1e293b',
        padding: '20px',
        borderRadius: '12px',
        border: '1px solid #334155'
      }}>
        <h3 style={{ margin: '0 0 15px 0', color: '#e2e8f0' }}>Quick Test Examples</h3>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          {[
            'Count files in ~',
            'List files in ~/Desktop',
            'Get CNN headlines',
            'Current time and date'
          ].map((example) => (
            <button
              key={example}
              onClick={() => setGoal(example)}
              style={{
                backgroundColor: '#374151',
                color: '#e2e8f0',
                border: '1px solid #4b5563',
                padding: '8px 16px',
                borderRadius: '6px',
                fontSize: '0.875rem',
                cursor: 'pointer'
              }}
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default App;
EOF

# Create main.tsx
echo -e "${BLUE}🚀 Creating main.tsx...${NC}"
cat > ui/src/main.tsx << 'EOF'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
EOF

# Install dependencies
echo -e "${BLUE}📦 Installing UI dependencies...${NC}"
cd ui
npm install

echo ""
echo -e "${GREEN}✅ Minimal UI setup complete!${NC}"
echo ""
echo -e "${BLUE}🚀 To start the frontend:${NC}"
echo "  cd ui && npm run dev"
echo ""
echo -e "${BLUE}🌐 Or use the start script:${NC}"
echo "  ./scripts/start.sh"
echo ""
echo -e "${GREEN}✨ Ready to test! 🧠⚡${NC}"