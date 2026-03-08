import { Injectable, inject } from '@angular/core';
import { ExerciseData } from '../models/exercise.model';
import { ExerciseService } from '../services/exercise.service';

const STORAGE_KEY_EXERCISE_ID = 'exercise_id';
const LOCAL_CACHE_PREFIX = 'exercise_state_local:';
const AUTOSAVE_DELAY_MS = 250;

@Injectable({ providedIn: 'root' })
export class WorkspaceAutosaveService {
  private readonly exerciseService = inject(ExerciseService);

  private autosaveTimer: ReturnType<typeof setTimeout> | null = null;
  private lastSerialized = '';
  private ready = false;

  getOrCreateExerciseId(): string {
    const existing = localStorage.getItem(STORAGE_KEY_EXERCISE_ID);
    if (existing) return existing;
    const newId = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY_EXERCISE_ID, newId);
    return newId;
  }

  getLocalState(exerciseId: string): ExerciseData | null {
    try {
      const raw = localStorage.getItem(`${LOCAL_CACHE_PREFIX}${exerciseId}`);
      return raw ? (JSON.parse(raw) as ExerciseData) : null;
    } catch {
      return null;
    }
  }

  saveLocalState(exerciseId: string, data: ExerciseData): void {
    try {
      localStorage.setItem(`${LOCAL_CACHE_PREFIX}${exerciseId}`, JSON.stringify(data ?? {}));
    } catch {
    }
  }

  serialize(data: ExerciseData): string {
    return JSON.stringify(data ?? {});
  }

  isChanged(data: ExerciseData): boolean {
    const s = this.serialize(data);
    if (s === this.lastSerialized) return false;
    this.lastSerialized = s;
    return true;
  }

  markReady(currentData: ExerciseData): void {
    this.ready = true;
    this.lastSerialized = this.serialize(currentData);
  }

  isReady(): boolean {
    return this.ready;
  }

  scheduleRemoteSave(exerciseId: string, data: ExerciseData): void {
    this.cancelPendingTimer();
    this.autosaveTimer = setTimeout(async () => {
      try {
        await this.exerciseService.saveExerciseState(exerciseId, data);
      } catch (err) {
        console.error('[WorkspaceAutosaveService] Autosave failed:', err);
      }
    }, AUTOSAVE_DELAY_MS);
  }

  async flushRemoteSave(exerciseId: string, data: ExerciseData): Promise<void> {
    this.cancelPendingTimer();
    try {
      await this.exerciseService.saveExerciseState(exerciseId, data, { keepalive: true });
    } catch (err) {
      console.error('[WorkspaceAutosaveService] Flush failed:', err);
    }
  }

  cancelPendingTimer(): void {
    if (this.autosaveTimer) {
      clearTimeout(this.autosaveTimer);
      this.autosaveTimer = null;
    }
  }
}
