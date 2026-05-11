import { Injectable, signal, Inject } from '@angular/core';
import { PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { ComponentMetadata } from '../services/components-metadata.service';
import { ExerciseGenerationContext } from '../models/exercise.model';

// Panel width constants
export const DEFAULT_LEFT_WIDTH = 330;
export const DEFAULT_RIGHT_WIDTH = 360;
export const MIN_LEFT = 200;
export const MAX_LEFT = 600;
export const MIN_RIGHT = 200;
export const MAX_RIGHT = 500;
export const MIN_CENTER = 300;

export type LeftPanelTab = 'discussion' | 'templates';

@Injectable({ providedIn: 'root' })
export class WorkspaceStore {
  readonly activeLeftTab = signal<LeftPanelTab | null>(null);
  readonly leftPanelWidth = signal<number>(DEFAULT_LEFT_WIDTH);
  readonly rightPanelWidth = signal<number>(DEFAULT_RIGHT_WIDTH);
  readonly isComponentsPanelCollapsed = signal<boolean>(false);
  readonly isTemplatesFiltersExpanded = signal<boolean>(true);
  readonly formulaireComponents = signal<ComponentMetadata[]>([]);
  readonly widgetComponents = signal<ComponentMetadata[]>([]);
  readonly availableComponentNames = signal<string[]>([]);
  readonly tooltipOpenFor = signal<string | null>(null);
  readonly generationContext = signal<ExerciseGenerationContext | null>(null);

  setGenerationContext(ctx: ExerciseGenerationContext): void {
    this.generationContext.set(ctx);
  }

  readonly isDiscussionCollapsed = () => this.activeLeftTab() !== 'discussion';
  readonly isTemplatesPanelExpanded = () => this.activeLeftTab() === 'templates';
  readonly isComponentsPanelExpanded = () => !this.isComponentsPanelCollapsed();

  constructor(@Inject(PLATFORM_ID) private platformId: Object) {
    this.loadPanelWidths();
  }

  selectLeftTab(tab: LeftPanelTab): void {
    if (this.activeLeftTab() === tab) {
      this.activeLeftTab.set(null);
    } else {
      this.activeLeftTab.set(tab);
    }
  }

  collapseDiscussion(): void { this.activeLeftTab.set(null); }
  expandDiscussion(): void { this.activeLeftTab.set('discussion'); }

  collapseComponentsPanel(): void { this.isComponentsPanelCollapsed.set(true); }
  expandComponentsPanel(): void { this.isComponentsPanelCollapsed.set(false); }
  toggleComponentsPanel(): void { this.isComponentsPanelCollapsed.update(v => !v); }

  openTemplatesPanel(): void { this.activeLeftTab.set('templates'); }
  closeTemplatesPanel(): void { this.activeLeftTab.set(null); }
  toggleTemplatesFilters(): void { this.isTemplatesFiltersExpanded.update(v => !v); }
  collapseTemplatesFilters(): void { this.isTemplatesFiltersExpanded.set(false); }

  getComponentByName(name: string): ComponentMetadata | undefined {
    return [...this.formulaireComponents(), ...this.widgetComponents()].find(c => c.name === name);
  }

  getComponentNameByTag(tag: string): string {
    const all = [...this.formulaireComponents(), ...this.widgetComponents()];
    return all.find(c => c.tag === tag)?.name ?? tag;
  }

  setLeftPanelWidth(width: number): void {
    this.leftPanelWidth.set(width);
    this.persistPanelWidths();
  }

  setRightPanelWidth(width: number): void {
    this.rightPanelWidth.set(width);
    this.persistPanelWidths();
  }

  persistPanelWidths(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    try {
      const widths = {
        left: this.leftPanelWidth(),
        right: this.rightPanelWidth()
      };
      localStorage.setItem('workspace_panel_widths', JSON.stringify(widths));
    } catch (error) {
      console.warn('[WorkspaceStore] Failed to persist panel widths', error);
    }
  }

  private loadPanelWidths(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    try {
      const stored = localStorage.getItem('workspace_panel_widths');
      if (stored) {
        const widths = JSON.parse(stored);
        if (typeof widths.left === 'number') {
          this.leftPanelWidth.set(widths.left);
        }
        if (typeof widths.right === 'number') {
          this.rightPanelWidth.set(widths.right);
        }
      }
    } catch (error) {
      console.warn('[WorkspaceStore] Failed to load panel widths', error);
    }
  }
}
