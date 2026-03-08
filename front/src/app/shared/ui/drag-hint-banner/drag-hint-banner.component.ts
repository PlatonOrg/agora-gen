import { Component, ChangeDetectionStrategy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { OnboardingService } from '../../../features/workspace/services/onboarding.service';

@Component({
  selector: 'app-drag-hint-banner',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './drag-hint-banner.component.html',
  styleUrl: './drag-hint-banner.component.scss',
})
export class DragHintBannerComponent {
  protected readonly onboarding = inject(OnboardingService);

  protected dismiss(): void {
    this.onboarding.dismissDragHint();
  }
}



