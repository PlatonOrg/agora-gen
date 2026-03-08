import { Message, CachedMessage, DiscussionCachePayload } from './discussion.models';

export class DiscussionCache {
  private readonly prefix = 'exercise_discussion_local:';
  private readonly fallbackKey = 'exercise_discussion_local:default';
  private currentKey: string;

  constructor(private readonly isBrowser: boolean) {
    this.currentKey = this.fallbackKey;
  }

  init(): void {
    if (!this.isBrowser) return;
    const id = localStorage.getItem('exercise_id');
    this.currentKey = id ? `${this.prefix}${id}` : this.fallbackKey;
  }

  refresh(): void {
    if (!this.isBrowser) return;
    const id = localStorage.getItem('exercise_id');
    this.currentKey = id ? `${this.prefix}${id}` : this.fallbackKey;
  }

  read(): DiscussionCachePayload | null {
    if (!this.isBrowser) return null;
    return this._readKey(this.currentKey) ?? this._readKey(this.fallbackKey);
  }

  write(payload: DiscussionCachePayload): void {
    if (!this.isBrowser) return;
    try {
      localStorage.setItem(this.currentKey, JSON.stringify(payload));
    } catch (e) {
      console.warn('[DiscussionCache] Write failed:', e);
    }
  }

  private _readKey(key: string): DiscussionCachePayload | null {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) as DiscussionCachePayload : null;
    } catch (e) {
      console.warn('[DiscussionCache] Read failed for key', key, e);
      return null;
    }
  }

  serializeMessages(messages: Message[]): CachedMessage[] {
    return messages.map(m => ({
      ...m,
      timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : new Date(m.timestamp).toISOString(),
    }));
  }

  deserializeMessages(messages: CachedMessage[] | undefined): Message[] {
    if (!Array.isArray(messages)) return [];
    return messages
      .filter(m => !!m && typeof m.id === 'string')
      .map(m => ({ ...m, timestamp: new Date(m.timestamp) }));
  }
}

