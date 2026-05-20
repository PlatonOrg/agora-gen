import { Injectable, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly API_BASE_URL = '/api/v1';
  private readonly isBrowser: boolean;

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  private buildHeaders(): HeadersInit {
    return { 'Content-Type': 'application/json' };
  }

  private resolveUrl(endpoint: string): string {
    return `${this.API_BASE_URL}${endpoint}`;
  }

  private guardSSR(endpoint: string): void {
    if (!this.isBrowser) {
      throw new Error(`[ApiService] SSR: cannot fetch ${endpoint}`);
    }
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      console.error('[ApiService] error:', error);
      throw new Error(error.error || `HTTP ${response.status}`);
    }
    const data = await response.json();
    console.log('[ApiService] response:', data);
    return data as T;
  }

  async get<T>(endpoint: string): Promise<T> {
    this.guardSSR(endpoint);
    const url = this.resolveUrl(endpoint);
    console.log('[ApiService] GET', url);
    const response = await fetch(url, { method: 'GET', headers: this.buildHeaders(), credentials: 'include' });
    return this.handleResponse<T>(response);
  }

  async post<T>(endpoint: string, body: unknown): Promise<T> {
    this.guardSSR(endpoint);
    const url = this.resolveUrl(endpoint);
    console.log('[ApiService] POST', url);
    const response = await fetch(url, { method: 'POST', headers: this.buildHeaders(), credentials: 'include', body: JSON.stringify(body) });
    return this.handleResponse<T>(response);
  }

  async put<T>(endpoint: string, body: unknown): Promise<T> {
    this.guardSSR(endpoint);
    const url = this.resolveUrl(endpoint);
    console.log('[ApiService] PUT', url);
    const response = await fetch(url, { method: 'PUT', headers: this.buildHeaders(), credentials: 'include', body: JSON.stringify(body) });
    return this.handleResponse<T>(response);
  }

  async patch<T>(endpoint: string, body: unknown): Promise<T> {
    this.guardSSR(endpoint);
    const url = this.resolveUrl(endpoint);
    console.log('[ApiService] PATCH', url);
    const response = await fetch(url, { method: 'PATCH', headers: this.buildHeaders(), credentials: 'include', body: JSON.stringify(body) });
    return this.handleResponse<T>(response);
  }

  async delete<T>(endpoint: string): Promise<T> {
    this.guardSSR(endpoint);
    const url = this.resolveUrl(endpoint);
    console.log('[ApiService] DELETE', url);
    const response = await fetch(url, { method: 'DELETE', headers: this.buildHeaders(), credentials: 'include' });
    return this.handleResponse<T>(response);
  }
}

