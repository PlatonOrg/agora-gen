import { Component, Input, Output, EventEmitter, OnDestroy, Inject, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ComponentMetadata } from '../../services/components-metadata.service';

const TOOLTIP_WIDTH = 240;
const TOOLTIP_OFFSET = 10;
const SCREEN_MARGIN = 8;

@Component({
  selector: 'app-components-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './components-panel.component.html',
  styleUrls: ['./components-panel.component.scss']
})
export class ComponentsPanelComponent implements OnDestroy {
  @Input({ required: true }) formulaireComponents!: ComponentMetadata[];
  @Input({ required: true }) widgetComponents!: ComponentMetadata[];

  @Output() addComponent = new EventEmitter<string>();
  @Output() toggleTooltip = new EventEmitter<{ name: string; event: MouseEvent }>();

  private tooltipEl: HTMLElement | null = null;
  private readonly isBrowser: boolean;

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnDestroy(): void {
    this.removeTooltipEl();
  }

  protected onDragStart(event: DragEvent, componentName: string, category: 'Formulaire' | 'Widget'): void {
    if (!event.dataTransfer) return;
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData('application/json', JSON.stringify({
      type: 'component',
      name: componentName,
      category,
    }));
  }

  protected showTooltip(event: MouseEvent, comp: ComponentMetadata): void {
    if (!this.isBrowser) return;
    const fullDescription = comp.description || '';
    const firstSentence = fullDescription.split('.')[0]?.trim() || fullDescription;
    const text = firstSentence ? firstSentence + '.' : '';
    if (!text) return;

    this.removeTooltipEl();

    const el = document.createElement('div');
    el.className = 'comp-global-tooltip';

    const textSpan = document.createElement('span');
    textSpan.className = 'comp-global-tooltip__text';
    textSpan.textContent = text;
    el.appendChild(textSpan);

    const arrow = document.createElement('span');
    arrow.className = 'comp-global-tooltip__arrow';
    el.appendChild(arrow);

    document.body.appendChild(el);
    this.tooltipEl = el;

    this.positionTooltip(event.currentTarget as HTMLElement);
  }

  protected hideTooltip(): void {
    this.removeTooltipEl();
  }

  private positionTooltip(anchor: HTMLElement): void {
    if (!this.tooltipEl) return;

    const rect = anchor.getBoundingClientRect();
    const tooltipH = this.tooltipEl.offsetHeight || 50;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = rect.left + rect.width / 2 - TOOLTIP_WIDTH / 2;
    let top = rect.top - tooltipH - TOOLTIP_OFFSET;
    let arrowBelow = true;

    if (top < SCREEN_MARGIN) {
      top = rect.bottom + TOOLTIP_OFFSET;
      arrowBelow = false;
    }

    left = Math.max(SCREEN_MARGIN, Math.min(left, vw - TOOLTIP_WIDTH - SCREEN_MARGIN));
    top = Math.max(SCREEN_MARGIN, Math.min(top, vh - tooltipH - SCREEN_MARGIN));

    this.tooltipEl.style.left = `${left}px`;
    this.tooltipEl.style.top = `${top}px`;
    this.tooltipEl.style.width = `${TOOLTIP_WIDTH}px`;

    const arrow = this.tooltipEl.querySelector('.comp-global-tooltip__arrow') as HTMLElement | null;
    if (arrow) {
      if (arrowBelow) {
        arrow.classList.add('comp-global-tooltip__arrow--below');
        arrow.classList.remove('comp-global-tooltip__arrow--above');
      } else {
        arrow.classList.add('comp-global-tooltip__arrow--above');
        arrow.classList.remove('comp-global-tooltip__arrow--below');
      }
      const arrowLeft = rect.left + rect.width / 2 - left;
      const clampedArrow = Math.max(10, Math.min(arrowLeft, TOOLTIP_WIDTH - 10));
      arrow.style.left = `${clampedArrow}px`;
    }
  }

  private removeTooltipEl(): void {
    if (this.tooltipEl) {
      this.tooltipEl.remove();
      this.tooltipEl = null;
    }
  }

  protected docUrl(comp: ComponentMetadata): string {
    if (comp.doc_path) {
      const withoutExt = comp.doc_path.replace(/\.mdx$/, '');
      return `https://platon.univ-eiffel.fr/docs/${withoutExt}`;
    }
    const type = comp.category === 'Formulaire' ? 'forms' : 'widgets';
    return `https://platon.univ-eiffel.fr/docs/components/${type}/${comp.tag}`;
  }
}
