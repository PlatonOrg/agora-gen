import { Component, signal, input, output, inject, PLATFORM_ID, Inject, computed, effect, ViewChild, ElementRef, AfterViewInit, runInInjectionContext, Injector, Output, EventEmitter } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MonacoEditorModule } from 'ngx-monaco-editor-v2';
import { ComponentsMetadataService, ComponentPropertyEntry } from '../../services/components-metadata.service';
import { ChatService } from '../../services/chat.service';
import { TemplateParametersComponent } from '../template-parameters/template-parameters.component';
import { ExerciseData } from '../../models/exercise.model';
import { PublishDialogComponent } from './publish-dialog.component';
import { PublishExerciseRequest } from '../../models/publish.model';
import { FIELD_DESCRIPTIONS, makeMonacoOptions, PLE_EDITOR_OPTIONS, SANDBOX_LANGUAGE_MAP } from './exercise-content.constants';
import { ConfirmDialogComponent } from '../../../../shared/ui/confirm-dialog/confirm-dialog.component';

@Component({
  selector: 'app-exercise-content-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, MonacoEditorModule, TemplateParametersComponent, PublishDialogComponent, ConfirmDialogComponent],
  templateUrl: './exercise-content-panel.component.html',
  styleUrls: ['../workspace.shared.scss', './exercise-content-panel.component.scss'],
})
export class ExerciseContentPanelComponent implements AfterViewInit {

  @Output() previewCompleted = new EventEmitter<{
    success: boolean;
    error?: string;
    url?: string;
  }>();

  private componentsMetadataService = inject(ComponentsMetadataService);
  private chatService = inject(ChatService);
  private injector = inject(Injector);
  public isBrowser: boolean;

  exerciseData = input.required<ExerciseData>();
  exerciseId = input.required<string>();

  currentExerciseData = computed(() => {
    const data = this.exerciseData();
    return {
      name: '',
      description: '',
      titre: '',
      enonce: '',
      forme: '',
      solution: '',
      indications: [],
      theories: [],
      components: [],
      sandbox: 'python',
      construction: '',
      evaluation: '',
      ...data,
      metadata: {
        levels: data.metadata?.levels ?? [],
        topics: data.metadata?.topics ?? [],
        readme: data.metadata?.readme,
      },
    };
  });

  updateExercise = output<ExerciseData>();
  addComponent = output<string>();
  removeComponent = output<string>();
  addIndication = output<void>();
  removeIndication = output<number>();
  addTheory = output<void>();
  removeTheory = output<number>();
  toggleFieldInfo = output<{ fieldName: string; event: MouseEvent }>();

  public fieldDescriptions = FIELD_DESCRIPTIONS;
  public readonly pleEditorOptions = PLE_EDITOR_OPTIONS;

  nameSignal = signal<string>('');
  descriptionSignal = signal<string>('');
  sandboxVariablesContent = signal<string>('');
  isComponentsDropZone = signal<boolean>(false);
  isViewPleLoading = signal<boolean>(false);
  isPlePopupVisible = signal<boolean>(false);
  pleContent = signal<string>('');
  isViewExerciseLoading = signal<boolean>(false);
  isEditable = signal<boolean>(true);
  showPublishDialog = signal<boolean>(false);
  publishFeedback = signal<{ type: 'success' | 'error'; message: string } | null>(null);
  activeTab = signal<'content' | 'components' | 'optional' | 'technical' | 'params' | 'metadata'>('content');
  showResetExerciseConfirm = signal<boolean>(false);

  platonTopicsSuggestions = signal<{ id: string; name: string }[]>([]);
  platonLevelsSuggestions = signal<{ id: string; name: string }[]>([]);
  tagsLoaded = signal<boolean>(false);
  newTopicInput = signal<string>('');
  newLevelInput = signal<string>('');
  topicDropdownOpen = signal<boolean>(false);
  levelDropdownOpen = signal<boolean>(false);
  readmeSignal = signal<string>('');

  protected readonly resetExerciseDialogOptions = {
    title: 'Réinitialiser l\'exercice ?',
    description: "Tout le contenu de l'exercice (titre, énoncé, code, composants, etc.) sera effacé définitivement. Cette action est irréversible.",
    confirmLabel: 'Réinitialiser',
    variant: 'danger' as const,
  };

  fieldInfoOpen = signal<string | null>(null);
  fieldInfoPosition = signal<{ top: number; left: number } | null>(null);
  propertyInfoOpen = signal<string | null>(null);
  propertyInfoPosition = signal<{ top: number; left: number } | null>(null);
  propertyInfoDescription = signal<string>('');
  currentTemplateName = signal<string | null>(null);

  private hasInitializedComponentsFromSandbox = signal<boolean>(false);
  private jsonParseErrors = new Map<string, boolean>();
  private sandboxVarsPending: { key: string; value: string }[] | null = null;
  private currentDragImage: HTMLElement | null = null;
  private previewUrlCache = signal<{ hash: string; url: string } | null>(null);

  constructionEditorOptions = makeMonacoOptions('python');
  evaluationEditorOptions = makeMonacoOptions('python');
  sandboxVariablesEditorOptions = makeMonacoOptions('python');
  readmeEditorOptions = makeMonacoOptions('markdown');

  @ViewChild('titleTextarea', { static: false }) titleTextarea!: ElementRef<HTMLTextAreaElement>;
  @ViewChild('descriptionTextarea', { static: false }) descriptionTextarea!: ElementRef<HTMLTextAreaElement>;

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);

    effect(() => {
      this.nameSignal.set(this.currentExerciseData().name || '');
      this.descriptionSignal.set(this.currentExerciseData().description || '');
    });

    effect(() => {
      const data = this.currentExerciseData();
      this.readmeSignal.set(data.metadata.readme ?? this.buildReadmeFromData(data));
    });

    effect(() => {
      const data = this.exerciseData();
      this.currentTemplateName.set(data.template_id && data.name ? data.name : null);
      if (data.template_id) {
        if (this.activeTab() !== 'metadata') {
          this.activeTab.set('params');
        }
      } else if (this.activeTab() === 'params') {
        this.activeTab.set('content');
      }
    });


    effect(() => {
      const editable = this.isEditable();
      const isTemplate = this.isTemplate();
      const lang = (this.constructionEditorOptions as any).language || 'python';
      this.constructionEditorOptions = makeMonacoOptions(lang, !editable || isTemplate) as any;
      this.evaluationEditorOptions = makeMonacoOptions(lang, !editable || isTemplate) as any;
      this.sandboxVariablesEditorOptions = makeMonacoOptions('python', !editable || isTemplate) as any;
      this.readmeEditorOptions = makeMonacoOptions('markdown', !editable) as any;
    });

    effect(() => {
      const sandboxVars = this.currentExerciseData().sandbox_variables;
      this.sandboxVarsPending = null;
      if (!sandboxVars) { this.sandboxVariablesContent.set(''); return; }
      const lines: string[] = [];
      for (const [key, value] of Object.entries(sandboxVars)) {
        if (key === 'author') continue;
        if (typeof value === 'object' && value !== null && 'cid' in value) {
          const selector = (value as any).selector || 'unknown';
          lines.push(`${key} = ${selector}`);
          for (const [prop, propValue] of Object.entries(value)) {
            if (prop !== 'cid' && prop !== 'selector') lines.push(`${key}.${prop} = ${JSON.stringify(propValue)}`);
          }
        } else {
          lines.push(`${key} = ${JSON.stringify(value)}`);
        }
      }
      this.sandboxVariablesContent.set(lines.join('\n'));
    });

    effect(() => {
      const componentInstances = this.currentExerciseData().component_instances || [];
      const currentData = this.currentExerciseData();
      const sandboxVars = { ...(currentData.sandbox_variables || {}) };
      let hasChanges = false;
      if (componentInstances.length === 0 || !componentInstances.every(inst => this.isCompleteComponentInstance(inst))) return;
      for (const instance of componentInstances) {
        if (!instance.instanceName) continue;
        const metadata = this.componentsMetadataService.getComponentByName(instance.componentName);
        if (!metadata) continue;
        const componentObj: any = { cid: metadata.tag, selector: metadata.tag, ...instance.properties };
        const existing = sandboxVars[instance.instanceName];
        if (JSON.stringify(existing) !== JSON.stringify(componentObj)) { sandboxVars[instance.instanceName] = componentObj; hasChanges = true; }
      }
      const instanceNames = new Set(componentInstances.map(i => i.instanceName).filter(n => n));
      for (const [key, value] of Object.entries(sandboxVars)) {
        if (typeof value === 'object' && value !== null && 'cid' in value && !instanceNames.has(key)) { delete sandboxVars[key]; hasChanges = true; }
      }
      if (hasChanges) setTimeout(() => this.updateExercise.emit({ ...currentData, sandbox_variables: sandboxVars }), 0);
    });

    effect(() => {
      const currentData = this.currentExerciseData();
      const sandboxVars = currentData.sandbox_variables;
      const existingInstances = currentData.component_instances || [];
      const hasCompleteInstances = existingInstances.length > 0 && existingInstances.every(inst => this.isCompleteComponentInstance(inst));
      if (!sandboxVars || hasCompleteInstances || this.hasInitializedComponentsFromSandbox()) return;
      const newInstances: import('../../models/exercise.model').ComponentInstance[] = [];
      for (const [key, value] of Object.entries(sandboxVars)) {
        if (typeof value === 'object' && value !== null && 'cid' in value) {
          const cid = (value as any).cid;
          const metadata = this.componentsMetadataService.components().find(c => c.tag === cid);
          if (metadata) {
            const { cid: _, selector: __, ...properties } = value as any;
            newInstances.push({ id: `inst_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`, selector: cid, componentName: metadata.name, instanceName: key, category: metadata.category, properties, collapsed: true });
          }
        }
      }
      if (newInstances.length > 0) {
        this.hasInitializedComponentsFromSandbox.set(true);
        setTimeout(() => this.updateExercise.emit({ ...currentData, component_instances: newInstances }), 0);
      }
    });
  }

  ngAfterViewInit(): void {
    if (!this.isBrowser) return;
    runInInjectionContext(this.injector, () => {
      effect(() => { this.nameSignal(); requestAnimationFrame(() => { const el = this.titleTextarea?.nativeElement; if (!el) return; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }); });
      effect(() => { this.descriptionSignal(); requestAnimationFrame(() => { const el = this.descriptionTextarea?.nativeElement; if (!el) return; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }); });
    });
    setTimeout(() => this.titleTextarea?.nativeElement?.focus(), 0);
  }

  setTab(tab: 'content' | 'components' | 'optional' | 'technical' | 'params' | 'metadata'): void {
    this.activeTab.set(tab);
    if (tab === 'metadata' && !this.tagsLoaded()) {
      void this.loadTags();
    }
  }

  private async loadTags(): Promise<void> {
    try {
      const tags = await this.chatService.getTags();
      this.platonTopicsSuggestions.set(tags.topics);
      this.platonLevelsSuggestions.set(tags.levels);
      this.tagsLoaded.set(true);
    } catch {
      this.tagsLoaded.set(true);
    }
  }

  protected getTopicSuggestions(): { id: string; name: string }[] {
    const input = this.newTopicInput().toLowerCase().trim();
    const existing = new Set(this.currentExerciseData().metadata.topics.map(t => t.toLowerCase()));
    return this.platonTopicsSuggestions()
      .filter(t => !existing.has(t.name.toLowerCase()) && (!input || t.name.toLowerCase().includes(input)));
  }

  protected getLevelSuggestions(): { id: string; name: string }[] {
    const input = this.newLevelInput().toLowerCase().trim();
    const existing = new Set(this.currentExerciseData().metadata.levels.map(l => l.toLowerCase()));
    return this.platonLevelsSuggestions()
      .filter(l => !existing.has(l.name.toLowerCase()) && (!input || l.name.toLowerCase().includes(input)));
  }

  protected addTopic(value: string): void {
    const trimmed = value.trim();
    if (!trimmed) return;
    const d = this.currentExerciseData();
    const topics = [...d.metadata.topics];
    if (!topics.includes(trimmed)) {
      this.updateExercise.emit({ ...d, metadata: { ...d.metadata, topics: [...topics, trimmed] } });
    }
    this.newTopicInput.set('');
    this.topicDropdownOpen.set(false);
  }

  protected removeTopic(index: number): void {
    const d = this.currentExerciseData();
    const topics = d.metadata.topics.filter((_, i) => i !== index);
    this.updateExercise.emit({ ...d, metadata: { ...d.metadata, topics } });
  }

  protected addLevel(value: string): void {
    const trimmed = value.trim();
    if (!trimmed) return;
    const d = this.currentExerciseData();
    const levels = [...d.metadata.levels];
    if (!levels.includes(trimmed)) {
      this.updateExercise.emit({ ...d, metadata: { ...d.metadata, levels: [...levels, trimmed] } });
    }
    this.newLevelInput.set('');
    this.levelDropdownOpen.set(false);
  }

  protected removeLevel(index: number): void {
    const d = this.currentExerciseData();
    const levels = d.metadata.levels.filter((_, i) => i !== index);
    this.updateExercise.emit({ ...d, metadata: { ...d.metadata, levels } });
  }

  protected onTopicInputKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      const input = this.newTopicInput().trim();
      if (input) this.addTopic(input);
    } else if (event.key === 'Escape') {
      this.topicDropdownOpen.set(false);
    }
  }

  protected onLevelInputKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      const input = this.newLevelInput().trim();
      if (input) this.addLevel(input);
    } else if (event.key === 'Escape') {
      this.levelDropdownOpen.set(false);
    }
  }
  public expandOnlyTemplateParameters(): void {
    this.activeTab.set('params');
  }

  isTemplate = computed((): boolean => {
    const data = this.currentExerciseData();
    return !!data.template_id || !!(data.config_variables && Array.isArray(data.config_variables['inputs']) && data.config_variables['inputs'].length > 0);
  });

  protected getTemplateParameters(): any[] { return this.currentExerciseData().config_variables?.['inputs'] || []; }

  protected onTemplateParameterChange(change: { name: string; value: any }): void {
    const currentData = this.currentExerciseData();
    const configVars = { ...currentData.config_variables };
    if (configVars['inputs']) {
      const idx = configVars['inputs'].findIndex((i: any) => i.name === change.name);
      if (idx !== -1) configVars['inputs'][idx].value = change.value;
    }
    this.updateExercise.emit({ ...currentData, config_variables: configVars });
  }

  protected onSandboxChange(): void {
    const lang = SANDBOX_LANGUAGE_MAP[this.currentExerciseData().sandbox] || 'plaintext';
    this.constructionEditorOptions = makeMonacoOptions(lang, (this.constructionEditorOptions as any).readOnly) as any;
    this.evaluationEditorOptions = makeMonacoOptions(lang, (this.evaluationEditorOptions as any).readOnly) as any;
  }

  protected doAddIndication(): void { const d = this.currentExerciseData(); this.updateExercise.emit({ ...d, indications: [...(d.indications || []), ''] }); }
  protected doRemoveIndication(index: number): void { const d = this.currentExerciseData(); this.updateExercise.emit({ ...d, indications: (d.indications || []).filter((_: string, i: number) => i !== index) }); }
  protected doAddTheory(): void { const d = this.currentExerciseData(); this.updateExercise.emit({ ...d, theories: [...(d.theories || []), { title: '', url: '' }] }); }
  protected doRemoveTheory(index: number): void { const d = this.currentExerciseData(); this.updateExercise.emit({ ...d, theories: (d.theories || []).filter((_: any, i: number) => i !== index) }); }

  protected onNameChange(value: string): void { this.nameSignal.set(value); this.updateExercise.emit({ ...this.currentExerciseData(), name: value }); }
  protected onDescriptionChange(value: string): void { this.descriptionSignal.set(value); this.updateExercise.emit({ ...this.currentExerciseData(), description: value }); }
  protected onReadmeChange(value: string): void {
    this.readmeSignal.set(value);
    const d = this.currentExerciseData();
    this.updateExercise.emit({ ...d, metadata: { ...d.metadata, readme: value } });
  }
  protected onTitreChange(value: string): void { this.updateExercise.emit({ ...this.currentExerciseData(), titre: value }); }
  protected onEnonceChange(value: string): void { this.updateExercise.emit({ ...this.currentExerciseData(), enonce: value }); }
  protected onFormeChange(value: string): void { this.updateExercise.emit({ ...this.currentExerciseData(), forme: value }); }
  protected onSolutionFieldChange(value: string): void { this.updateExercise.emit({ ...this.currentExerciseData(), solution: value }); }
  protected onConstructionChange(value: string): void { this.updateExercise.emit({ ...this.currentExerciseData(), construction: value }); }
  protected onEvaluationChange(value: string): void { this.updateExercise.emit({ ...this.currentExerciseData(), evaluation: value }); }
  protected onIndicationChange(index: number, value: string): void { const d = this.currentExerciseData(); const arr = [...(d.indications || [])]; arr[index] = value; this.updateExercise.emit({ ...d, indications: arr }); }
  protected onTheoryTitleChange(index: number, value: string): void { const d = this.currentExerciseData(); const arr = [...(d.theories || [])]; arr[index] = { ...arr[index], title: value }; this.updateExercise.emit({ ...d, theories: arr }); }
  protected onTheoryUrlChange(index: number, value: string): void { const d = this.currentExerciseData(); const arr = [...(d.theories || [])]; arr[index] = { ...arr[index], url: value }; this.updateExercise.emit({ ...d, theories: arr }); }
  protected onSandboxSelectChange(value: string): void { this.updateExercise.emit({ ...this.currentExerciseData(), sandbox: value }); this.onSandboxChange(); }

  protected showFieldInfo(event: MouseEvent, fieldName: string): void {
    event.stopPropagation();
    if (this.fieldInfoOpen() === fieldName) { this.fieldInfoOpen.set(null); this.fieldInfoPosition.set(null); }
    else {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      this.fieldInfoPosition.set({ top: rect.bottom + 8, left: rect.left + rect.width / 2 });
      this.fieldInfoOpen.set(fieldName);
    }
    this.toggleFieldInfo.emit({ fieldName, event });
  }

  protected showPropertyInfo(event: MouseEvent, componentInstanceId: string, propertyKey: string, description: string): void {
    event.stopPropagation();
    const key = `${componentInstanceId}_${propertyKey}`;
    if (this.propertyInfoOpen() === key) { this.propertyInfoOpen.set(null); this.propertyInfoPosition.set(null); this.propertyInfoDescription.set(''); }
    else {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      this.propertyInfoPosition.set({ top: rect.bottom + 8, left: rect.left + rect.width / 2 });
      this.propertyInfoOpen.set(key);
      this.propertyInfoDescription.set(description);
    }
  }

  protected onFieldDragStart(event: DragEvent, fieldName: string): void {
    event.stopPropagation();
    if (!event.dataTransfer) return;
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData('application/json', JSON.stringify({ type: 'field', name: fieldName }));
    event.dataTransfer.setData('text/plain', `{ ${fieldName} }`);
    if (this.currentDragImage) {
      try { document.body.removeChild(this.currentDragImage); } catch {}
      this.currentDragImage = null;
    }
    const dragImage = document.createElement('div');
    dragImage.style.cssText = 'position:fixed;top:-9999px;left:-9999px;padding:5px 10px;background:#1565C0;color:#fff;border-radius:4px;font-size:12px;font-weight:600;pointer-events:none;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.18);letter-spacing:0.02em;z-index:99999;';
    dragImage.textContent = `{ ${fieldName} }`;
    this.currentDragImage = dragImage;
    document.body.appendChild(dragImage);
    event.dataTransfer.setDragImage(dragImage, 40, 14);
  }

  protected onFieldDragEnd(_event: DragEvent): void {
    if (this.currentDragImage) {
      try { document.body.removeChild(this.currentDragImage); } catch {}
      this.currentDragImage = null;
    }
  }

  buildReadmeFromData(data: ExerciseData): string {
    const lines: string[] = [];
    const titre = data.titre || data.name;
    if (titre) { lines.push(`# ${titre}`); lines.push(''); }
    if (data.description) { lines.push('## Description'); lines.push(''); lines.push(data.description); lines.push(''); }
    const theories = data.theories || [];
    if (theories.length > 0) {
      lines.push('## Ressources'); lines.push('');
      for (const t of theories) {
        if (t.title && t.url) lines.push(`- [${t.title}](${t.url})`);
        else if (t.title) lines.push(`- ${t.title}`);
      }
      lines.push('');
    }
    return lines.join('\n').trimEnd();
  }

  private hashExerciseData(data: any): string {    const key = JSON.stringify(data);
    let hash = 0;
    for (let i = 0; i < key.length; i++) { const c = key.charCodeAt(i); hash = ((hash << 5) - hash) + c; hash |= 0; }
    return hash.toString(36);
  }

  public async viewExercise(): Promise<void> {
    this.isViewExerciseLoading.set(true);
    const displayData = this.currentExerciseData();
    const exerciseData = this.exerciseData();
    try {
      const currentHash = this.hashExerciseData(exerciseData);
      const cached = this.previewUrlCache();
      if (cached && cached.hash === currentHash) { window.open(cached.url, '_blank'); this.previewCompleted.emit({ success: true, url: cached.url }); return; }
      if (displayData.config_variables && displayData.template_id) {
        const variables: { [key: string]: any } = {};
        this.getTemplateParameters().forEach((p: any) => { if (p.name && p.value !== undefined) variables[p.name] = p.value; });
        const result = await this.chatService.previewTemplate(displayData.template_id, variables);
        this.previewUrlCache.set({ hash: currentHash, url: result.preview_url });
        window.open(result.preview_url, '_blank');
        this.previewCompleted.emit({ success: true, url: result.preview_url });
      } else {
        const result = await this.chatService.previewExercise(exerciseData);
        this.previewUrlCache.set({ hash: currentHash, url: result.preview_url });
        window.open(result.preview_url, '_blank');
        this.previewCompleted.emit({ success: true, url: result.preview_url });
      }
    } catch (error) {
      this.previewCompleted.emit({ success: false, error: error instanceof Error ? error.message : 'Unknown error occurred' });
    } finally {
      this.isViewExerciseLoading.set(false);
    }
  }

  public async viewPleContent(): Promise<void> {
    this.isViewPleLoading.set(true);
    try {
      const result = await this.chatService.getPleContent(this.exerciseData());
      this.openPlePopup(result.ple_content);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erreur inconnue lors de la génération du code PLE.';
      this.publishFeedback.set({ type: 'error', message });
      setTimeout(() => this.publishFeedback.set(null), 6000);
    } finally {
      this.isViewPleLoading.set(false);
    }
  }

  protected closePlePopup(): void { this.isPlePopupVisible.set(false); }
  protected openPlePopup(content: string): void { this.pleContent.set(content); this.isPlePopupVisible.set(true); }

  protected onComponentsDragOver(event: DragEvent): void { event.preventDefault(); event.stopPropagation(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'; this.isComponentsDropZone.set(true); }
  protected onComponentsDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    const related = event.relatedTarget as Node | null;
    const container = (event.currentTarget as HTMLElement);
    if (!related || !container.contains(related)) {
      this.isComponentsDropZone.set(false);
    }
  }
  protected onComponentsDrop(event: DragEvent): void {
    event.preventDefault(); event.stopPropagation(); this.isComponentsDropZone.set(false);
    if (!event.dataTransfer) return;
    try {
      const dropped = JSON.parse(event.dataTransfer.getData('application/json'));
      if (dropped.type === 'component') this.addComponentInstance(dropped.name, dropped.category);
    } catch (e) { console.error('Error processing dropped component:', e); }
  }

  protected addComponentInstance(componentName: string, category: 'Formulaire' | 'Widget'): void {
    const metadata = this.componentsMetadataService.getComponentByName(componentName);
    if (!metadata) { console.error('Component metadata not found:', componentName); return; }
    this.hasInitializedComponentsFromSandbox.set(true);
    const id = `inst_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const selector = metadata.tag;
    const baseInstanceName = componentName.toLowerCase().replace(/\s+/g, '_');
    const currentData = this.currentExerciseData();
    const existing = currentData.component_instances || [];
    let instanceName = baseInstanceName; let counter = 1;
    while (existing.some(inst => inst.instanceName === instanceName)) { instanceName = `${baseInstanceName}${counter++}`; }
    const properties: { [key: string]: any } = {};
    if (metadata.properties) { for (const [key, propDef] of Object.entries(metadata.properties)) properties[key] = this.getDefaultValueForType(propDef); }
    this.updateExercise.emit({ ...currentData, component_instances: [...existing, { id, selector, componentName, instanceName, category, properties, collapsed: true }] });
  }

  protected removeComponentInstance(id: string): void {
    const d = this.currentExerciseData();
    this.updateExercise.emit({ ...d, component_instances: (d.component_instances || []).filter(i => i.id !== id) });
  }

  protected toggleComponentCollapse(id: string): void {
    const d = this.currentExerciseData();
    this.updateExercise.emit({
      ...d,
      component_instances: (d.component_instances || []).map(i =>
        i.id === id ? { ...i, collapsed: i.collapsed === false } : i
      ),
    });
  }

  protected getComponentProperties(instance: import('../../models/exercise.model').ComponentInstance): ComponentPropertyEntry[] {
    const metadata = this.componentsMetadataService.getComponentByName(instance.componentName);
    if (!metadata?.properties) return [];
    const topRequired: string[] = Array.isArray((metadata as any).required) ? (metadata as any).required : [];
    return Object.entries(metadata.properties).map(([key, propDef]: [string, any]) => {
      const rawType = propDef.type || this.getTypeFromValue(propDef);
      const isArrayOfStrings = rawType === 'array' && propDef.items && (propDef.items as any).type === 'string';
      return { key, type: rawType, description: propDef.description || '', defaultValue: propDef.default !== undefined ? propDef.default : null, required: topRequired.includes(key) || propDef.required === true, enumValues: Array.isArray(propDef.enum) ? propDef.enum : null, isArrayOfStrings: isArrayOfStrings || rawType === 'array<string>' };
    });
  }

  protected jsonErrorKey(instanceId: string, propKey: string): string { return `${instanceId}::${propKey}`; }
  protected hasJsonError(instanceId: string, propKey: string): boolean { return this.jsonParseErrors.get(this.jsonErrorKey(instanceId, propKey)) === true; }
  protected onComponentInstanceChange(): void { this.updateExercise.emit(this.cloneExerciseData(this.currentExerciseData())); }

  protected getPropertyDisplayValue(instance: import('../../models/exercise.model').ComponentInstance, key: string): string {
    const value = instance.properties[key];
    if (value === undefined || value === null) return '';
    return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  }

  protected setPropertyFromString(instance: import('../../models/exercise.model').ComponentInstance, key: string, stringValue: string, type: string): void {
    const errKey = this.jsonErrorKey(instance.id, key);
    if (type === 'array' || type === 'object') {
      try {
        instance.properties[key] = stringValue.trim() === '' ? (type === 'array' ? [] : {}) : JSON.parse(stringValue);
        this.jsonParseErrors.set(errKey, false); this.onComponentInstanceChange();
      } catch {
        try { instance.properties[key] = JSON.parse(stringValue.replace(/'/g, '"')); this.jsonParseErrors.set(errKey, false); this.onComponentInstanceChange(); }
        catch { this.jsonParseErrors.set(errKey, true); instance.properties[key] = stringValue; this.onComponentInstanceChange(); }
      }
    } else { this.jsonParseErrors.set(errKey, false); instance.properties[key] = stringValue; this.onComponentInstanceChange(); }
  }

  protected getArrayStringItems(instance: import('../../models/exercise.model').ComponentInstance, key: string): string[] {
    const value = instance.properties[key];
    return Array.isArray(value) ? value : [];
  }

  protected updateArrayStringItem(instance: import('../../models/exercise.model').ComponentInstance, key: string, index: number, newValue: string): void {
    const items = this.getArrayStringItems(instance, key);
    if (index >= 0 && index < items.length) { items[index] = newValue; instance.properties[key] = [...items]; this.onComponentInstanceChange(); }
  }

  protected addArrayStringItem(instance: import('../../models/exercise.model').ComponentInstance, key: string): void {
    const items = this.getArrayStringItems(instance, key);
    instance.properties[key] = [...items, '']; this.onComponentInstanceChange();
  }

  protected removeArrayStringItem(instance: import('../../models/exercise.model').ComponentInstance, key: string, index: number): void {
    const items = this.getArrayStringItems(instance, key);
    if (index >= 0 && index < items.length) { items.splice(index, 1); instance.properties[key] = [...items]; this.onComponentInstanceChange(); }
  }

  public openPublishDialog(): void { this.showPublishDialog.set(true); }
  protected closePublishDialog(): void { this.showPublishDialog.set(false); }

  /** True while a publish request is in flight. */
  isPublishing = signal<boolean>(false);

  protected async onPublishRequest(request: PublishExerciseRequest): Promise<void> {
    if (this.isPublishing()) return;
    this.isPublishing.set(true);
    try {
      await this.chatService.publishExercise(this.exerciseId(), request);
      this.closePublishDialog();
      this.showPublishFeedback({ type: 'success', message: 'Exercice publié avec succès.' });
    } catch (error: any) {
      this.closePublishDialog();
      const msg = error instanceof Error ? error.message : 'La publication a échoué.';
      this.showPublishFeedback({ type: 'error', message: msg });
    } finally {
      this.isPublishing.set(false);
    }
  }

  private showPublishFeedback(feedback: { type: 'success' | 'error'; message: string }): void {
    this.publishFeedback.set(feedback);
    setTimeout(() => this.publishFeedback.set(null), 4000);
  }

  public openResetExerciseConfirm(): void {
    this.showResetExerciseConfirm.set(true);
    requestAnimationFrame(() => { (document.querySelector('.exercise-content .confirm-overlay') as HTMLElement)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); });
  }

  /** Called by the workspace page unified reset action, bypassing the panel's own confirm dialog. */
  public doConfirmResetExerciseExternal(): void {
    this.showResetExerciseConfirm.set(false);
    this.resetExercise();
    this.scrollToTop();
  }

  protected doConfirmResetExercise(): void { this.showResetExerciseConfirm.set(false); this.resetExercise(); this.scrollToTop(); }
  protected doCancelResetExercise(): void { this.showResetExerciseConfirm.set(false); this.scrollToTop(); }

  private scrollToTop(): void { requestAnimationFrame(() => { (document.querySelector('.exercise-content') as HTMLElement)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }); }

  protected getSandboxVariablesList(): { key: string; value: string }[] {
    if (this.sandboxVarsPending !== null) return this.sandboxVarsPending;
    const sandboxVars = this.currentExerciseData().sandbox_variables || {};
    const list: { key: string; value: string }[] = [];
    for (const [key, value] of Object.entries(sandboxVars)) {
      if (typeof value === 'object' && value !== null && 'cid' in value) continue;
      if (key === 'author') continue;
      list.push({ key, value: typeof value === 'string' ? value : JSON.stringify(value) });
    }
    this.sandboxVarsPending = list.slice();
    return this.sandboxVarsPending;
  }

  protected addSandboxVariable(): void {
    this.getSandboxVariablesList();
    let counter = 1; let candidate = `var${counter}`;
    while (this.sandboxVarsPending!.some(v => v.key === candidate)) { candidate = `var${++counter}`; }
    this.sandboxVarsPending!.push({ key: candidate, value: '' });
    this.onSandboxVariableChange();
  }

  protected removeSandboxVariable(index: number): void {
    const list = this.getSandboxVariablesList();
    if (index < 0 || index >= list.length) return;
    list.splice(index, 1); this.onSandboxVariableChange();
  }

  protected onSandboxVariableKeyChange(index: number, newKey: string): void { const list = this.getSandboxVariablesList(); if (index >= 0 && index < list.length) { list[index].key = newKey; this.onSandboxVariableChange(); } }
  protected onSandboxVariableValueChange(index: number, newValue: string): void { const list = this.getSandboxVariablesList(); if (index >= 0 && index < list.length) { list[index].value = newValue; this.onSandboxVariableChange(); } }

  protected onSandboxVariableChange(): void {
    const currentData = this.currentExerciseData();
    const sandboxVars: { [key: string]: any } = {};
    for (const [key, value] of Object.entries(currentData.sandbox_variables || {})) { if (typeof value === 'object' && value !== null && 'cid' in value) sandboxVars[key] = value; }
    for (const item of this.getSandboxVariablesList()) {
      if (item.key && item.key !== 'author') {
        try { sandboxVars[item.key] = item.value.trim() === '' ? '' : (item.value.startsWith('{') || item.value.startsWith('[') ? JSON.parse(item.value) : item.value); }
        catch { sandboxVars[item.key] = item.value; }
      }
    }
    this.updateExercise.emit({ ...currentData, sandbox_variables: sandboxVars });
  }

  protected resetExercise(): void {
    const empty: ExerciseData = { name: '', description: '', titre: '', enonce: '', forme: '', solution: '', indications: [], theories: [], components: [], component_instances: [], sandbox: 'python', construction: '', evaluation: '', sandbox_variables: {}, config_variables: undefined, template_id: undefined, metadata: { levels: [], topics: [], readme: undefined } };
    this.currentTemplateName.set(null);
    this.hasInitializedComponentsFromSandbox.set(false);
    this.updateExercise.emit(empty);
  }

  public setComponentsInitialized(): void { this.hasInitializedComponentsFromSandbox.set(true); }

  private isCompleteComponentInstance(instance: any): instance is import('../../models/exercise.model').ComponentInstance {
    return !!instance && typeof instance.id === 'string' && typeof instance.componentName === 'string' && typeof instance.instanceName === 'string' && (instance.category === 'Formulaire' || instance.category === 'Widget') && typeof instance.properties === 'object' && instance.properties !== null;
  }

  private cloneExerciseData(data: ExerciseData): ExerciseData { return JSON.parse(JSON.stringify(data ?? {})); }


  private getDefaultValueForType(propDef: any): any {
    if (propDef.hasOwnProperty('default')) return propDef.default;
    const type = propDef.type || typeof propDef;
    if (type === 'boolean') return false; if (type === 'number') return 0; if (type === 'string') return ''; if (type === 'array') return []; if (type === 'object') return {}; return '';
  }

  private getTypeFromValue(value: any): string {
    if (typeof value === 'boolean') return 'boolean'; if (typeof value === 'number') return 'number'; if (Array.isArray(value)) return 'array'; if (typeof value === 'object' && value !== null) return 'object'; return 'string';
  }
}


