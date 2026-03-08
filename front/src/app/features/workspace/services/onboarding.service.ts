import { Injectable, signal, computed, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

export interface TourStep {
  id: string;
  title: string;
  body: string;
  targetSelector: string;
  position: 'top' | 'bottom' | 'left' | 'right';
  action?: () => void;
}

const STORAGE_KEY = 'agora_onboarding_seen_v1';
const DRAG_HINT_KEY = 'agora_drag_hint_dismissed_v1';

@Injectable({ providedIn: 'root' })
export class OnboardingService {
  private readonly isBrowser: boolean;

  private readonly _isActive = signal(false);
  private readonly _currentStepIndex = signal(0);
  private readonly _hasSeen = signal(false);
  private readonly _showDragHint = signal(false);

  readonly isActive = this._isActive.asReadonly();
  readonly hasSeen = this._hasSeen.asReadonly();
  readonly currentStepIndex = this._currentStepIndex.asReadonly();
  readonly showDragHint = this._showDragHint.asReadonly();

  readonly currentStep = computed<TourStep | null>(() => {
    const steps = this.steps;
    const idx = this._currentStepIndex();
    return idx < steps.length ? steps[idx] : null;
  });

  readonly isLastStep = computed(() => {
    return this._currentStepIndex() >= this.steps.length - 1;
  });

  readonly progressLabel = computed(() => {
    return `${this._currentStepIndex() + 1} / ${this.steps.length}`;
  });

  readonly steps: TourStep[] = [];

  constructor(@Inject(PLATFORM_ID) platformId: object) {
    this.isBrowser = isPlatformBrowser(platformId);
    if (this.isBrowser) {
      this._hasSeen.set(!!localStorage.getItem(STORAGE_KEY));
      this._showDragHint.set(!localStorage.getItem(DRAG_HINT_KEY));
    }
  }

  registerSteps(steps: TourStep[]): void {
    (this.steps as TourStep[]).length = 0;
    (this.steps as TourStep[]).push(...steps);
  }

  startIfFirstVisit(): void {
    if (!this.isBrowser) return;
    if (this._hasSeen()) return;
    this.start();
  }

  start(): void {
    this._currentStepIndex.set(0);
    this._isActive.set(true);
    const first = this.steps[0];
    if (first?.action) {
      first.action();
    }
  }

  next(): void {
    const nextIndex = this._currentStepIndex() + 1;
    if (nextIndex >= this.steps.length) {
      this.complete();
    } else {
      const step = this.steps[nextIndex];
      if (step?.action) {
        step.action();
      }
      this._currentStepIndex.set(nextIndex);
    }
  }

  skip(): void {
    this.complete();
  }

  private complete(): void {
    this._isActive.set(false);
    this._hasSeen.set(true);
    if (this.isBrowser) {
      localStorage.setItem(STORAGE_KEY, '1');
    }
  }

  dismissDragHint(): void {
    this._showDragHint.set(false);
    if (this.isBrowser) {
      localStorage.setItem(DRAG_HINT_KEY, '1');
    }
  }

  reset(): void {
    if (this.isBrowser) {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(DRAG_HINT_KEY);
    }
    this._hasSeen.set(false);
    this._showDragHint.set(true);
  }
}






