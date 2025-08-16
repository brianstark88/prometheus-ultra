// ui/src/components/EnhancedThinkingPanel.tsx
import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Brain, Zap, Target, CheckCircle, AlertCircle, Clock, Settings } from 'lucide-react';

interface ThinkingStep {
  thought: string;
  step_type: string;
  timestamp: number;
}

interface ReasoningStep {
  step: string;
  reasoning: string;
  details?: any;
  timestamp: number;
}

interface AgentEvent {
  type: string;
  data: any;
}

interface EnhancedThinkingPanelProps {
  sessionId: string;
  isActive: boolean;
  onClear?: () => void;
}

const EnhancedThinkingPanel: React.FC<EnhancedThinkingPanelProps> = ({ 
  sessionId, 
  isActive, 
  onClear 
}) => {
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [reasoningSteps, setReasoningSteps] = useState<ReasoningStep[]>([]);
  const [isExpanded, setIsExpanded] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);
  
  const thinkingRef = useRef<HTMLDivElement>(null);
  const lastStepRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new steps added
  useEffect(() => {
    if (autoScroll && lastStepRef.current) {
      lastStepRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [thinkingSteps, reasoningSteps, autoScroll]);

  // SSE Connection Management
  useEffect(() => {
    if (!isActive || !sessionId) return;

    // Create new EventSource connection
    const es = new EventSource(`/auto/stream?session_id=${sessionId}`);
    setEventSource(es);

    // Handle SSE events
    es.onmessage = (event) => {
      try {
        const eventData = JSON.parse(event.data);
        handleSSEEvent({ type: event.type || 'message', data: eventData });
      } catch (error) {
        console.error('Failed to parse SSE event:', error);
      }
    };

    // Handle specific event types
    es.addEventListener('thinking', (event) => {
      const data = JSON.parse(event.data);
      handleThinkingEvent(data);
    });

    es.addEventListener('reasoning', (event) => {
      const data = JSON.parse(event.data);
      handleReasoningEvent(data);
    });

    es.addEventListener('status', (event) => {
      const data = JSON.parse(event.data);
      handleStatusEvent(data);
    });

    es.addEventListener('plan', (event) => {
      const data = JSON.parse(event.data);
      handlePlanEvent(data);
    });

    es.addEventListener('exec', (event) => {
      const data = JSON.parse(event.data);
      handleExecEvent(data);
    });

    es.addEventListener('obs', (event) => {
      const data = JSON.parse(event.data);
      handleObsEvent(data);
    });

    es.addEventListener('final', (event) => {
      const data = JSON.parse(event.data);
      handleFinalEvent(data);
    });

    es.onerror = (error) => {
      console.error('SSE connection error:', error);
      addThinkingStep("❌ Connection error - attempting to reconnect...", "error");
    };

    return () => {
      es.close();
      setEventSource(null);
    };
  }, [sessionId, isActive]);

  const handleSSEEvent = (event: AgentEvent) => {
    // Generic event handler for any events not specifically handled
    console.log('SSE Event:', event.type, event.data);
  };

  const handleThinkingEvent = (data: ThinkingStep) => {
    addThinkingStep(data.thought, data.step_type, data.timestamp);
  };

  const handleReasoningEvent = (data: ReasoningStep) => {
    setReasoningSteps(prev => [...prev, data]);
    // Also add to thinking steps for unified view
    addThinkingStep(`🤔 ${data.reasoning}`, "reasoning", data.timestamp);
  };

  const handleStatusEvent = (data: any) => {
    const statusEmojis: Record<string, string> = {
      'starting': '🚀',
      'planning': '🧠',
      'executing': '⚡',
      'verifying_hypothesis': '🔍',
      'completed': '✅',
      'error': '❌'
    };

    const emoji = statusEmojis[data.status] || '⚙️';
    const statusText = data.status.replace(/_/g, ' ').toUpperCase();
    
    addThinkingStep(`${emoji} ${statusText}`, "status");
  };

  const handlePlanEvent = (data: any) => {
    const action = data.next_action || 'unknown';
    const rationale = data.rationale || 'No rationale provided';
    
    addThinkingStep(`📋 Plan: ${action}`, "plan");
    addThinkingStep(`💡 ${rationale}`, "plan_reasoning");
    
    if (data.tool_chain && data.tool_chain.length > 1) {
      addThinkingStep(`🔗 Chain: ${data.tool_chain.join(' → ')}`, "tool_chain");
    }
  };

  const handleExecEvent = (data: any) => {
    const tool = data.tool || 'unknown';
    const argsStr = data.args ? JSON.stringify(data.args) : '{}';
    
    addThinkingStep(`🔨 Executing: ${tool}`, "execution");
    
    // Show args if they're not too long
    if (argsStr.length < 100) {
      addThinkingStep(`📝 Args: ${argsStr}`, "execution_args");
    }
  };

  const handleObsEvent = (data: any) => {
    if (data.error_class) {
      addThinkingStep(`❌ Error: ${data.error_class}`, "error");
      if (data.observation) {
        addThinkingStep(`📄 ${truncateText(data.observation, 150)}`, "error_detail");
      }
    } else {
      const signature = data.signature || 'unknown';
      addThinkingStep(`✅ Success: ${signature}`, "success");
      
      // Show observation if it's short and informative
      if (data.observation && typeof data.observation === 'string' && data.observation.length < 200) {
        addThinkingStep(`📄 ${data.observation}`, "observation");
      } else if (data.observation && typeof data.observation === 'object') {
        const summary = summarizeObject(data.observation);
        addThinkingStep(`📊 ${summary}`, "observation");
      }
    }
  };

  const handleFinalEvent = (data: any) => {
    const emoji = data.success ? '🎉' : '⏹️';
    const status = data.success ? 'SUCCESS' : 'COMPLETED';
    
    addThinkingStep(`${emoji} ${status}`, "final");
    addThinkingStep(`📋 ${truncateText(data.result, 200)}`, "final_result");
  };

  const addThinkingStep = (thought: string, stepType: string, timestamp?: number) => {
    const newStep: ThinkingStep = {
      thought,
      step_type: stepType,
      timestamp: timestamp || Date.now()
    };
    
    setThinkingSteps(prev => [...prev, newStep]);
  };

  const truncateText = (text: string, maxLength: number): string => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const summarizeObject = (obj: any): string => {
    if (Array.isArray(obj)) {
      return `Array with ${obj.length} items`;
    } else if (typeof obj === 'object' && obj !== null) {
      const keys = Object.keys(obj);
      if (keys.includes('count')) {
        return `Count: ${obj.count}`;
      } else if (keys.includes('result')) {
        return `Result: ${obj.result}`;
      } else {
        return `Object with ${keys.length} properties`;
      }
    }
    return String(obj);
  };

  const clearThinking = () => {
    setThinkingSteps([]);
    setReasoningSteps([]);
    if (onClear) onClear();
  };

  const getStepIcon = (stepType: string) => {
    const icons: Record<string, React.ReactNode> = {
      'goal_analysis': <Target className="w-4 h-4" />,
      'planning': <Brain className="w-4 h-4" />,
      'execution': <Zap className="w-4 h-4" />,
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
      'error_detail': 'border-red-400 bg-red-400/10 text-red-200',
      'final': 'border-emerald-500 bg-emerald-500/10 text-emerald-300',
      'final_result': 'border-emerald-400 bg-emerald-400/10 text-emerald-200',
      'status': 'border-cyan-500 bg-cyan-500/10 text-cyan-300',
      'observation': 'border-gray-500 bg-gray-500/10 text-gray-300',
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

  if (!isExpanded) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg">
        <div 
          className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-800"
          onClick={() => setIsExpanded(true)}
        >
          <div className="flex items-center space-x-2">
            <ChevronRight className="w-4 h-4 text-gray-400" />
            <Brain className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium text-gray-300">Agent Thinking</span>
            {thinkingSteps.length > 0 && (
              <span className="text-xs bg-blue-600 text-white px-2 py-1 rounded-full">
                {thinkingSteps.length}
              </span>
            )}
          </div>
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
            className="text-gray-400 hover:text-gray-200"
          >
            <ChevronDown className="w-4 h-4" />
          </button>
          <Brain className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-gray-300">Agent Thinking</span>
          {thinkingSteps.length > 0 && (
            <span className="text-xs bg-blue-600 text-white px-2 py-1 rounded-full">
              {thinkingSteps.length}
            </span>
          )}
        </div>
        
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`text-xs px-2 py-1 rounded ${
              autoScroll 
                ? 'bg-blue-600 text-white' 
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            Auto-scroll
          </button>
          
          <button
            onClick={clearThinking}
            className="text-xs px-2 py-1 rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Thinking Steps */}
      <div 
        ref={thinkingRef}
        className="max-h-96 overflow-y-auto p-4 space-y-2 bg-gray-950"
      >
        {thinkingSteps.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            <Brain className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Waiting for agent to start thinking...</p>
          </div>
        ) : (
          thinkingSteps.map((step, index) => (
            <div
              key={index}
              className={`p-3 rounded-md border-l-4 ${getStepColorClass(step.step_type)}`}
              ref={index === thinkingSteps.length - 1 ? lastStepRef : undefined}
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
            <div className={`w-2 h-2 rounded-full ${
              eventSource?.readyState === EventSource.OPEN 
                ? 'bg-green-500' 
                : 'bg-red-500'
            }`}></div>
            <span>
              {eventSource?.readyState === EventSource.OPEN 
                ? 'Connected' 
                : 'Disconnected'
              }
            </span>
          </div>
          
          <span>Session: {sessionId.substring(0, 8)}...</span>
        </div>
      </div>
    </div>
  );
};

export default EnhancedThinkingPanel;

// ui/src/components/AgentInterface.tsx
import React, { useState } from 'react';
import { Send, Loader2 } from 'lucide-react';
import EnhancedThinkingPanel from './EnhancedThinkingPanel';

interface AgentInterfaceProps {
  onSubmitGoal: (goal: string) => void;
  isLoading: boolean;
}

const AgentInterface: React.FC<AgentInterfaceProps> = ({ onSubmitGoal, isLoading }) => {
  const [goal, setGoal] = useState('');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (goal.trim() && !isLoading) {
      const sessionId = generateSessionId();
      setCurrentSessionId(sessionId);
      onSubmitGoal(goal.trim());
    }
  };

  const generateSessionId = (): string => {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  };

  const handleClearThinking = () => {
    // Reset session when clearing thinking
    setCurrentSessionId(null);
  };

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {/* Goal Input */}
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
        <h1 className="text-2xl font-bold text-white mb-4 flex items-center">
          <span className="mr-2">🧠</span>
          GOD-MODE Agent
        </h1>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="goal" className="block text-sm font-medium text-gray-300 mb-2">
              What would you like me to help you with?
            </label>
            <textarea
              id="goal"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g., How many stars are there in the solar system?"
              className="w-full px-4 py-3 bg-gray-800 border border-gray-600 rounded-md text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              rows={3}
              disabled={isLoading}
            />
          </div>
          
          <button
            type="submit"
            disabled={!goal.trim() || isLoading}
            className="flex items-center space-x-2 px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
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

      {/* Enhanced Thinking Panel */}
      {currentSessionId && (
        <EnhancedThinkingPanel
          sessionId={currentSessionId}
          isActive={isLoading}
          onClear={handleClearThinking}
        />
      )}

      {/* Example Goals */}
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Example Goals</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            "How many stars are there in the solar system?",
            "Count files in my Documents folder",
            "Find my most recent Python file and analyze it",
            "What's the capital of France?",
            "List all .txt files in my home directory",
            "Compare file and directory counts in ~/Desktop"
          ].map((example, index) => (
            <button
              key={index}
              onClick={() => setGoal(example)}
              disabled={isLoading}
              className="text-left p-3 bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded-md text-gray-300 text-sm transition-colors disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AgentInterface;

// ui/src/App.tsx
import React, { useState } from 'react';
import AgentInterface from './components/AgentInterface';

const App: React.FC = () => {
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmitGoal = async (goal: string) => {
    setIsLoading(true);
    
    try {
      // The actual goal submission will be handled by the SSE connection
      // in the EnhancedThinkingPanel component
      console.log('Submitting goal:', goal);
      
      // Simulate some processing time
      await new Promise(resolve => setTimeout(resolve, 2000));
    } catch (error) {
      console.error('Error submitting goal:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950">
      <AgentInterface
        onSubmitGoal={handleSubmitGoal}
        isLoading={isLoading}
      />
    </div>
  );
};

export default App;