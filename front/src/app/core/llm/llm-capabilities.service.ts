import { Injectable, signal, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

export interface UploadedFileEntry {
  file_id: string;
  filename: string;
}

@Injectable({
  providedIn: 'root'
})
export class LlmCapabilitiesService {
  private readonly API_BASE_URL = '/api/v1';

  readonly fileUploadSupported = signal<boolean>(false);
  readonly maxFiles = signal<number>(5);
  readonly sessionFileCount = signal<number>(0);
  readonly acceptedExtensions = signal<string[]>([]);

  private isBrowser: boolean;

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  async loadCapabilities(): Promise<void> {
    if (!this.isBrowser) return;

    console.log('[LlmCapabilitiesService] Loading LLM capabilities...');

    const response = await fetch(`${this.API_BASE_URL}/chat/file-support`, {
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      console.error('[LlmCapabilitiesService] Failed to load capabilities: HTTP', response.status);
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    this.fileUploadSupported.set(data.supported === true);
    if (typeof data.max_files === 'number') {
      this.maxFiles.set(data.max_files);
    }
    if (Array.isArray(data.accepted_extensions)) {
      this.acceptedExtensions.set(data.accepted_extensions as string[]);
    }
    console.log(
      '[LlmCapabilitiesService] File upload supported:', this.fileUploadSupported(),
      'max_files:', this.maxFiles(),
      'accepted_extensions:', this.acceptedExtensions().length === 0 ? '(all)' : this.acceptedExtensions(),
    );
  }

  async uploadFile(file: File): Promise<string> {
    if (!this.isBrowser) throw new Error('Cannot upload file in server context');

    console.log('[LlmCapabilitiesService] Uploading file:', file.name);

    const formData = new FormData();
    formData.append('file', file, file.name);

    const response = await fetch(`${this.API_BASE_URL}/chat/upload-file`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      console.error('[LlmCapabilitiesService] File upload failed:', error);
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log('[LlmCapabilitiesService] File uploaded, file_id:', data.file_id);
    this.sessionFileCount.update(n => n + 1);
    return data.file_id as string;
  }

  async getSessionFiles(): Promise<UploadedFileEntry[]> {
    if (!this.isBrowser) return [];

    const response = await fetch(`${this.API_BASE_URL}/chat/files`, {
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      console.warn('[LlmCapabilitiesService] Failed to get session files: HTTP', response.status);
      return [];
    }

    const data = await response.json();
    const files = (data.files ?? []) as UploadedFileEntry[];
    this.sessionFileCount.set(files.length);
    return files;
  }

  resetSessionFileCount(): void {
    this.sessionFileCount.set(0);
  }

  async deleteAllSessionFiles(): Promise<void> {
    if (!this.isBrowser) return;

    console.log('[LlmCapabilitiesService] Deleting all session files...');

    const response = await fetch(`${this.API_BASE_URL}/chat/files`, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      console.error('[LlmCapabilitiesService] Failed to delete session files:', error);
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log('[LlmCapabilitiesService] Session files deleted:', data.deleted, 'failed:', data.failed);
    this.sessionFileCount.set(0);
  }
}
