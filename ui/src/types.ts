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
  goal: string;
  startTime: number;
}
