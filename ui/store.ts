import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { 
  SessionState, 
  Message, 
  ThinkingStep, 
  UISettings, 
  SystemMetrics, 
  SessionMetrics,
  ComposerState,
  EventTimelineItem
} from '../types';

interface AppState {
  // Session Management
  currentSession: SessionState | null;
  sessions: Record<string, SessionState>;
  
  // UI State
  settings: UISettings;
  sidebarOpen: boolean;
  thinkingPanelOpen: boolean;
  
  // Metrics
  systemMetrics: SystemMetrics | null;
  sessionMetrics: SessionMetrics | null;
  
  // Composer
  composer: ComposerState;
  
  // Actions
  createSession: (goal: string) => string;
  updateSession: (sessionId: string, updates: Partial<SessionState>) => void;
  addMessage: (sessionId: string, message: Omit<Message, 'id' | 'timestamp'>) => void;
  addThinkingStep: (sessionId: string, step: Omit<ThinkingStep, 'timestamp'>) => void;
  updateThinkingStep: (sessionId: string, stepIndex: number, updates: Partial<ThinkingStep>) => void;
  setCurrentSession: (sessionId: string | null) => void;
  
  // UI Actions
  updateSettings: (settings: Partial<UISettings>) => void;
  toggleSidebar: () => void;
  toggleThinkingPanel: () => void;
  
  // Metrics Actions
  updateSystemMetrics: (metrics: SystemMetrics) => void;
  updateSessionMetrics: (metrics: SessionMetrics) => void;
  
  // Composer Actions
  updateComposer: (updates: Partial<ComposerState>) => void;
  resetComposer: () => void;
}

const defaultSettings: UISettings = {
  theme: 'dark',
  fontSize: 'medium',
  language: 'en',
  backendUrl: 'http://127.0.0.1:8000',
  showThinkingPanel: true,
  showMetricsBar: true,
  enableVoiceInput: false,
  enableVoiceOutput: false,
  autoScroll: true,
  ecoMode: false,
};

const defaultComposer: ComposerState = {
  input: '',
  model: 'gpt-oss:20b',
  temperature: 0.3,
  maxSteps: 15,
  destructive: false,
  isSubmitting: false,
};

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Initial state
      currentSession: null,
      sessions: {},
      settings: defaultSettings,
      sidebarOpen: true,
      thinkingPanelOpen: true,
      systemMetrics: null,
      sessionMetrics: null,
      composer: defaultComposer,

      // Session actions
      createSession: (goal: string) => {
        const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const newSession: SessionState = {
          id: sessionId,
          status: 'idle',
          messages: [],
          thinkingSteps: [],
          currentStep: 0,
          maxSteps: get().composer.maxSteps,
          goal,
          startTime: Date.now(),
        };

        set((state) => ({
          sessions: { ...state.sessions, [sessionId]: newSession },
          currentSession: newSession,
        }));

        return sessionId;
      },

      updateSession: (sessionId: string, updates: Partial<SessionState>) => {
        set((state) => {
          const session = state.sessions[sessionId];
          if (!session) return state;

          const updatedSession = { ...session, ...updates };
          const newSessions = { ...state.sessions, [sessionId]: updatedSession };

          return {
            sessions: newSessions,
            currentSession: state.currentSession?.id === sessionId ? updatedSession : state.currentSession,
          };
        });
      },

      addMessage: (sessionId: string, message: Omit<Message, 'id' | 'timestamp'>) => {
        const newMessage: Message = {
          ...message,
          id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          timestamp: Date.now(),
        };

        set((state) => {
          const session = state.sessions[sessionId];
          if (!session) return state;

          const updatedSession = {
            ...session,
            messages: [...session.messages, newMessage],
          };

          return {
            sessions: { ...state.sessions, [sessionId]: updatedSession },
            currentSession: state.currentSession?.id === sessionId ? updatedSession : state.currentSession,
          };
        });
      },

      addThinkingStep: (sessionId: string, step: Omit<ThinkingStep, 'timestamp'>) => {
        const newStep: ThinkingStep = {
          ...step,
          timestamp: Date.now(),
        };

        set((state) => {
          const session = state.sessions[sessionId];
          if (!session) return state;

          const updatedSession = {
            ...session,
            thinkingSteps: [...session.thinkingSteps, newStep],
          };

          return {
            sessions: { ...state.sessions, [sessionId]: updatedSession },
            currentSession: state.currentSession?.id === sessionId ? updatedSession : state.currentSession,
          };
        });
      },

      updateThinkingStep: (sessionId: string, stepIndex: number, updates: Partial<ThinkingStep>) => {
        set((state) => {
          const session = state.sessions[sessionId];
          if (!session || !session.thinkingSteps[stepIndex]) return state;

          const updatedSteps = [...session.thinkingSteps];
          updatedSteps[stepIndex] = { ...updatedSteps[stepIndex], ...updates };

          const updatedSession = {
            ...session,
            thinkingSteps: updatedSteps,
          };

          return {
            sessions: { ...state.sessions, [sessionId]: updatedSession },
            currentSession: state.currentSession?.id === sessionId ? updatedSession : state.currentSession,
          };
        });
      },

      setCurrentSession: (sessionId: string | null) => {
        set((state) => ({
          currentSession: sessionId ? state.sessions[sessionId] || null : null,
        }));
      },

      // UI Actions
      updateSettings: (newSettings: Partial<UISettings>) => {
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        }));
      },

      toggleSidebar: () => {
        set((state) => ({ sidebarOpen: !state.sidebarOpen }));
      },

      toggleThinkingPanel: () => {
        set((state) => ({ thinkingPanelOpen: !state.thinkingPanelOpen }));
      },

      // Metrics Actions
      updateSystemMetrics: (metrics: SystemMetrics) => {
        set({ systemMetrics: metrics });
      },

      updateSessionMetrics: (metrics: SessionMetrics) => {
        set({ sessionMetrics: metrics });
      },

      // Composer Actions
      updateComposer: (updates: Partial<ComposerState>) => {
        set((state) => ({
          composer: { ...state.composer, ...updates },
        }));
      },

      resetComposer: () => {
        set((state) => ({
          composer: { ...defaultComposer, model: state.composer.model },
        }));
      },
    }),
    {
      name: 'god-mode-agent-store',
      partialize: (state) => ({
        settings: state.settings,
        sessions: state.sessions,
        sidebarOpen: state.sidebarOpen,
        thinkingPanelOpen: state.thinkingPanelOpen,
      }),
    }
  )
);

// Utility hooks
export const useCurrentSession = () => {
  const currentSession = useAppStore((state) => state.currentSession);
  return currentSession;
};

export const useSettings = () => {
  const settings = useAppStore((state) => state.settings);
  const updateSettings = useAppStore((state) => state.updateSettings);
  return { settings, updateSettings };
};

export const useComposer = () => {
  const composer = useAppStore((state) => state.composer);
  const updateComposer = useAppStore((state) => state.updateComposer);
  const resetComposer = useAppStore((state) => state.resetComposer);
  return { composer, updateComposer, resetComposer };
};