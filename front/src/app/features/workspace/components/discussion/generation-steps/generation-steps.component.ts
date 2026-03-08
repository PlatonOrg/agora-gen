import { Component, input, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { GenerationTimelineData, GenerationTimelineDetail } from '../discussion.models';

@Component({
  selector: 'app-generation-steps',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './generation-steps.component.html',
  styleUrl: './generation-steps.component.scss',
})
export class GenerationStepsComponent {
  timeline = input.required<GenerationTimelineData>();

  protected detailsCollapsed = signal(false);

  protected isCompleted = computed(() =>
    this.timeline().steps.every(s => s.state === 'completed')
  );

  protected hasError = computed(() =>
    this.timeline().steps.some(s => s.state === 'error')
  );

  protected isStopped = computed(() =>
    this.timeline().steps.some(s => s.state === 'stopped') &&
    !this.timeline().steps.some(s => s.state === 'in_progress')
  );

  protected currentStep = computed(() => {
    const steps = this.timeline().steps;
    const inProgress = steps.find(s => s.state === 'in_progress');
    if (inProgress) return inProgress;
    const error = steps.find(s => s.state === 'error');
    if (error) return error;
    const stopped = steps.find(s => s.state === 'stopped');
    if (stopped) return stopped;
    return null;
  });

  protected hasDetails = computed(() =>
    this.timeline().details.length > 0 || this.timeline().isTyping
  );

  protected allDetails = computed((): GenerationTimelineDetail[] => {
    const d = this.timeline().details;
    if (!this.timeline().isTyping) return d;
    return [...d, {
      id: '__typing__',
      text: this.timeline().typingText,
      status: this.timeline().typingStatus,
    }];
  });

  protected toggleDetails(): void {
    this.detailsCollapsed.update(v => !v);
  }
}


