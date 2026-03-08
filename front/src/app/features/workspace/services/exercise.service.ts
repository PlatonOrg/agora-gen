import { Injectable, signal } from '@angular/core';
import { ExerciseData } from '../models/exercise.model';

@Injectable({
  providedIn: 'root'
})
export class ExerciseService {
  private readonly API_BASE_URL = '/api/v1';
  private readonly EXERCISE_BASE_URL = `${this.API_BASE_URL}/exercises`;
  exerciseData = signal<ExerciseData>({});

  /**
   * Save (upsert) exercise state
   */
  async saveExerciseState(
    exerciseId: string,
    exerciseData: ExerciseData,
    options?: { keepalive?: boolean }
  ): Promise<ExerciseData> {
    const response = await fetch(`${this.EXERCISE_BASE_URL}/state/save/${exerciseId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include',
      keepalive: options?.keepalive === true,
      body: JSON.stringify(exerciseData)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Load exercise state
   */
  async getExerciseState(exerciseId: string): Promise<ExerciseData> {
    const response = await fetch(`${this.EXERCISE_BASE_URL}/state/${exerciseId}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include'
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Delete exercise state
   */
  async clearExerciseState(exerciseId: string): Promise<ExerciseData> {
    const response = await fetch(`${this.EXERCISE_BASE_URL}/state/${exerciseId}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include'
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }
}



 
