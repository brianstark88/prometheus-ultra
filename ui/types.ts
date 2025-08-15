// UI Types for GOD-MODE Agent

export interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  metadata?: {
    model?: string;
    confidence?: number;
    steps?: number;
  };
}

export interface SSEEvent {
  event: string;
  data: {
    session_id: string;
    step: number;
    timestamp: number;
    [key: string]: any;
  };
}

export interface ThinkingStep {
  type: 'status' | 'plan' | 'critic' | 'exec' | 'obs' | 'hyp' | 'bb' | 'met' | 'final';
  step: number;
  timestamp: number;
  data: any;
  completed: boolean;
}

export interface SessionState {
  id: string;
  status: 'idle' | 'planning' | 'executing' | 'completed' | 'error';
  messages: Message[];
  thinkingSteps: ThinkingStep[];
  currentStep: number;
  maxSteps: number;
  startTime?: number;
  endTime?: number;
  goal?: string;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  gpu_temp: number;
  available_memory_gb: number;
  performance_score: number;
  under_load: boolean;
  eco_mode_recommended: boolean;
}

export interface SessionMetrics {
  session_id: string;
  duration: number;
  steps_completed: number;
  average_step_time: number;
  tool_usage: Record<string, number>;
  error_counts: Record<string, number>;
  llm_calls: number;
  token_usage: number;
  confidence_trend: number[];
}

export interface UISettings {
  theme: 'light' | 'dark' | 'auto';
  fontSize: 'small' | 'medium' | 'large';
  language: string;
  backendUrl: string;
  showThinkingPanel: boolean;
  showMetricsBar: boolean;
  enableVoiceInput: boolean;
  enableVoiceOutput: boolean;
  autoScroll: boolean;
  ecoMode: boolean;
}

export interface Tool {
  name: string;
  enabled: boolean;
  requires_confirm: boolean;
  destructive: boolean;
  description?: string;
  policy?: Record<string, any>;
}

export interface HealthStatus {
  ok: boolean;
  timestamp: number;
  tools_loaded: number;
  models: {
    ollama_host: string;
    primary_model: string;
    healthy_models: string[];
    total_models: number;
    system_healthy: boolean;
    model_details: Record<string, any>;
  };
  active_sessions: number;
}

export interface ComposerState {
  input: string;
  model: string;
  temperature: number;
  maxSteps: number;
  destructive: boolean;
  isSubmitting: boolean;
}

export interface EventTimelineItem {
  id: string;
  type: 'status' | 'plan' | 'critic' | 'exec' | 'obs' | 'hyp' | 'bb' | 'met' | 'final';
  title: string;
  description: string;
  timestamp: number;
  step: number;
  status: 'pending' | 'active' | 'completed' | 'error';
  data?: any;
}

export interface VoiceSettings {
  enabled: boolean;
  autoStart: boolean;
  language: string;
  voiceRate: number;
  voicePitch: number;
  voiceVolume: number;
}