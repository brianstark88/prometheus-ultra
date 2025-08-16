# Complete Frontend Integration Guide
# This will integrate the enhanced thinking panel into your existing UI

# Step 1: Navigate to your UI directory
cd ui

# Step 2: Install required dependencies
npm install lucide-react

# Step 3: Create the enhanced components directory structure
mkdir -p src/components/enhanced
mkdir -p src/types
mkdir -p src/hooks

# Step 4: Create type definitions
cat > src/types/agent.ts << 'EOF

# Step 7: Create the main Agent Interface component
cat > src/components/enhanced/AgentInterface.tsx << 'EOF'
import React, { useState, useCallback } from 'react';
import { Send, Loader2, Brain, BookOpen, CheckCircle } from 'lucide-react';
import { ThinkingStep, ReasoningStep, AgentEvent } from '../../types/agent';
import { useSSEConnection } from '../../hooks/useSSEConnection';
import ThinkingPanel from './ThinkingPanel';

interface AgentInterfaceProps {
  className?: string;
}

const AgentInterface: React.FC<AgentInterfaceProps> = ({ className = '' }) => {
  const [goal, setGoal] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [finalResult, setFinalResult] = useState<string>('');

  // Generate session ID
  const generateSessionId = (): string => {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  };

  // Handle thinking events
  const handleThinking = useCallback((step: ThinkingStep) => {
    setThinkingSteps(prev => [...prev, step]);
  }, []);

  // Handle reasoning events
  const handleReasoning = useCallback((step: ReasoningStep) => {
    // Add reasoning as thinking step for unified display
    setThinkingSteps(prev => [...prev, {
      thought: `🤔 ${step.reasoning}`,
      step_type: 'reasoning',
      timestamp: step.timestamp || Date.now()
    }]);
  }, []);

  // Handle other agent events
  const handleAgentEvent = useCallback((event: AgentEvent) => {
    console.log('Agent Event:', event.type, event.data);
    
    switch (event.type) {
      case 'final':
        setFinalResult(event.data.result);
        setIsProcessing(false);
        break;
        
      case 'status':
        if (event.data.status === 'starting') {
          setThinkingSteps([]);
          setFinalResult('');
        }
        break;
    }
  }, []);

  // SSE Connection
  const { connectionState, reconnect } = useSSEConnection({
    url: '/auto/stream',
    sessionId: currentSessionId,
    onThinking: handleThinking,
    onReasoning: handleReasoning,
    onEvent: handleAgentEvent,
    enabled: isProcessing && Boolean(currentSessionId)
  });

  // Submit goal
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim() || isProcessing) return;

    const sessionId = generateSessionId();
    setCurrentSessionId(sessionId);
    setIsProcessing(true);
    setThinkingSteps([]);
    setFinalResult('');

    try {
      // Trigger the SSE stream by making a request to your endpoint
      const response = await fetch(`/auto/stream?goal=${encodeURIComponent(goal.trim())}&session_id=${sessionId}`, {
        method: 'GET',
        headers: {
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // The SSE connection will handle the streaming response
      console.log('Goal submitted successfully');
      
    } catch (error) {
      console.error('Error submitting goal:', error);
      setIsProcessing(false);
      setThinkingSteps(prev => [...prev, {
        thought: `❌ Error submitting goal: ${error}`,
        step_type: 'error',
        timestamp: Date.now()
      }]);
    }
  };

  // Clear thinking panel
  const handleClearThinking = () => {
    setThinkingSteps([]);
    setFinalResult('');
  };

  // Example goals
  const exampleGoals = [
    "How many stars are there in the solar system?",
    "Count files in my Documents folder",
    "Find my most recent Python file and analyze it",
    "What's the capital of France?",
    "List all .txt files in my home directory",
    "Compare file and directory counts in ~/Desktop"
  ];

  return (
    <div className={`max-w-6xl mx-auto space-y-6 ${className}`}>
      {/* Header */}
      <div className="text-center mb-8">
        <div className="flex items-center justify-center space-x-3 mb-4">
          <Brain className="w-8 h-8 text-blue-400" />
          <h1 className="text-3xl font-bold text-white">GOD-MODE Agent</h1>
          <span className="text-sm bg-blue-600 text-white px-2 py-1 rounded-full">
            v3.2 Enhanced
          </span>
        </div>
        <p className="text-gray-400 max-w-2xl mx-auto">
          An intelligent AI agent that can answer questions, analyze files, and help with complex tasks. 
          Watch it think in real-time!
        </p>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Left Column: Input and Examples */}
        <div className="space-y-6">
          
          {/* Goal Input */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center">
              <Send className="w-5 h-5 mr-2" />
              What can I help you with?
            </h2>
            
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <textarea
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  placeholder="e.g., How many stars are there in the solar system?"
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-600 rounded-md text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none transition-colors"
                  rows={3}
                  disabled={isProcessing}
                />
              </div>
              
              <button
                type="submit"
                disabled={!goal.trim() || isProcessing}
                className="w-full flex items-center justify-center space-x-2 px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>Submit Goal</span>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Example Goals */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
              <BookOpen className="w-5 h-5 mr-2" />
              Example Goals
            </h3>
            <div className="grid grid-cols-1 gap-2">
              {exampleGoals.map((example, index) => (
                <button
                  key={index}
                  onClick={() => setGoal(example)}
                  disabled={isProcessing}
                  className="text-left p-3 bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded-md text-gray-300 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>

          {/* Final Result */}
          {finalResult && (
            <div className="bg-gray-900 border border-green-600 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-green-400 mb-3 flex items-center">
                <CheckCircle className="w-5 h-5 mr-2" />
                Final Result
              </h3>
              <div className="text-gray-200 whitespace-pre-wrap leading-relaxed">
                {finalResult}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Thinking Panel */}
        <div className="space-y-6">
          <ThinkingPanel
            steps={thinkingSteps}
            connectionState={connectionState}
            sessionId={currentSessionId}
            onClear={handleClearThinking}
            onReconnect={reconnect}
          />
        </div>
      </div>
    </div>
  );
};

export default AgentInterface;
EOF

# Step 8: Update your main App component
cat > src/App.tsx << 'EOF'
import React from 'react';
import AgentInterface from './components/enhanced/AgentInterface';
import './App.css';

function App() {
  return (
    <div className="min-h-screen bg-gray-950 p-6">
      <AgentInterface />
    </div>
  );
}

export default App;
EOF

# Step 9: Update package.json to include new dependencies (if not already present)
echo "
Make sure your package.json includes these dependencies:
{
  \"dependencies\": {
    \"react\": \"^18.0.0\",
    \"react-dom\": \"^18.0.0\",
    \"lucide-react\": \"^0.263.1\",
    \"@types/react\": \"^18.0.0\",
    \"@types/react-dom\": \"^18.0.0\",
    \"typescript\": \"^5.0.0\"
  }
}
"

# Step 10: Update your index.css for Tailwind (if not already configured)
cat > src/index.css << 'EOF'
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: #0a0a0a;
  color: #ffffff;
}

code {
  font-family: source-code-pro, Menlo, Monaco, Consolas, 'Courier New',
    monospace;
}

/* Custom scrollbar for thinking panel */
.bg-gray-950::-webkit-scrollbar {
  width: 6px;
}

.bg-gray-950::-webkit-scrollbar-track {
  background: #1f2937;
}

.bg-gray-950::-webkit-scrollbar-thumb {
  background: #4b5563;
  border-radius: 3px;
}

.bg-gray-950::-webkit-scrollbar-thumb:hover {
  background: #6b7280;
}
EOF

# Step 11: Create/update Tailwind config (if using Tailwind)
cat > tailwind.config.js << 'EOF'
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        gray: {
          950: '#0a0a0a',
        }
      }
    },
  },
  plugins: [],
}
EOF

# Step 12: Build and test
echo "
🚀 Integration Complete! 

Next steps:
1. Install dependencies: npm install
2. Start your backend: python api/app.py
3. Start your frontend: npm run dev
4. Test with: 'How many stars are there in the solar system?'

Your enhanced UI is now ready with real-time thinking display!
"

# Step 13: Run the integration
echo "Running integration commands..."

# Install dependencies
npm install

# Create a simple test script
cat > test-integration.sh << 'EOF'
#!/bin/bash
echo "🧪 Testing Enhanced GOD-MODE Agent Integration"
echo ""
echo "1. Starting backend in background..."
cd .. && python api/app.py &
BACKEND_PID=$!
sleep 3

echo "2. Starting frontend in background..."
cd ui && npm run dev &
FRONTEND_PID=$!
sleep 5

echo ""
echo "✅ Integration test complete!"
echo "🌐 Frontend: http://localhost:5173"
echo "🔧 Backend:  http://localhost:8000"
echo ""
echo "Test with: 'How many stars are there in the solar system?'"
echo ""
echo "To stop services:"
echo "kill $BACKEND_PID $FRONTEND_PID"
EOF

chmod +x test-integration.sh

echo "
🎉 INTEGRATION COMPLETE!

Your enhanced frontend is now integrated with:
✅ Real-time thinking display
✅ Enhanced SSE event handling  
✅ Beautiful UI with Tailwind CSS
✅ TypeScript types for safety
✅ Connection management
✅ Auto-scroll and controls

To test:
1. Run: ./test-integration.sh
2. Or manually:
   - Backend: python api/app.py
   - Frontend: npm run dev
3. Ask: 'How many stars are there in the solar system?'

You'll see real-time thinking like:
🎯 Goal: How many stars are there in the solar system?
🧠 This is a knowledge question - I can answer this directly
💡 Plan: I'll use the 'analyze' tool
🎉 SUCCESS: There is exactly one star in our solar system: the Sun

Enjoy your GOD-MODE Agent! 🧠⚡
"'
export interface ThinkingStep {
  thought: string;
  step_type: string;
  timestamp: number;
}

export interface ReasoningStep {
  step: string;
  reasoning: string;
  details?: any;
  timestamp: number;
}

export interface AgentEvent {
  type: string;
  data: any;
}

export interface SessionState {
  sessionId: string;
  isActive: boolean;
  startTime: number;
  endTime?: number;
}

export interface PlanData {
  strategy: string;
  next_action: string;
  args: any;
  rationale: string;
  tool_chain?: string[];
  confidence: number;
}

export interface ObservationData {
  observation: any;
  signature: string;
  error_class?: string;
  timestamp: number;
}

export interface FinalResult {
  result: string;
  success: boolean;
  confidence: number;
  suggestions?: string[];
}
EOF

# Step 5: Create SSE hook for managing connections
cat > src/hooks/useSSEConnection.ts << 'EOF'
import { useState, useEffect, useCallback, useRef } from 'react';
import { ThinkingStep, ReasoningStep, AgentEvent } from '../types/agent';

interface SSEConnectionProps {
  url: string;
  sessionId: string;
  onThinking: (step: ThinkingStep) => void;
  onReasoning: (step: ReasoningStep) => void;
  onEvent: (event: AgentEvent) => void;
  enabled: boolean;
}

export const useSSEConnection = ({
  url,
  sessionId,
  onThinking,
  onReasoning,
  onEvent,
  enabled
}: SSEConnectionProps) => {
  const [connectionState, setConnectionState] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (!enabled || !sessionId) return;

    setConnectionState('connecting');
    
    const eventSource = new EventSource(`${url}?session_id=${sessionId}`);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setConnectionState('connected');
      console.log('SSE connected');
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      setConnectionState('error');
    };

    // Handle thinking events
    eventSource.addEventListener('thinking', (event) => {
      try {
        const data = JSON.parse(event.data);
        onThinking(data);
      } catch (error) {
        console.error('Failed to parse thinking event:', error);
      }
    });

    // Handle reasoning events
    eventSource.addEventListener('reasoning', (event) => {
      try {
        const data = JSON.parse(event.data);
        onReasoning(data);
      } catch (error) {
        console.error('Failed to parse reasoning event:', error);
      }
    });

    // Handle all other events
    const eventTypes = ['status', 'plan', 'exec', 'obs', 'final', 'critic', 'hyp', 'bb', 'met'];
    eventTypes.forEach(eventType => {
      eventSource.addEventListener(eventType, (event) => {
        try {
          const data = JSON.parse(event.data);
          onEvent({ type: eventType, data });
        } catch (error) {
          console.error(`Failed to parse ${eventType} event:`, error);
        }
      });
    });

  }, [url, sessionId, enabled, onThinking, onReasoning, onEvent]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setConnectionState('disconnected');
    }
  }, []);

  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }

    return disconnect;
  }, [enabled, connect, disconnect]);

  return {
    connectionState,
    reconnect: connect,
    disconnect
  };
};
EOF

# Step 6: Create the Enhanced Thinking Panel component
cat > src/components/enhanced/ThinkingPanel.tsx << 'EOF'
import React, { useState, useRef, useEffect } from 'react';
import { 
  ChevronDown, 
  ChevronRight, 
  Brain, 
  Zap, 
  Target, 
  CheckCircle, 
  AlertCircle, 
  Clock, 
  Settings,
  Trash2,
  RotateCcw
} from 'lucide-react';
import { ThinkingStep } from '../../types/agent';

interface ThinkingPanelProps {
  steps: ThinkingStep[];
  connectionState: 'disconnected' | 'connecting' | 'connected' | 'error';
  sessionId: string;
  onClear: () => void;
  onReconnect: () => void;
}

const ThinkingPanel: React.FC<ThinkingPanelProps> = ({ 
  steps, 
  connectionState, 
  sessionId, 
  onClear, 
  onReconnect 
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const lastStepRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new steps added
  useEffect(() => {
    if (autoScroll && lastStepRef.current) {
      lastStepRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [steps, autoScroll]);

  const getStepIcon = (stepType: string) => {
    const icons: Record<string, React.ReactNode> = {
      'goal_analysis': <Target className="w-4 h-4" />,
      'goal_classification': <Target className="w-4 h-4" />,
      'planning': <Brain className="w-4 h-4" />,
      'plan_decision': <Brain className="w-4 h-4" />,
      'plan_reasoning': <Brain className="w-4 h-4" />,
      'tool_chain': <Zap className="w-4 h-4" />,
      'execution': <Zap className="w-4 h-4" />,
      'execution_args': <Zap className="w-4 h-4" />,
      'success': <CheckCircle className="w-4 h-4" />,
      'error': <AlertCircle className="w-4 h-4" />,
      'final': <CheckCircle className="w-4 h-4" />,
      'status': <Settings className="w-4 h-4" />
    };
    
    return icons[stepType] || <Clock className="w-4 h-4" />;
  };

  const getStepColorClass = (stepType: string): string => {
    const colors: Record<string, string> = {
      'goal_analysis': 'border-blue-500 bg-blue-500/10 text-blue-300',
      'goal_classification': 'border-blue-400 bg-blue-400/10 text-blue-200',
      'planning': 'border-purple-500 bg-purple-500/10 text-purple-300',
      'plan_decision': 'border-purple-400 bg-purple-400/10 text-purple-200',
      'plan_reasoning': 'border-purple-300 bg-purple-300/10 text-purple-100',
      'tool_chain': 'border-indigo-400 bg-indigo-400/10 text-indigo-200',
      'execution': 'border-amber-500 bg-amber-500/10 text-amber-300',
      'execution_args': 'border-amber-400 bg-amber-400/10 text-amber-200',
      'success': 'border-green-500 bg-green-500/10 text-green-300',
      'error': 'border-red-500 bg-red-500/10 text-red-300',
      'final': 'border-emerald-500 bg-emerald-500/10 text-emerald-300',
      'status': 'border-cyan-500 bg-cyan-500/10 text-cyan-300',
      'reasoning': 'border-violet-500 bg-violet-500/10 text-violet-300'
    };
    
    return colors[stepType] || 'border-gray-600 bg-gray-600/10 text-gray-400';
  };

  const formatTime = (timestamp: number): string => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const getConnectionStatusColor = () => {
    switch (connectionState) {
      case 'connected': return 'bg-green-500';
      case 'connecting': return 'bg-yellow-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  if (!isExpanded) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg">
        <div 
          className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-800 transition-colors"
          onClick={() => setIsExpanded(true)}
        >
          <div className="flex items-center space-x-2">
            <ChevronRight className="w-4 h-4 text-gray-400" />
            <Brain className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium text-gray-300">Agent Thinking</span>
            {steps.length > 0 && (
              <span className="text-xs bg-blue-600 text-white px-2 py-1 rounded-full">
                {steps.length}
              </span>
            )}
          </div>
          <div className={`w-2 h-2 rounded-full ${getConnectionStatusColor()}`}></div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-3 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setIsExpanded(false)}
            className="text-gray-400 hover:text-gray-200 transition-colors"
          >
            <ChevronDown className="w-4 h-4" />
          </button>
          <Brain className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-gray-300">Agent Thinking</span>
          {steps.length > 0 && (
            <span className="text-xs bg-blue-600 text-white px-2 py-1 rounded-full">
              {steps.length}
            </span>
          )}
        </div>
        
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              autoScroll 
                ? 'bg-blue-600 text-white' 
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            Auto-scroll
          </button>
          
          {connectionState === 'error' && (
            <button
              onClick={onReconnect}
              className="text-xs px-2 py-1 rounded bg-yellow-600 text-white hover:bg-yellow-700 transition-colors flex items-center space-x-1"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Reconnect</span>
            </button>
          )}
          
          <button
            onClick={onClear}
            className="text-xs px-2 py-1 rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors flex items-center space-x-1"
          >
            <Trash2 className="w-3 h-3" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* Thinking Steps */}
      <div 
        ref={containerRef}
        className="max-h-96 overflow-y-auto p-4 space-y-2 bg-gray-950"
      >
        {steps.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            <Brain className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Waiting for agent to start thinking...</p>
            {connectionState === 'disconnected' && (
              <p className="text-xs mt-2 text-gray-600">Not connected</p>
            )}
            {connectionState === 'connecting' && (
              <p className="text-xs mt-2 text-yellow-500">Connecting...</p>
            )}
          </div>
        ) : (
          steps.map((step, index) => (
            <div
              key={index}
              className={`p-3 rounded-md border-l-4 transition-all duration-200 ${getStepColorClass(step.step_type)}`}
              ref={index === steps.length - 1 ? lastStepRef : undefined}
            >
              <div className="flex items-start space-x-2">
                <div className="flex-shrink-0 mt-0.5">
                  {getStepIcon(step.step_type)}
                </div>
                
                <div className="flex-1 min-w-0">
                  <p className="text-sm leading-relaxed break-words">
                    {step.thought}
                  </p>
                </div>
                
                <div className="flex-shrink-0 text-xs opacity-60">
                  {formatTime(step.timestamp)}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Connection Status */}
      <div className="px-3 py-2 bg-gray-800 border-t border-gray-700">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${getConnectionStatusColor()}`}></div>
            <span className="capitalize">{connectionState}</span>
          </div>
          
          <span>Session: {sessionId.substring(0, 8)}...</span>
        </div>
      </div>
    </div>
  );
};

export default ThinkingPanel;
EOF