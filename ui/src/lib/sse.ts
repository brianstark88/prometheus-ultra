import type { SSEEvent } from '../types';

export interface SSEOptions {
  onEvent?: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  onOpen?: () => void;
  onClose?: () => void;
  retryInterval?: number;
  maxRetries?: number;
}

interface ThinkingStep {
  thought: string;
  step_type: string;
  timestamp: number;
}

export class SSEClient {
  private eventSource: EventSource | null = null;
  private url: string;
  private options: SSEOptions;
  private retryCount = 0;
  private isConnected = false;
  private abortController: AbortController | null = null;

  constructor(url: string, options: SSEOptions = {}) {
    this.url = url;
    this.options = {
      retryInterval: 3000,
      maxRetries: 5,
      ...options,
    };
  }

  connect(): void {
    if (this.isConnected) {
      return;
    }

    this.abortController = new AbortController();

    try {
      this.eventSource = new EventSource(this.url);
      
      this.eventSource.onopen = () => {
        this.isConnected = true;
        this.retryCount = 0;
        this.options.onOpen?.();
      };

      this.eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const sseEvent: SSEEvent = {
            event: event.type || 'message',
            data,
          };
          this.options.onEvent?.(sseEvent);
        } catch (error) {
          console.error('Failed to parse SSE message:', error);
        }
      };

      // Handle different event types
      const eventTypes = [
        'status', 'plan', 'critic', 'exec', 'obs', 'hyp', 'bb', 'met', 'final', 'error', 'cancel'
      ];

      eventTypes.forEach(type => {
        this.eventSource?.addEventListener(type, (event) => {
          try {
            const data = JSON.parse((event as MessageEvent).data);
            const sseEvent: SSEEvent = {
              event: type,
              data,
            };
            this.options.onEvent?.(sseEvent);
          } catch (error) {
            console.error(`Failed to parse ${type} event:`, error);
          }
        });
      });

      this.eventSource.onerror = (event) => {
        this.isConnected = false;
        
        // Check if it's a network error or server closed connection
        if (this.eventSource?.readyState === EventSource.CLOSED) {
          this.options.onClose?.();
          return;
        }

        const error = new Error('SSE connection error');
        this.options.onError?.(error);

        // Auto-retry with exponential backoff
        if (this.retryCount < (this.options.maxRetries || 5)) {
          this.retryCount++;
          const delay = Math.min(
            (this.options.retryInterval || 3000) * Math.pow(2, this.retryCount - 1),
            30000 // Max 30 seconds
          );
          
          setTimeout(() => {
            if (!this.abortController?.signal.aborted) {
              this.disconnect();
              this.connect();
            }
          }, delay);
        }
      };

    } catch (error) {
      this.options.onError?.(error as Error);
    }
  }

  disconnect(): void {
    this.isConnected = false;
    this.abortController?.abort();
    
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  isActive(): boolean {
    return this.isConnected && this.eventSource?.readyState === EventSource.OPEN;
  }

  getReadyState(): number {
    return this.eventSource?.readyState ?? EventSource.CLOSED;
  }
}

// Utility function to create SSE URL with parameters
export function createSSEUrl(baseUrl: string, endpoint: string, params: Record<string, string>): string {
  const url = new URL(endpoint, baseUrl);
  Object.entries(params).forEach(([key, value]) => {
    url.searchParams.append(key, value);
  });
  return url.toString();
}

// Hook for using SSE in React components
export function useSSEConnection(url: string, options: SSEOptions = {}) {
  const [client, setClient] = React.useState<SSEClient | null>(null);
  const [isConnected, setIsConnected] = React.useState(false);
  const [error, setError] = React.useState<Error | null>(null);

  React.useEffect(() => {
    if (!url) return;

    const sseClient = new SSEClient(url, {
      ...options,
      onOpen: () => {
        setIsConnected(true);
        setError(null);
        options.onOpen?.();
      },
      onClose: () => {
        setIsConnected(false);
        options.onClose?.();
      },
      onError: (err) => {
        setError(err);
        options.onError?.(err);
      },
      onEvent: options.onEvent,
    });

    setClient(sseClient);
    sseClient.connect();

    return () => {
      sseClient.disconnect();
    };
  }, [url]);

  const disconnect = React.useCallback(() => {
    client?.disconnect();
    setIsConnected(false);
  }, [client]);

  return {
    client,
    isConnected,
    error,
    disconnect,
  };
}