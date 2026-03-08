import {
  Directive,
  Input,
  HostListener,
  ElementRef,
  OnDestroy,
  Inject,
  inject,
} from '@angular/core';
import { PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import {
  WorkspaceStore,
  MIN_LEFT,
  MAX_LEFT,
  MIN_RIGHT,
  MAX_RIGHT,
} from '../state/workspace.store';

@Directive({
  selector: '[appResizeHandle]',
  standalone: true,
  host: {
    '[attr.role]': '"separator"',
    '[attr.tabindex]': '"0"',
    '[attr.aria-label]': 'ariaLabel',
    '[attr.aria-valuenow]': 'ariaValueNow',
    '[attr.aria-valuemin]': 'ariaValueMin',
    '[attr.aria-valuemax]': 'ariaValueMax',
  },
})
export class ResizeHandleDirective implements OnDestroy {
  @Input('appResizeHandle') panel: 'left' | 'right' = 'left';
  @Input() panelElement!: HTMLElement;

  private readonly el = inject(ElementRef<HTMLElement>);
  private readonly wsStore = inject(WorkspaceStore);
  private readonly isBrowser: boolean;

  private dragging = false;
  private startX = 0;
  private startWidth = 0;
  private rafId: number | null = null;
  private pointerId: number | null = null;

  private boundPointerMove = this.onPointerMove.bind(this);
  private boundPointerUp = this.onPointerUp.bind(this);

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  // --- ARIA getters ---

  get ariaLabel(): string {
    return this.panel === 'left'
      ? 'Resize left panel'
      : 'Resize right panel';
  }

  get ariaValueNow(): number {
    return this.panel === 'left'
      ? this.wsStore.leftPanelWidth()
      : this.wsStore.rightPanelWidth();
  }

  get ariaValueMin(): number {
    return this.panel === 'left' ? MIN_LEFT : MIN_RIGHT;
  }

  get ariaValueMax(): number {
    return this.panel === 'left' ? MAX_LEFT : MAX_RIGHT;
  }

  // --- Pointer events ---

  @HostListener('pointerdown', ['$event'])
  onPointerDown(event: PointerEvent): void {
    if (!this.isBrowser) return;
    event.preventDefault();

    this.dragging = true;
    this.startX = event.clientX;
    this.startWidth = this.panel === 'left'
      ? this.wsStore.leftPanelWidth()
      : this.wsStore.rightPanelWidth();
    this.pointerId = event.pointerId;

    this.el.nativeElement.setPointerCapture(event.pointerId);

    document.body.classList.add('resizing');
    this.setMonacoPointerEvents('none');

    document.addEventListener('pointermove', this.boundPointerMove);
    document.addEventListener('pointerup', this.boundPointerUp);
  }

  private onPointerMove(event: PointerEvent): void {
    if (!this.dragging) return;

    if (this.rafId !== null) return;

    this.rafId = requestAnimationFrame(() => {
      this.rafId = null;
      if (!this.dragging) return;

      const delta = event.clientX - this.startX;
      let newWidth: number;

      // Calculate dynamic max width to prevent center content from being crushed
      const viewportWidth = window.innerWidth;
      const railWidths = 72; // 36px left rail + 36px right rail
      const handleWidths = 12; // 6px left handle + 6px right handle
      const MIN_CENTER = 300;

      let otherPanelWidth: number;
      if (this.panel === 'left') {
        const isRightOpen = !this.wsStore.isComponentsPanelCollapsed();
        otherPanelWidth = isRightOpen ? this.wsStore.rightPanelWidth() : 36;
      } else {
        const isLeftOpen = this.wsStore.activeLeftTab() !== null;
        otherPanelWidth = isLeftOpen ? this.wsStore.leftPanelWidth() : 36;
      }

      const dynamicMax = viewportWidth - otherPanelWidth - MIN_CENTER - railWidths - handleWidths;
      const staticMax = this.panel === 'left' ? MAX_LEFT : MAX_RIGHT;
      const minWidth = this.panel === 'left' ? MIN_LEFT : MIN_RIGHT;
      const effectiveMax = Math.min(staticMax, dynamicMax);

      if (this.panel === 'left') {
        newWidth = this.startWidth + delta;
        newWidth = Math.max(minWidth, Math.min(effectiveMax, newWidth));
        this.wsStore.leftPanelWidth.set(newWidth);
      } else {
        // Right panel: dragging left increases width, dragging right decreases
        newWidth = this.startWidth - delta;
        newWidth = Math.max(minWidth, Math.min(effectiveMax, newWidth));
        this.wsStore.rightPanelWidth.set(newWidth);
      }
    });
  }

  private onPointerUp(event: PointerEvent): void {
    if (!this.dragging) return;

    this.dragging = false;

    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }

    if (this.pointerId !== null) {
      try {
        this.el.nativeElement.releasePointerCapture(this.pointerId);
      } catch {
        // Pointer capture may already be released
      }
      this.pointerId = null;
    }

    document.body.classList.remove('resizing');
    this.setMonacoPointerEvents('');

    document.removeEventListener('pointermove', this.boundPointerMove);
    document.removeEventListener('pointerup', this.boundPointerUp);

    this.wsStore.persistPanelWidths();
    window.dispatchEvent(new Event('resize'));
  }

  // --- Keyboard accessibility ---

  @HostListener('keydown', ['$event'])
  onKeyDown(event: KeyboardEvent): void {
    if (!this.isBrowser) return;

    const step = 10;
    let currentWidth: number;
    let newWidth: number;

    if (this.panel === 'left') {
      currentWidth = this.wsStore.leftPanelWidth();
      if (event.key === 'ArrowRight') {
        newWidth = Math.min(MAX_LEFT, currentWidth + step);
      } else if (event.key === 'ArrowLeft') {
        newWidth = Math.max(MIN_LEFT, currentWidth - step);
      } else {
        return;
      }
      this.wsStore.leftPanelWidth.set(newWidth);
    } else {
      currentWidth = this.wsStore.rightPanelWidth();
      if (event.key === 'ArrowLeft') {
        newWidth = Math.min(MAX_RIGHT, currentWidth + step);
      } else if (event.key === 'ArrowRight') {
        newWidth = Math.max(MIN_RIGHT, currentWidth - step);
      } else {
        return;
      }
      this.wsStore.rightPanelWidth.set(newWidth);
    }

    event.preventDefault();
    this.wsStore.persistPanelWidths();
    window.dispatchEvent(new Event('resize'));
  }

  // --- Helpers ---

  private setMonacoPointerEvents(value: string): void {
    if (!this.isBrowser) return;
    const monacoElements = document.querySelectorAll<HTMLElement>('.exc-monaco-wrap');
    monacoElements.forEach(el => {
      el.style.pointerEvents = value;
    });
  }

  ngOnDestroy(): void {
    if (this.dragging) {
      this.onPointerUp(new PointerEvent('pointerup'));
    }
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
    }
    if (this.isBrowser) {
      document.removeEventListener('pointermove', this.boundPointerMove);
      document.removeEventListener('pointerup', this.boundPointerUp);
    }
}
}
