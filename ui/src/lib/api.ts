import type { HealthStatus, Tool, SystemMetrics } from '../types';

export class APIClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl.replace(/\/$/, ''); // Remove trailing slash
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API Error: ${response.status} - ${errorText}`);
    }

    return response.json();
  }

  // Health check
  async getHealth(): Promise<HealthStatus> {
    return this.request<HealthStatus>('/health');
  }

  // Tools
  async getTools(): Promise<{ tools: Record<string, Tool>; count: number }> {
    return this.request('/tools');
  }

  // System metrics
  async getSystemMetrics(): Promise<SystemMetrics> {
    return this.request<SystemMetrics>('/metrics');
  }

  // Session management
  async exportSession(sessionId: string): Promise<any> {
    return this.request(`/sessions/${sessionId}/export`);
  }

  async cancelSession(sessionId: string): Promise<{ cancelled: boolean; session_id: string }> {
    return this.request(`/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  async confirmDestructive(sessionId: string, action: string): Promise<any> {
    return this.request(`/confirm/${sessionId}`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  }

  // Create SSE stream URL
  createStreamUrl(params: {
    goal: string;
    max_steps?: number;
    destructive?: boolean;
    session_id?: string;
  }): string {
    const url = new URL('/auto/stream', this.baseUrl);
    
    url.searchParams.append('goal', params.goal);
    if (params.max_steps) {
      url.searchParams.append('max_steps', params.max_steps.toString());
    }
    if (params.destructive) {
      url.searchParams.append('destructive', 'true');
    }
    if (params.session_id) {
      url.searchParams.append('session_id', params.session_id);
    }
    
    return url.toString();
  }

  // Update base URL
  setBaseUrl(baseUrl: string): void {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }
}

// Global API client instance
export const apiClient = new APIClient();

// Hook for API client with settings
export function useAPIClient() {
  const [client] = React.useState(() => apiClient);
  
  const updateBaseUrl = React.useCallback((baseUrl: string) => {
    client.setBaseUrl(baseUrl);
  }, [client]);

  return {
    client,
    updateBaseUrl,
  };
}