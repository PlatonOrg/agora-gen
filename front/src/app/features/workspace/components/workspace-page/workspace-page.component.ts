import {
  ChangeDetectorRef,
  Component, OnInit, OnDestroy, PLATFORM_ID, Inject,
  inject, ViewChild, Injector, signal,
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Overlay, OverlayRef } from '@angular/cdk/overlay';
import { ComponentPortal } from '@angular/cdk/portal';
import { ComponentTooltipComponent } from '../../../../shared/ui/component-tooltip/component-tooltip.component';
import { TreeNode } from '../../../../shared/ui/tree-select/tree-select.component';
import { TourTooltipComponent } from '../../../../shared/ui/tour-tooltip/tour-tooltip.component';
import { DiscussionPanelComponent } from '../discussion/discussion-panel.component';
import { ExerciseContentPanelComponent } from '../exercise-content/exercise-content-panel.component';
import { SidePanelComponent } from '../side-panel/side-panel.component';
import { ResizeHandleDirective } from '../../directives/resize-handle.directive';

import { TemplatesPanelComponent } from '../templates-panel/templates-panel.component';
import { WorkspaceHeaderComponent } from '../workspace-header/workspace-header.component';
import { HelpPopupComponent } from '../../../../shared/ui/help-popup/help-popup.component';
import { TemplateResponse } from '../../models/template.model';
import { ExerciseData } from '../../models/exercise.model';
import { WorkspaceFacade } from '../../state/workspace.facade';
import { WorkspaceFiltersStore } from '../../state/workspace-filters.store';
import { WorkspaceStore } from '../../state/workspace.store';
import { ChatService } from '../../services/chat.service';
import { OnboardingService } from '../../services/onboarding.service';
import { ConfirmDialogComponent } from '../../../../shared/ui/confirm-dialog/confirm-dialog.component';
import { WORKSPACE_TOUR_STEPS, TEMPLATES_HELP_CONTENT } from '../../models/help-content.constants';

@Component({
  selector: 'app-workspace-page',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    DiscussionPanelComponent, ExerciseContentPanelComponent,
    SidePanelComponent, TemplatesPanelComponent,
    WorkspaceHeaderComponent, ResizeHandleDirective,
    ConfirmDialogComponent, TourTooltipComponent, HelpPopupComponent,
  ],
  templateUrl: './workspace-page.component.html',
  styleUrl: './workspace-page.component.scss',
})
export class WorkspacePageComponent implements OnInit, OnDestroy {
  protected readonly facade = inject(WorkspaceFacade);
  protected readonly wsStore = inject(WorkspaceStore);
  protected readonly filters = inject(WorkspaceFiltersStore);
  protected readonly onboarding = inject(OnboardingService);

  private readonly overlay = inject(Overlay);
  private readonly injector = inject(Injector);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chatService = inject(ChatService);
  private readonly isBrowser: boolean;
  private overlayRef: OverlayRef | null = null;

  protected readonly templatesHelpContent = TEMPLATES_HELP_CONTENT;

  protected readonly showUseTemplateConfirm = signal(false);
  private pendingTemplate: TemplateResponse | null = null;

  protected readonly showResetAllConfirm = signal(false);

  protected readonly isPanelSwitcherOpen = signal(false);

  protected readonly useTemplateDialogOptions = {
    title: 'Appliquer ce modèle ?',
    description: "Le contenu actuel de l'exercice sera remplacé par la configuration de ce modèle. Cette action est irréversible.",
    confirmLabel: 'Appliquer',
    variant: 'warning' as const,
  };

  protected readonly resetAllDialogOptions = {
    title: 'Réinitialiser l\'espace de travail ?',
    description: 'Le contenu de l\'exercice (titre, énoncé, code, composants, etc.) et l\'intégralité de l\'historique de conversation seront effacés définitivement. Cette action est irréversible.',
    confirmLabel: 'Réinitialiser',
    variant: 'danger' as const,
  };

  @ViewChild('discussionPanel') discussionPanel?: DiscussionPanelComponent;
  @ViewChild('exerciseContentPanel') exerciseContentPanel!: ExerciseContentPanelComponent;

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  async ngOnInit(): Promise<void> {
    await this.facade.init(this.injector);
    this.onboarding.registerSteps(this.buildTourSteps());
    this.onboarding.startIfFirstVisit();
  }

  private buildTourSteps(): import('../../services/onboarding.service').TourStep[] {
    return WORKSPACE_TOUR_STEPS.map(step => {
      switch (step.id) {
        case 'welcome':
          return { ...step, action: () => {
            this.wsStore.collapseDiscussion();
            this.wsStore.collapseComponentsPanel();
          }};
        case 'panel-menu':
          return { ...step, action: () => {
            this.wsStore.collapseDiscussion();
            this.wsStore.collapseComponentsPanel();
          }};
        case 'discussion':
          return { ...step, action: () => {
            this.wsStore.expandDiscussion();
            this.wsStore.collapseComponentsPanel();
          }};
        case 'templates':
          return { ...step, action: () => {
            this.wsStore.openTemplatesPanel();
            this.wsStore.collapseComponentsPanel();
          }};
        case 'exercise-editor':
          return { ...step, action: () => {
            this.wsStore.collapseDiscussion();
            this.wsStore.collapseComponentsPanel();
          }};
        case 'components-panel':
        case 'drag-drop':
          return { ...step, action: () => {
            this.wsStore.collapseDiscussion();
            this.wsStore.expandComponentsPanel();
          }};
        case 'header-actions':
          return { ...step, action: () => {
            this.wsStore.collapseDiscussion();
            this.wsStore.collapseComponentsPanel();
          }};
        case 'finish':
          return { ...step, action: () => {
            this.wsStore.collapseDiscussion();
            this.wsStore.collapseComponentsPanel();
          }};
        default:
          return step;
      }
    });
  }

  protected toggleLeftPanel(): void {
    if (this.wsStore.activeLeftTab() !== null) {
      this.wsStore.collapseDiscussion();
    } else {
      this.wsStore.expandDiscussion();
    }
  }

  protected togglePanelSwitcher(): void {
    this.isPanelSwitcherOpen.update(v => !v);
  }

  protected closePanelSwitcher(): void {
    this.isPanelSwitcherOpen.set(false);
  }

  protected switchToDiscussion(): void {
    this.closePanelSwitcher();
    this.wsStore.expandDiscussion();
  }

  ngOnDestroy(): void {
    this.closeTooltip();
    this.facade.flushOnDestroy();
    this.chatService.forceAbort();
  }

  get cercleTree(): TreeNode {
    return this.facade.cercleTree;
  }

  get filteredSujets(): string[] {
    return this.filters.filteredSujets();
  }

  get filteredNiveaux(): string[] {
    return this.filters.filteredNiveaux();
  }

  get filteredComponents(): string[] {
    const input = this.filters.componentInput().toLowerCase();
    const current = this.filters.selectedComponents();
    return this.wsStore.availableComponentNames()
      .filter(c => !current.includes(c) && c.toLowerCase().includes(input))
      .slice(0, 20);
  }

  protected useTemplate(template: TemplateResponse): void {
    this.pendingTemplate = template;
    this.showUseTemplateConfirm.set(true);
  }

  protected confirmUseTemplate(): void {
    this.showUseTemplateConfirm.set(false);
    if (!this.pendingTemplate) return;
    const template = this.pendingTemplate;
    this.pendingTemplate = null;
    const newData = this.facade.applyTemplate(template);
    this.facade.updateExercise(newData);
    this.cdr.markForCheck();
    this.exerciseContentPanel.setComponentsInitialized();
    this.exerciseContentPanel.expandOnlyTemplateParameters();
  }

  protected cancelUseTemplate(): void {
    this.showUseTemplateConfirm.set(false);
    this.pendingTemplate = null;
  }

  protected onTemplateApplied(_event: { name: string; previousState: ExerciseData }): void {}

  protected onTemplateCancelled(): void {}

  protected onChatResponse(response: { exercise_data?: ExerciseData; url?: string; error?: string }): void {
    if (response.exercise_data) {
      this.facade.updateExercise(response.exercise_data);
      this.cdr.markForCheck();
    }
    if (response.url) {
      window.location.href = response.url;
    }
  }

  protected onPreviewCompleted(event: { success: boolean; error?: string; url?: string }): void {
    this.discussionPanel?.addMessage({
      id: crypto.randomUUID(),
      role: 'system',
      content: event.success
        ? `Prévisualisation générée avec succès.`
        : `Échec de la prévisualisation : ${event.error ?? 'erreur inconnue'}`,
      components: [],
      timestamp: new Date(),
    });
  }

  protected addComponentToDiscussion(componentName: string): void {
    const component = this.facade.getComponentByName(componentName);
    if (component) {
      const type = component.category === 'Formulaire' ? 'formulaire' : 'widget';
      this.discussionPanel?.addComponentBadge(component.name, component.tag, type);
    }
  }

  protected toggleTooltip(componentName: string, event: MouseEvent): void {
    event.stopPropagation();
    if (this.wsStore.tooltipOpenFor() === componentName) {
      this.closeTooltip();
    } else {
      this.openTooltip(componentName, event);
    }
  }

  protected get headerViewExerciseLoading(): boolean {
    return this.exerciseContentPanel?.isViewExerciseLoading() ?? false;
  }

  protected get headerViewPleLoading(): boolean {
    return this.exerciseContentPanel?.isViewPleLoading() ?? false;
  }

  protected get headerTemplateName(): string | null {
    return this.exerciseContentPanel?.currentTemplateName() ?? null;
  }

  onHeaderViewExercise(): void { this.exerciseContentPanel?.viewExercise(); }
  onHeaderViewPle(): void { this.exerciseContentPanel?.viewPleContent(); }
  onHeaderResetExercise(): void { this.showResetAllConfirm.set(true); }
  onHeaderPublishExercise(): void { this.exerciseContentPanel?.openPublishDialog(); }

  protected async confirmResetAll(): Promise<void> {
    this.showResetAllConfirm.set(false);
    // Stop any running generation before clearing the exercise state.
    this.chatService.stopGeneration();
    // Reset exercise data via the exercise panel helper (keeps internal state consistent)
    this.exerciseContentPanel?.doConfirmResetExerciseExternal();
    // Reset conversation history and purge session files via the discussion panel
    await this.discussionPanel?.resetDiscussion();
    this.cdr.markForCheck();
  }

  protected cancelResetAll(): void {
    this.showResetAllConfirm.set(false);
  }

  private openTooltip(componentName: string, event: MouseEvent): void {
    this.closeTooltip();
    const triggerElement = event.target as HTMLElement;
    const positionStrategy = this.overlay.position()
      .flexibleConnectedTo(triggerElement)
      .withPositions([
        { originX: 'center', originY: 'bottom', overlayX: 'center', overlayY: 'top', offsetY: 8 },
        { originX: 'center', originY: 'top', overlayX: 'center', overlayY: 'bottom', offsetY: -8 },
      ]);

    this.overlayRef = this.overlay.create({
      positionStrategy,
      hasBackdrop: true,
      backdropClass: 'tooltip-backdrop',
      scrollStrategy: this.overlay.scrollStrategies.reposition(),
    });

    this.overlayRef.backdropClick().subscribe(() => this.closeTooltip());

    const portal = new ComponentPortal(ComponentTooltipComponent);
    const ref = this.overlayRef.attach(portal);
    ref.instance.component = this.facade.getComponentByName(componentName);
    this.wsStore.tooltipOpenFor.set(componentName);
  }

  private closeTooltip(): void {
    this.overlayRef?.dispose();
    this.overlayRef = null;
    this.wsStore.tooltipOpenFor.set(null);
  }
}

