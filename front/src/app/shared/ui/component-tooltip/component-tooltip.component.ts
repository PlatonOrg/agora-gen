import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ComponentsMetadataService, ComponentMetadata } from '../../../features/workspace/services/components-metadata.service';

@Component({
  selector: 'app-component-tooltip',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="tooltip-content">
      <div class="tooltip-usage">
        <div class="tooltip-label">Description</div>
        <div class="tooltip-text">{{ firstSentence(component?.description) }}</div>
      </div>
      @if (hasVideo(component?.name)) {
        <div class="tooltip-video">
          <video
            [src]="getVideoPath(component?.name)"
            autoplay
            loop
            muted
            playsinline
            class="component-video"
            (error)="onVideoError($event)"
            (loadeddata)="onVideoLoad($event)"
          ></video>
        </div>
      }
    </div>
  `,
  styles: [`
    .tooltip-content {
      background: linear-gradient(135deg, var(--brand-background-secondary) 0%, var(--brand-background-components) 100%);
      border: 1px solid var(--brand-border-color);
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15), 0 2px 8px rgba(0, 0, 0, 0.1);
      padding: 1rem;
      font-size: 0.8125rem;
      line-height: 1.5;
      color: var(--brand-text-primary);
      width: 450px !important;
      min-width: 450px !important;
      max-width: 500px !important;
      backdrop-filter: blur(10px);
    }

    .tooltip-usage {
      margin-bottom: 0.625rem;
    }

    .tooltip-label {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--brand-color-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 0.375rem;
    }

    .tooltip-text {
      font-size: 0.8125rem;
      color: var(--brand-text-secondary);
      line-height: 1.6;
    }

    .tooltip-video {
      margin-top: 0.75rem;
      border-radius: 6px;
      overflow: hidden;
      background-color: var(--brand-background-hover);
      border: 1px solid var(--brand-border-color);
    }

    .component-video {
      max-width: 100%;
      height: auto;
      max-height: 280px;
      display: block;
      object-fit: contain;
      margin: 0 auto;
    }
  `]
})
export class ComponentTooltipComponent {
  @Input() component?: ComponentMetadata;

  private componentsMetadataService = inject(ComponentsMetadataService);

  protected firstSentence(description?: string): string {
    if (!description) return '';
    const sentence = description.split('.')[0]?.trim() || description;
    return sentence.endsWith('.') ? sentence : sentence + '.';
  }

  protected getVideoPath(componentName?: string): string {
    if (!componentName) return '';
    const normalizedName = componentName.charAt(0).toLowerCase() + componentName.slice(1);
    return this.componentsMetadataService.getVideoPath(normalizedName);
  }

  protected hasVideo(componentName?: string): boolean {
    return !!componentName;
  }

  protected onVideoError(event: Event): void {
    const video = event.target as HTMLVideoElement;
    if (video && video.parentElement) {
      video.parentElement.style.display = 'none';
    }
  }

  protected onVideoLoad(event: Event): void {
    // Video loaded successfully
  }
}
