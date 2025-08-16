import React, { useState, useEffect, useRef } from 'react';

interface Message {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: number;
  thinking?: ThinkingStep[];
  isStreaming?: boolean;
}

interface ThinkingStep {
  type: string;
  data: any;
  timestamp: number;
  thought?: string;
  step_type?: string;
}

interface HealthStatus {
  ok: boolean;
  tools_loaded: number;
  models: {
    healthy_models: string[];
    system_healthy: boolean;
  };
  enhanced_mode: boolean;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [showThinking, setShowThinking] = useState(true); // Default to true to see thinking
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch('http://127.0.0.1:8000/health')
      .then(res => res.json())
      .then(setHealth)
      .catch(console.error);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    };

    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      type: 'assistant',
      content: '',
      timestamp: Date.now(),
      thinking: [],
      isStreaming: true,
    };

    setMessages(prev => [...prev, userMessage, assistantMessage]);
    setInput('');
    setIsStreaming(true);

    try {
      const url = `http://127.0.0.1:8000/auto/stream?goal=${encodeURIComponent(input.trim())}`;
      const eventSource = new EventSource(url);
      
      let currentThinking: ThinkingStep[] = [];
      let finalResult = '';

      const updateAssistantMessage = (updates: Partial<Message>) => {
        setMessages(prev => prev.map(msg => 
          msg.id === assistantMessage.id ? { ...msg, ...updates } : msg
        ));
      };

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          currentThinking.push({
            type: 'message',
            data,
            timestamp: Date.now()
          });
          updateAssistantMessage({ thinking: [...currentThinking] });
        } catch (e) {
          console.error('Failed to parse message:', e);
        }
      };

      // Handle new thinking events
      eventSource.addEventListener('thinking', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          currentThinking.push({
            type: 'thinking',
            data,
            timestamp: Date.now(),
            thought: data.thought,
            step_type: data.step_type
          });
          updateAssistantMessage({ thinking: [...currentThinking] });
        } catch (e) {
          console.error('Failed to parse thinking:', e);
        }
      });

      // Handle reasoning events
      eventSource.addEventListener('reasoning', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          currentThinking.push({
            type: 'reasoning',
            data,
            timestamp: Date.now(),
            thought: `🤔 ${data.reasoning}`,
            step_type: 'reasoning'
          });
          updateAssistantMessage({ thinking: [...currentThinking] });
        } catch (e) {
          console.error('Failed to parse reasoning:', e);
        }
      });

      // Handle existing events
      ['status', 'plan', 'critic', 'exec', 'obs', 'hyp', 'bb', 'met'].forEach(eventType => {
        eventSource.addEventListener(eventType, (event) => {
          try {
            const data = JSON.parse((event as MessageEvent).data);
            currentThinking.push({
              type: eventType,
              data,
              timestamp: Date.now()
            });
            updateAssistantMessage({ thinking: [...currentThinking] });
          } catch (e) {
            console.error(`Failed to parse ${eventType}:`, e);
          }
        });
      });

      eventSource.addEventListener('final', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          finalResult = data.result || 'Task completed';
          
          currentThinking.push({
            type: 'final',
            data,
            timestamp: Date.now(),
            thought: `🎉 ${data.success ? 'SUCCESS' : 'COMPLETED'}: ${finalResult}`,
            step_type: 'final'
          });

          updateAssistantMessage({
            content: finalResult,
            thinking: [...currentThinking],
            isStreaming: false
          });

          eventSource.close();
          setIsStreaming(false);
        } catch (e) {
          console.error('Failed to parse final:', e);
          eventSource.close();
          setIsStreaming(false);
        }
      });

      eventSource.onerror = () => {
        eventSource.close();
        setIsStreaming(false);
        if (!finalResult) {
          updateAssistantMessage({
            content: 'Sorry, there was an error processing your request.',
            isStreaming: false
          });
        }
      };

    } catch (error) {
      setIsStreaming(false);
      setMessages(prev => prev.map(msg => 
        msg.id === assistantMessage.id 
          ? { ...msg, content: 'Error: ' + String(error), isStreaming: false }
          : msg
      ));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  const formatThinkingData = (step: ThinkingStep) => {
    // Handle new thinking format - prioritize actual thoughts
    if (step.type === 'thinking' && step.thought) {
      return step.thought;
    } else if (step.type === 'reasoning' && step.thought) {
      return step.thought;
    }
    
    // Handle existing event types with cleaner formatting
    if (step.type === 'status') {
      const statusEmojis: Record<string, string> = {
        'starting': '🚀',
        'planning': '🧠',
        'executing': '⚡',
        'verifying_hypothesis': '🔍'
      };
      const emoji = statusEmojis[step.data.status] || '⚙️';
      return `${emoji} ${step.data.status.replace('_', ' ').toUpperCase()}`;
    } else if (step.type === 'plan') {
      const action = step.data.next_action || 'unknown';
      const rationale = step.data.rationale;
      if (rationale && rationale.length < 100) {
        return `📋 Plan: ${action} - ${rationale}`;
      }
      return `📋 Plan: ${action}`;
    } else if (step.type === 'exec') {
      return `🔨 Executing: ${step.data.tool}`;
    } else if (step.type === 'obs') {
      if (step.data.error_class) {
        return `❌ Error: ${step.data.error_class}`;
      } else {
        // Clean up observation display
        let obs = step.data.observation;
        if (typeof obs === 'string') {
          // For knowledge questions, show the actual answer
          if (obs.includes('solar system') || obs.includes('star')) {
            return `✅ Answer: ${obs.substring(0, 200)}${obs.length > 200 ? '...' : ''}`;
          }
          return `✅ Result: ${obs.substring(0, 100)}${obs.length > 100 ? '...' : ''}`;
        }
        return `✅ Result: ${step.data.signature}`;
      }
    } else if (step.type === 'final') {
      if (step.thought) {
        return step.thought;
      }
      return `🎉 ${step.data.success ? 'SUCCESS' : 'COMPLETED'}: ${step.data.result}`;
    } else if (step.type === 'hyp') {
      // Skip showing raw hypothesis data
      if (step.data.expected_match) {
        return `✅ Results match expectations`;
      } else {
        return `⚠️ Results differ from expectations, but may still be useful`;
      }
    } else if (step.type === 'bb' || step.type === 'met') {
      // Skip showing raw blackboard and metrics data in thinking panel
      return null;
    }
    
    // Fallback for unknown types - but don't show session IDs
    if (step.data && typeof step.data === 'object' && step.data.session_id) {
      return null; // Hide technical SSE data
    }
    
    return `${step.type}: ${JSON.stringify(step.data).substring(0, 50)}...`;
  };

  const getThinkingStepColor = (step: ThinkingStep) => {
    if (step.step_type) {
      const colors: Record<string, string> = {
        'goal_analysis': '#3b82f6',
        'goal_classification': '#3b82f6',
        'planning': '#8b5cf6',
        'plan_decision': '#8b5cf6',
        'plan_reasoning': '#8b5cf6',
        'execution': '#f59e0b',
        'execution_start': '#f59e0b',
        'success': '#10b981',
        'error': '#ef4444',
        'final': '#06d6a0',
        'reasoning': '#8b5cf6'
      };
      return colors[step.step_type] || '#6b7280';
    }
    
    const typeColors: Record<string, string> = {
      'status': '#06b6d4',
      'plan': '#8b5cf6',
      'exec': '#f59e0b',
      'obs': '#10b981',
      'final': '#06d6a0',
      'thinking': '#8b5cf6',
      'reasoning': '#8b5cf6'
    };
    return typeColors[step.type] || '#6b7280';
  };

  // Styles (keeping your existing styles but adding thinking styles)
  const styles = {
    container: {
      minHeight: '100vh',
      backgroundColor: '#ffffff',
      display: 'flex',
      flexDirection: 'column' as const,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    },
    header: {
      borderBottom: '1px solid #e5e7eb',
      backgroundColor: '#ffffff',
      position: 'sticky' as const,
      top: 0,
      zIndex: 10,
    },
    headerContent: {
      maxWidth: '896px',
      margin: '0 auto',
      padding: '12px 16px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    logoSection: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
    },
    logo: {
      width: '32px',
      height: '32px',
      background: 'linear-gradient(135deg, #f97316, #dc2626)',
      borderRadius: '8px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'white',
      fontSize: '14px',
      fontWeight: 'bold',
    },
    titleSection: {
      display: 'flex',
      flexDirection: 'column' as const,
    },
    title: {
      fontSize: '18px',
      fontWeight: '600',
      color: '#111827',
      margin: 0,
    },
    subtitle: {
      fontSize: '12px',
      color: '#6b7280',
      margin: 0,
    },
    headerRight: {
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
    },
    statusIndicator: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      fontSize: '14px',
    },
    statusDot: {
      width: '8px',
      height: '8px',
      borderRadius: '50%',
      backgroundColor: health?.ok ? '#10b981' : '#ef4444',
    },
    enhancedBadge: {
      fontSize: '10px',
      backgroundColor: health?.enhanced_mode ? '#3b82f6' : '#6b7280',
      color: 'white',
      padding: '2px 6px',
      borderRadius: '4px',
      fontWeight: '500',
    },
    button: {
      padding: '6px 12px',
      fontSize: '14px',
      border: '1px solid #d1d5db',
      borderRadius: '6px',
      backgroundColor: '#ffffff',
      color: '#374151',
      cursor: 'pointer',
      transition: 'background-color 0.2s',
    },
    main: {
      flex: 1,
      maxWidth: '896px',
      margin: '0 auto',
      width: '100%',
      padding: '24px 16px',
    },
    welcomeScreen: {
      textAlign: 'center' as const,
      padding: '48px 0',
    },
    welcomeLogo: {
      width: '64px',
      height: '64px',
      background: 'linear-gradient(135deg, #f97316, #dc2626)',
      borderRadius: '16px',
      margin: '0 auto 16px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: '32px',
    },
    welcomeTitle: {
      fontSize: '32px',
      fontWeight: '600',
      color: '#111827',
      margin: '0 0 8px 0',
    },
    welcomeSubtitle: {
      color: '#6b7280',
      margin: '0 0 32px 0',
      maxWidth: '384px',
      marginLeft: 'auto',
      marginRight: 'auto',
    },
    examplesGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
      gap: '12px',
      maxWidth: '512px',
      margin: '0 auto',
    },
    exampleCard: {
      padding: '16px',
      textAlign: 'left' as const,
      border: '1px solid #e5e7eb',
      borderRadius: '8px',
      backgroundColor: '#ffffff',
      cursor: 'pointer',
      transition: 'all 0.2s',
    },
    exampleTitle: {
      fontWeight: '500',
      color: '#111827',
      margin: '0 0 4px 0',
    },
    exampleText: {
      color: '#6b7280',
      fontSize: '14px',
      margin: 0,
    },
    messagesContainer: {
      display: 'flex',
      flexDirection: 'column' as const,
      gap: '24px',
    },
    messageRow: {
      display: 'flex',
      gap: '16px',
    },
    avatar: {
      width: '32px',
      height: '32px',
      borderRadius: '50%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: '14px',
      fontWeight: '500',
      flexShrink: 0,
    },
    userAvatar: {
      backgroundColor: '#3b82f6',
      color: 'white',
    },
    assistantAvatar: {
      background: 'linear-gradient(135deg, #f97316, #dc2626)',
      color: 'white',
    },
    messageContent: {
      flex: 1,
      paddingTop: '4px',
      minWidth: 0,
    },
    thinkingPanel: {
      backgroundColor: '#f9fafb',
      borderRadius: '8px',
      padding: '16px',
      border: '1px solid #e5e7eb',
      marginBottom: '16px',
      maxHeight: '400px',
      overflowY: 'auto' as const,
    },
    thinkingHeader: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      marginBottom: '12px',
    },
    thinkingDot: {
      width: '8px',
      height: '8px',
      backgroundColor: '#3b82f6',
      borderRadius: '50%',
      animation: 'pulse 2s infinite',
    },
    thinkingSteps: {
      display: 'flex',
      flexDirection: 'column' as const,
      gap: '8px',
    },
    thinkingStep: {
      fontSize: '14px',
      color: '#374151',
      fontFamily: 'SF Mono, Monaco, Consolas, monospace',
      backgroundColor: '#ffffff',
      borderRadius: '6px',
      padding: '8px 12px',
      border: '1px solid #e5e7eb',
      borderLeftWidth: '4px',
      lineHeight: 1.4,
    },
    messageText: {
      color: '#111827',
      lineHeight: 1.6,
      whiteSpace: 'pre-wrap' as const,
      margin: 0,
    },
    loadingIndicator: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      color: '#6b7280',
    },
    loadingDots: {
      display: 'flex',
      gap: '4px',
    },
    loadingDot: {
      width: '8px',
      height: '8px',
      backgroundColor: '#9ca3af',
      borderRadius: '50%',
      animation: 'bounce 1.5s infinite',
    },
    footer: {
      borderTop: '1px solid #e5e7eb',
      backgroundColor: '#ffffff',
      position: 'sticky' as const,
      bottom: 0,
    },
    footerContent: {
      maxWidth: '896px',
      margin: '0 auto',
      padding: '16px',
    },
    inputContainer: {
      position: 'relative' as const,
    },
    textarea: {
      width: '100%',
      resize: 'none' as const,
      border: '1px solid #d1d5db',
      borderRadius: '12px',
      padding: '12px 48px 12px 16px',
      fontSize: '16px',
      outline: 'none',
      minHeight: '48px',
      maxHeight: '128px',
      transition: 'border-color 0.2s, box-shadow 0.2s',
    },
    sendButton: {
      position: 'absolute' as const,
      right: '8px',
      top: '50%',
      transform: 'translateY(-50%)',
      width: '32px',
      height: '32px',
      backgroundColor: '#f97316',
      border: 'none',
      borderRadius: '8px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer',
      transition: 'background-color 0.2s',
    },
    footerInfo: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginTop: '8px',
      fontSize: '12px',
      color: '#6b7280',
    },
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.headerContent}>
          <div style={styles.logoSection}>
            <div style={styles.logo}>🧠</div>
            <div style={styles.titleSection}>
              <h1 style={styles.title}>StarkMatter</h1>
              <p style={styles.subtitle}>The Invisible Force Behind Everything</p>
            </div>
          </div>
          
          <div style={styles.headerRight}>
            {health && (
              <div style={styles.statusIndicator}>
                <div style={styles.statusDot} />
                <span style={{ color: '#6b7280' }}>
                  {health.tools_loaded} tools, {health.models.healthy_models.length} models
                </span>
                <span style={styles.enhancedBadge}>
                  {health.enhanced_mode ? 'ENHANCED' : 'STANDARD'}
                </span>
              </div>
            )}
            
            <button
              onClick={() => setShowThinking(!showThinking)}
              style={{
                ...styles.button,
                backgroundColor: showThinking ? '#f3f4f6' : '#ffffff',
              }}
              onMouseEnter={(e) => {
                if (!showThinking) e.currentTarget.style.backgroundColor = '#f9fafb';
              }}
              onMouseLeave={(e) => {
                if (!showThinking) e.currentTarget.style.backgroundColor = '#ffffff';
              }}
            >
              {showThinking ? 'Hide' : 'Show'} Thinking
            </button>
          </div>
        </div>
      </header>

      {/* Messages */}
      <main style={styles.main}>
        {messages.length === 0 ? (
          <div style={styles.welcomeScreen}>
            <div style={styles.welcomeLogo}>🧠</div>
            <h2 style={styles.welcomeTitle}>Hello! I'm StarkMatter</h2>
            <p style={styles.welcomeSubtitle}>
              The invisible force behind everything. I can help you with file operations, web research, data analysis, and more. Watch me think in real-time!
            </p>
            
            <div style={styles.examplesGrid}>
              {[
                'How many stars are there in the solar system?',
                'Count files in my home directory',
                'Find the most recent file in ~/Downloads',
                'What is the capital of France?'
              ].map((example, idx) => (
                <button
                  key={idx}
                  onClick={() => setInput(example)}
                  style={styles.exampleCard}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#d1d5db';
                    e.currentTarget.style.backgroundColor = '#f9fafb';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#e5e7eb';
                    e.currentTarget.style.backgroundColor = '#ffffff';
                  }}
                >
                  <div style={styles.exampleTitle}>Try asking:</div>
                  <div style={styles.exampleText}>"{example}"</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={styles.messagesContainer}>
            {messages.map((message) => (
              <div key={message.id}>
                {message.type === 'user' ? (
                  <div style={styles.messageRow}>
                    <div style={{ ...styles.avatar, ...styles.userAvatar }}>You</div>
                    <div style={styles.messageContent}>
                      <p style={styles.messageText}>{message.content}</p>
                    </div>
                  </div>
                ) : (
                  <div style={styles.messageRow}>
                    <div style={{ ...styles.avatar, ...styles.assistantAvatar }}>🧠</div>
                    <div style={styles.messageContent}>
                      {showThinking && message.thinking && message.thinking.length > 0 && (
                        <div style={styles.thinkingPanel}>
                          <div style={styles.thinkingHeader}>
                            <div style={styles.thinkingDot} />
                            <span style={{ fontSize: '14px', fontWeight: '500', color: '#374151' }}>
                              Agent Thinking {message.isStreaming ? '(Live)' : '(Complete)'}
                            </span>
                          </div>
                          <div style={styles.thinkingSteps}>
                            {message.thinking.slice(-10)
                              .map((step, idx) => ({ step, idx, formatted: formatThinkingData(step) }))
                              .filter(item => item.formatted !== null)
                              .map(({ step, idx, formatted }) => (
                                <div 
                                  key={idx} 
                                  style={{
                                    ...styles.thinkingStep,
                                    borderLeftColor: getThinkingStepColor(step)
                                  }}
                                >
                                  {formatted}
                                </div>
                              ))}
                          </div>
                        </div>
                      )}
                      
                      {message.isStreaming ? (
                        <div style={styles.loadingIndicator}>
                          <div style={styles.loadingDots}>
                            <div style={{ ...styles.loadingDot, animationDelay: '0s' }} />
                            <div style={{ ...styles.loadingDot, animationDelay: '0.1s' }} />
                            <div style={{ ...styles.loadingDot, animationDelay: '0.2s' }} />
                          </div>
                          <span style={{ fontSize: '14px' }}>Processing...</span>
                        </div>
                      ) : (
                        <p style={styles.messageText}>{message.content}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      {/* Input */}
      <footer style={styles.footer}>
        <div style={styles.footerContent}>
          <form onSubmit={handleSubmit} style={styles.inputContainer}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask me anything... (Press Enter to send, Shift+Enter for new line)"
              style={{
                ...styles.textarea,
                borderColor: '#d1d5db',
                boxShadow: 'none',
              }}
              disabled={isStreaming}
              onFocus={(e) => {
                e.target.style.borderColor = '#f97316';
                e.target.style.boxShadow = '0 0 0 3px rgba(249, 115, 22, 0.1)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = '#d1d5db';
                e.target.style.boxShadow = 'none';
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = 'auto';
                target.style.height = `${Math.min(target.scrollHeight, 128)}px`;
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || isStreaming}
              style={{
                ...styles.sendButton,
                backgroundColor: isStreaming || !input.trim() ? '#d1d5db' : '#f97316',
                cursor: isStreaming || !input.trim() ? 'not-allowed' : 'pointer',
              }}
              onMouseEnter={(e) => {
                if (!isStreaming && input.trim()) {
                  e.currentTarget.style.backgroundColor = '#ea580c';
                }
              }}
              onMouseLeave={(e) => {
                if (!isStreaming && input.trim()) {
                  e.currentTarget.style.backgroundColor = '#f97316';
                }
              }}
            >
              {isStreaming ? (
                <div style={{
                  width: '16px',
                  height: '16px',
                  border: '2px solid white',
                  borderTop: '2px solid transparent',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite',
                }} />
              ) : (
                <svg width="16" height="16" fill="white" viewBox="0 0 24 24">
                  <path d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
                </svg>
              )}
            </button>
          </form>
          
          <div style={styles.footerInfo}>
            <span>StarkMatter - The Invisible Force Behind Everything</span>
            <span>{health?.ok ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </footer>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        
        @keyframes bounce {
          0%, 20%, 53%, 80%, 100% { transform: translateY(0); }
          40%, 43% { transform: translateY(-8px); }
          70% { transform: translateY(-4px); }
          90% { transform: translateY(-2px); }
        }
        
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

export default App;