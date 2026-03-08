import { Injectable, inject, PLATFORM_ID, Injector, effect } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/auth/auth.service';
import { ContextService, CircleTreeNode } from '../services/context.service';
import { ComponentsMetadataService } from '../services/components-metadata.service';
import { ExerciseService } from '../services/exercise.service';
import { WorkspaceStore } from './workspace.store';
import { WorkspaceAutosaveService } from './workspace-autosave.service';
import { WorkspaceFiltersStore } from './workspace-filters.store';
import { WorkspaceTemplateService } from './workspace-template.service';
import { ExerciseData } from '../models/exercise.model';
import { TemplateResponse } from '../models/template.model';
import { TreeNode } from '../../../shared/ui/tree-select/tree-select.component';

@Injectable({ providedIn: 'root' })
export class WorkspaceFacade {
  private readonly authService = inject(AuthService);
  private readonly contextService = inject(ContextService);
  private readonly componentsMetadata = inject(ComponentsMetadataService);
  private readonly exerciseService = inject(ExerciseService);
  private readonly router = inject(Router);
  private readonly autosave = inject(WorkspaceAutosaveService);
  private readonly templateService = inject(WorkspaceTemplateService);
  private readonly platformId = inject(PLATFORM_ID);

  readonly store = inject(WorkspaceStore);
  readonly filters = inject(WorkspaceFiltersStore);

  readonly exerciseData = this.exerciseService.exerciseData;

  exerciseId: string | null = null;
  private readonly isBrowser = isPlatformBrowser(this.platformId);

  async init(injector: Injector): Promise<void> {
    if (!this.isBrowser) return;

    await this.authService.waitForInitialization();
    if (!this.authService.isAuthenticated()) {
      this.router.navigate(['/']);
      return;
    }

    const components = await this.componentsMetadata.loadComponents();
    this.store.formulaireComponents.set(components.filter(c => c.category === 'Formulaire'));
    this.store.widgetComponents.set(components.filter(c => c.category === 'Widget'));
    this.store.availableComponentNames.set(components.map(c => c.name));

    if (!this.contextService.isLoaded()) {
      await this.contextService.loadAllContext();
    }

    await this.initAutosave(injector);
  }

  private async initAutosave(injector: Injector): Promise<void> {
    this.exerciseId = this.autosave.getOrCreateExerciseId();
    const localCache = this.autosave.getLocalState(this.exerciseId);

    if (localCache) {
      this.exerciseService.exerciseData.set(localCache);
    }

    try {
      const remote = await this.exerciseService.getExerciseState(this.exerciseId);
      if (!localCache) {
        this.exerciseService.exerciseData.set(remote);
        this.autosave.saveLocalState(this.exerciseId, remote);
      }
    } catch {
    }

    this.autosave.markReady(this.exerciseService.exerciseData());

    effect((onCleanup) => {
      const data = this.exerciseService.exerciseData();
      if (!this.autosave.isReady() || !this.exerciseId) return;
      if (!this.autosave.isChanged(data)) return;

      this.autosave.saveLocalState(this.exerciseId, data);
      this.autosave.scheduleRemoteSave(this.exerciseId, data);

      onCleanup(() => this.autosave.cancelPendingTimer());
    }, { injector });
  }

  flushOnDestroy(): void {
    if (!this.isBrowser || !this.exerciseId || !this.autosave.isReady()) return;
    const data = this.exerciseService.exerciseData();
    this.autosave.saveLocalState(this.exerciseId, data);
    void this.autosave.flushRemoteSave(this.exerciseId, data);
  }

  get cercleTree(): TreeNode {
    const backend = this.contextService.circlesTree();
    return backend ? this.mapTreeNode(backend) : { name: 'PLaTon', children: [] };
  }

  private mapTreeNode(node: CircleTreeNode): TreeNode {
    return { name: node.name, children: node.children?.map(c => this.mapTreeNode(c)) };
  }

  applyTemplate(template: TemplateResponse): ExerciseData {
    return this.templateService.buildExerciseFromTemplate(template, this.exerciseService.exerciseData());
  }

  updateExercise(data: ExerciseData): void {
    this.exerciseService.exerciseData.set(data);
  }

  addComponent(name: string): void {
    this.exerciseService.exerciseData.update(d => {
      const current = d.components ?? [];
      if (current.includes(name)) return d;
      return { ...d, components: [...current, name] };
    });
  }

  removeComponent(name: string): void {
    this.exerciseService.exerciseData.update(d => ({
      ...d,
      components: (d.components ?? []).filter(c => c !== name),
    }));
  }

  addIndication(): void {
    this.exerciseService.exerciseData.update(d => ({
      ...d,
      indications: [...(d.indications ?? []), ''],
    }));
  }

  removeIndication(index: number): void {
    this.exerciseService.exerciseData.update(d => ({
      ...d,
      indications: (d.indications ?? []).filter((_, i) => i !== index),
    }));
  }

  addTheory(): void {
    this.exerciseService.exerciseData.update(d => ({
      ...d,
      theories: [...(d.theories ?? []), { title: '', url: '' }],
    }));
  }

  removeTheory(index: number): void {
    this.exerciseService.exerciseData.update(d => ({
      ...d,
      theories: (d.theories ?? []).filter((_, i) => i !== index),
    }));
  }

  getComponentByName(name: string) {
    return this.store.getComponentByName(name);
  }

  getComponentNameByTag(tag: string): string {
    return this.store.getComponentNameByTag(tag);
  }

  navigateToLogs(): void {
    this.router.navigate(['/logs']);
  }
}

