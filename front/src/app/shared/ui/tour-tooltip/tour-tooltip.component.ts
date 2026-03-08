import {
  Component, Input, Output, EventEmitter, AfterViewInit,
  OnDestroy, OnChanges, SimpleChanges, ElementRef,
  ChangeDetectionStrategy, PLATFORM_ID, Inject,
  ChangeDetectorRef, NgZone,
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { TourStep } from '../../../features/workspace/services/onboarding.service';

@Component({
  selector: 'app-tour-tooltip',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './tour-tooltip.component.html',
  styleUrl: './tour-tooltip.component.scss',
})
export class TourTooltipComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input({ required: true }) step!: TourStep;
  @Input({ required: true }) progressLabel!: string;
  @Input({ required: true }) isLastStep!: boolean;
  @Input() totalSteps = 1;
  @Input() currentStepIndex = 0;
  @Output() nextStep = new EventEmitter<void>();
  @Output() skipTour = new EventEmitter<void>();

  protected tooltipStyle: Record<string, string> = {};
  protected arrowClass = '';
  protected spotlightRect = { x: 0, y: 0, w: 0, h: 0, r: 8 };
  protected svgW = 0;
  protected svgH = 0;

  private readonly isBrowser: boolean;
  private resizeObserver: ResizeObserver | null = null;
  private repositionTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly host: ElementRef<HTMLElement>,
    private readonly cdr: ChangeDetectorRef,
    private readonly zone: NgZone,
    @Inject(PLATFORM_ID) platformId: object,
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngAfterViewInit(): void {
    this.scheduleReposition();
    if (this.isBrowser && typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => {
        this.scheduleReposition();
      });
      this.resizeObserver.observe(document.body);
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['step'] || changes['currentStepIndex']) {
      this.scheduleReposition();
    }
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    if (this.repositionTimer) clearTimeout(this.repositionTimer);
  }

  private scheduleReposition(): void {
    if (this.repositionTimer) clearTimeout(this.repositionTimer);
    this.repositionTimer = setTimeout(() => {
      this.positionTooltip();
      this.cdr.markForCheck();
    }, 120);
  }

  protected positionTooltip(): void {
    if (!this.isBrowser) return;

    const vp = { w: window.innerWidth, h: window.innerHeight };
    this.svgW = vp.w;
    this.svgH = vp.h;

    const target = document.querySelector(this.step.targetSelector) as HTMLElement | null;
    const el = this.host.nativeElement.querySelector('.tour-card') as HTMLElement | null;

    if (!target) {
      this.spotlightRect = { x: vp.w / 2 - 120, y: vp.h / 2 - 50, w: 240, h: 100, r: 10 };
      const tw = el?.offsetWidth || 340;
      const th = el?.offsetHeight || 200;
      this.tooltipStyle = {
        top: `${Math.round(vp.h / 2 - th / 2)}px`,
        left: `${Math.round(vp.w / 2 - tw / 2)}px`,
      };
      this.arrowClass = '';
      return;
    }

    const rect = target.getBoundingClientRect();
    this.spotlightRect = {
      x: rect.left,
      y: rect.top,
      w: rect.width,
      h: rect.height,
      r: 0,
    };

    const tw = el?.offsetWidth || 340;
    const th = el?.offsetHeight || 200;
    const gap = 12;
    const edge = 12;

    type Placement = { top: number; left: number; arrow: string };

    const placements: Record<string, () => Placement> = {
      right: () => ({
        top: rect.top + rect.height / 2 - th / 2,
        left: rect.right + gap,
        arrow: 'arrow-left',
      }),
      left: () => ({
        top: rect.top + rect.height / 2 - th / 2,
        left: rect.left - gap - tw,
        arrow: 'arrow-right',
      }),
      bottom: () => ({
        top: rect.bottom + gap,
        left: rect.left + rect.width / 2 - tw / 2,
        arrow: 'arrow-top',
      }),
      top: () => ({
        top: rect.top - gap - th,
        left: rect.left + rect.width / 2 - tw / 2,
        arrow: 'arrow-bottom',
      }),
    };

    const fits = (p: Placement): boolean =>
      p.top >= edge && p.left >= edge &&
      p.top + th <= vp.h - edge && p.left + tw <= vp.w - edge;

    const preferred = this.step.position;
    const fallbackOrder = ['right', 'bottom', 'left', 'top'];
    const tryOrder = [preferred, ...fallbackOrder.filter(d => d !== preferred)];

    let chosen: Placement | null = null;
    for (const dir of tryOrder) {
      const p = placements[dir]();
      if (fits(p)) { chosen = p; break; }
    }

    if (!chosen) {
      chosen = placements[preferred]();
    }

    chosen.top = Math.max(edge, Math.min(chosen.top, vp.h - th - edge));
    chosen.left = Math.max(edge, Math.min(chosen.left, vp.w - tw - edge));

    this.tooltipStyle = {
      top: `${Math.round(chosen.top)}px`,
      left: `${Math.round(chosen.left)}px`,
    };
    this.arrowClass = chosen.arrow;
  }

  get progressPercent(): number {
    if (this.totalSteps <= 1) return 100;
    return ((this.currentStepIndex + 1) / this.totalSteps) * 100;
  }
}
