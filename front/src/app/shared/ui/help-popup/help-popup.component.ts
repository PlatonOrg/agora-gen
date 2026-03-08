import {
  Component, Input, signal, HostListener, ElementRef, ChangeDetectionStrategy,
  ChangeDetectorRef, PLATFORM_ID, Inject, OnDestroy, Renderer2,
} from '@angular/core';
import { CommonModule, isPlatformBrowser, DOCUMENT } from '@angular/common';

@Component({
  selector: 'app-help-popup',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './help-popup.component.html',
  styleUrl: './help-popup.component.scss',
})
export class HelpPopupComponent implements OnDestroy {
  @Input({ required: true }) title!: string;
  @Input({ required: true }) markdownContent!: string;

  protected readonly isOpen = signal(false);

  private readonly isBrowser: boolean;
  private portalEl: HTMLElement | null = null;
  private readonly doc: Document;

  constructor(
    private readonly host: ElementRef<HTMLElement>,
    private readonly cdr: ChangeDetectorRef,
    private readonly renderer: Renderer2,
    @Inject(PLATFORM_ID) platformId: object,
    @Inject(DOCUMENT) doc: Document,
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
    this.doc = doc;
  }

  ngOnDestroy(): void {
    this.destroyPortal();
  }

  protected toggle(): void {
    if (this.isOpen()) {
      this.close();
    } else {
      this.isOpen.set(true);
      if (this.isBrowser) {
        requestAnimationFrame(() => this.createPortal());
      }
    }
  }

  protected close(): void {
    this.isOpen.set(false);
    this.destroyPortal();
  }

  private createPortal(): void {
    this.destroyPortal();

    const btnEl = this.host.nativeElement.querySelector('.help-btn') as HTMLElement | null;
    if (!btnEl) return;

    const btnRect = btnEl.getBoundingClientRect();
    const vp = { w: window.innerWidth, h: window.innerHeight };
    const margin = 12;

    const maxW = Math.min(400, vp.w - margin * 2);
    const maxH = Math.min(520, vp.h - margin * 2);

    const container = this.renderer.createElement('div') as HTMLElement;
    container.className = 'help-portal-backdrop';
    container.addEventListener('click', (e: Event) => {
      if (e.target === container) this.close();
    });

    const popup = this.renderer.createElement('div') as HTMLElement;
    popup.className = 'help-portal-popup';
    popup.style.maxWidth = `${maxW}px`;
    popup.style.maxHeight = `${maxH}px`;
    popup.innerHTML = `
      <div class="help-portal-popup__header">
        <h2 class="help-portal-popup__title">${this.escapeHtml(this.title)}</h2>
        <button class="help-portal-popup__close" type="button" aria-label="Fermer">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
               stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <div class="help-portal-popup__body">${this.parseMarkdown(this.markdownContent)}</div>
    `;

    popup.querySelector('.help-portal-popup__close')?.addEventListener('click', () => this.close());

    container.appendChild(popup);
    this.doc.body.appendChild(container);
    this.portalEl = container;

    requestAnimationFrame(() => {
      const popupRect = popup.getBoundingClientRect();
      const popupW = popupRect.width;
      const popupH = popupRect.height;

      let top = btnRect.bottom + 6;
      if (top + popupH + margin > vp.h) {
        top = btnRect.top - popupH - 6;
      }
      top = Math.max(margin, Math.min(top, vp.h - popupH - margin));

      let left = btnRect.right - popupW;
      if (left < margin) left = btnRect.left;
      if (left + popupW > vp.w - margin) left = vp.w - margin - popupW;
      left = Math.max(margin, left);

      popup.style.top = `${Math.round(top)}px`;
      popup.style.left = `${Math.round(left)}px`;
      popup.style.opacity = '1';
      popup.style.transform = 'scale(1) translateY(0)';
    });
  }

  private destroyPortal(): void {
    if (this.portalEl) {
      this.portalEl.remove();
      this.portalEl = null;
    }
  }

  private escapeHtml(text: string): string {
    const div = this.doc.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    if (this.isOpen()) this.close();
  }

  protected parseMarkdown(text: string): string {
    return text
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^---$/gm, '<hr>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
      .replace(/^\| (.+) \|$/gm, (_, row: string) => {
        const cells = row.split(' | ').map((c: string) => `<td>${c.trim()}</td>`).join('');
        return `<tr>${cells}</tr>`;
      })
      .replace(/(<tr>[\s\S]*?<\/tr>)/g, (m) => m)
      .replace(/(<tr>[\s\S]*?<\/tr>\n?)+/g, (block) => `<table>${block}</table>`)
      .replace(/^\|[-| ]+\|$/gm, '')
      .replace(/^(\d+)\. (.+)$/gm, '<li data-ol>$2</li>')
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      .replace(/(<li[^>]*>.*<\/li>\n?)+/gs, (block) => {
        if (block.includes('data-ol')) {
          return `<ol>${block.replace(/ data-ol/g, '')}</ol>`;
        }
        return `<ul>${block}</ul>`;
      })
      .replace(/\n\n+/g, '\n\n')
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, ' ')
      .trim();
  }
}
