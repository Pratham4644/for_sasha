// ============================================================================
// Platform API Client
// Standard Fetch-based client supporting same-origin /api/v1, HttpOnly cookies,
// parameter serialization, and automatic response normalization.
// ============================================================================

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    const metaEnv = typeof import.meta !== 'undefined' ? (import.meta as any).env : undefined;
    const envBase = metaEnv?.VITE_API_BASE_URL || metaEnv?.VITE_API_URL;

    this.baseUrl = baseUrl || (typeof envBase === 'string' && envBase ? envBase : '/api/v1');
  }

  private buildUrl(endpoint: string, params?: Record<string, any>): string {
    let url: string;

    if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
      url = endpoint;
    } else {
      const cleanBase = this.baseUrl.replace(/\/+$/, '');
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

      // Prevent duplicate /api/v1 if endpoint already includes base path
      if (cleanEndpoint.startsWith(cleanBase)) {
        url = cleanEndpoint;
      } else {
        url = `${cleanBase}${cleanEndpoint}`;
      }
    }

    if (params && typeof params === 'object') {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null && value !== '') {
          searchParams.append(key, String(value));
        }
      }
      const qs = searchParams.toString();
      if (qs) {
        url += (url.includes('?') ? '&' : '?') + qs;
      }
    }

    return url;
  }

  private async request<T = any>(
    endpoint: string,
    options: RequestInit = {},
    params?: Record<string, any>
  ): Promise<T> {
    const url = this.buildUrl(endpoint, params);

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    if (options.body && typeof options.body === 'string') {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include', // HttpOnly cookie authentication preservation
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      let errorData: any = null;

      try {
        errorData = await response.json();
        if (errorData) {
          if (errorData.error?.message) {
            errorMessage = errorData.error.message;
          } else if (typeof errorData.detail === 'string') {
            errorMessage = errorData.detail;
          } else if (Array.isArray(errorData.detail)) {
            errorMessage = errorData.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
          } else if (errorData.message) {
            errorMessage = errorData.message;
          }
        }
      } catch {
        // Response body was not JSON
      }

      throw new ApiError(errorMessage, response.status, errorData);
    }

    if (response.status === 204) {
      return undefined as unknown as T;
    }

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      return (await response.text()) as unknown as T;
    }

    const json = await response.json();

    // Backend wraps response in ApiResponse: { success: boolean, data?: T, ... }
    if (json && typeof json === 'object' && 'data' in json && 'success' in json) {
      if (!json.success) {
        const msg = json.error?.message || json.message || 'Operation failed';
        throw new ApiError(msg, response.status, json);
      }

      const result = json.data;

      // Normalization helpers for caller ergonomics
      if (result && typeof result === 'object' && !Array.isArray(result)) {
        if (!result.id && result.user_id) {
          result.id = result.user_id;
        }
        if (typeof result.success === 'boolean' && result.ok === undefined) {
          result.ok = result.success;
        }
      }

      return result as T;
    }

    return json as T;
  }

  public get<T = any>(endpoint: string, params?: Record<string, any>): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' }, params);
  }

  public post<T = any>(
    endpoint: string,
    data?: any,
    params?: Record<string, any>
  ): Promise<T> {
    return this.request<T>(
      endpoint,
      {
        method: 'POST',
        body: data !== undefined ? JSON.stringify(data) : undefined,
      },
      params
    );
  }

  public put<T = any>(
    endpoint: string,
    data?: any,
    params?: Record<string, any>
  ): Promise<T> {
    return this.request<T>(
      endpoint,
      {
        method: 'PUT',
        body: data !== undefined ? JSON.stringify(data) : undefined,
      },
      params
    );
  }

  public patch<T = any>(
    endpoint: string,
    data?: any,
    params?: Record<string, any>
  ): Promise<T> {
    return this.request<T>(
      endpoint,
      {
        method: 'PATCH',
        body: data !== undefined ? JSON.stringify(data) : undefined,
      },
      params
    );
  }

  public delete<T = any>(endpoint: string, params?: Record<string, any>): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' }, params);
  }

  /**
   * Downloads exported detection logs as a CSV file in the browser.
   */
  public async exportDetectionLogsCsv(params?: Record<string, any>): Promise<void> {
    const url = this.buildUrl('/detection-logs/export', params);

    const response = await fetch(url, {
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      let msg = 'Failed to export detection logs CSV';
      try {
        const errJson = await response.json();
        if (errJson?.error?.message) msg = errJson.error.message;
        else if (errJson?.detail) msg = errJson.detail;
      } catch {
        // ignore
      }
      throw new ApiError(msg, response.status);
    }

    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition');
    let filename = `cctv-detections-${new Date().toISOString().slice(0, 10)}.csv`;

    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename=["']?([^"';]+)["']?/i);
      if (match && match[1]) {
        filename = match[1].trim();
      }
    }

    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(blobUrl);
  }
}

export const api = new ApiClient();
export default api;
