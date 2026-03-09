import {
  Component, signal, computed, ElementRef, ViewChild, AfterViewInit,
  Output, EventEmitter, inject, PLATFORM_ID, Inject, ChangeDetectorRef,
  OnDestroy,
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ChatService } from '../../services/chat.service';
import { ComponentsMetadataService } from '../../services/components-metadata.service';
import { ChatResponse } from '../../models/exercise.model';
import { ExerciseService } from '../../services/exercise.service';
import { LlmCapabilitiesService } from '../../../../core/llm/llm-capabilities.service';
import { Message, ComponentBadge, AssistantMode, GenerationDetailStatus } from './discussion.models';
import { DiscussionCache } from './discussion.cache';
import { GenerationTimeline } from './generation-timeline';
import { HelpPopupComponent } from '../../../../shared/ui/help-popup/help-popup.component';
import { MessageBubbleComponent } from './message-bubble/message-bubble.component';
import { ChatInputComponent } from './chat-input/chat-input.component';
import { ConfirmDialogComponent } from '../../../../shared/ui/confirm-dialog/confirm-dialog.component';
import { DISCUSSION_HELP_CONTENT } from '../../models/help-content.constants';

@Component({
  selector: 'app-discussion-panel',
  standalone: true,
  imports: [CommonModule, HelpPopupComponent, MessageBubbleComponent, ChatInputComponent, ConfirmDialogComponent],
  templateUrl: './discussion-panel.component.html',
  styleUrls: ['../workspace.shared.scss', './discussion-panel.component.scss'],
})
export class DiscussionPanelComponent implements AfterViewInit, OnDestroy {
  protected readonly discussionHelpContent = DISCUSSION_HELP_CONTENT;

  // Messages state
  messages = signal<Message[]>([]);

  // Component badges in input
  componentBadges = signal<ComponentBadge[]>([]);

  // Parameter badges in input
  parameterBadges = signal<{ name: string; type: string }[]>([]);

  // Field badges in input
  fieldBadges = signal<{ name: string }[]>([]);

  // Attached files (only used when file upload is supported)
  attachedFiles = signal<File[]>([]);

  // Files already uploaded to the session (persisted across messages and refresh)
  uploadedFiles = signal<import('../../../../core/llm/llm-capabilities.service').UploadedFileEntry[]>([]);

  // Locked conversation mode after first generation (null = not yet decided)
  conversationMode = signal<string | null>(null);

  /**
   * Stable UUID that identifies this conversation in the backend log tables.
   * Generated once when the first message is sent, persisted in the local cache,
   * and regenerated whenever the conversation is reset.
   */
  private conversationId = signal<string>(this._newConversationId());

  private _newConversationId(): string {
    return crypto.randomUUID();
  }

  /**
   * When true, the backend will skip template matching entirely and always
   * generate a fully custom exercise from scratch.  Can only be toggled
   * before the first message is sent (i.e. before generation has started).
   */
  forcePureExercise = signal<boolean>(false);

  /**
   * True once at least one *generation* message exists in the conversation.
   * Discussion messages (mode 'ask') do not lock the generation mode.
   * At that point the generation mode is implicitly locked by the exercise
   * state, so the forcePureExercise toggle must be hidden and replaced by
   * the locked-mode indicator strip.
   */
  readonly isGenerationLocked = computed(
    () => this.messages().some(m => m.source === 'generation')
  );

  // Drag state
  isDragOver = false;

  protected readonly resetDiscussionDialogOptions = {
    title: 'Effacer la conversation ?',
    description: 'L\'historique complet de cette conversation sera supprim茅 d茅finitivement. Le contenu de l\'exercice en cours ne sera pas affect茅.',
    confirmLabel: 'Effacer',
    variant: 'danger' as const,
  };

  // Input state
  inputText = signal<string>('');

  // Selected assistant mode
  selectedAssistantMode = signal<AssistantMode>('ask');


  // Loading state pour bloquer l'envoi pendant que le LLM repond
  isProcessing = signal<boolean>(false);

  showResetDiscussionConfirm = signal<boolean>(false);
  uploadFeedback = signal<{ type: 'error'; message: string } | null>(null);

  private readonly FIELD_NAME_MAP: { [key: string]: string } = {
    'titre': 'title',
    'enonce': 'statement',
    'forme': 'form',
    'solution': 'solution',
    'indications': 'hint',
    'theories': 'theories',
    'sandbox': 'sandbox',
    'construction': 'builder',
    'evaluation': 'grader'
  };

  // Input for exercise state
  // @Input() exerciseState!: ExerciseData;

  @ViewChild('messagesContainer') messagesContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('chatInputRef') chatInputRef!: ChatInputComponent;

  @Output() chatResponse = new EventEmitter<ChatResponse>();

  @Output() collapsed = new EventEmitter<void>();

  @Output() switchToTemplates = new EventEmitter<void>();

  protected readonly isPanelSwitcherOpen = signal(false);

  private readonly componentsMetadataService = inject(ComponentsMetadataService);
  readonly llmCapabilities = inject(LlmCapabilitiesService);
  private readonly isBrowser: boolean;

  private readonly cache: DiscussionCache;
  private readonly timeline = new GenerationTimeline(12);
  private generationTimelineMessageId: string | null = null;
  private readonly askTypingDelayMs = 16;
  private readonly cdr = inject(ChangeDetectorRef);
  private userHasScrolledUp = false;
  private scrollListenerAttached = false;
  private typingAborted = false;
  private uploadFeedbackTimer: ReturnType<typeof setTimeout> | null = null;

  /**
   * Identifies the currently active generation.  A new UUID is assigned each
   * time a generation request is dispatched.  Setting it to null immediately
   * invalidates any in-flight result so that a stopped or superseded
   * generation can never overwrite the current exercise state.
   */
  private _activeGenerationId: string | null = null;

  /**
   * Bound listener kept so it can be removed in ngOnDestroy.
   * Only registered for `beforeunload` (actual tab/window close), NOT for
   * `visibilitychange`, because switching tabs or minimising the window must
   * never interrupt an ongoing generation.
   */
  private readonly _onBeforeUnload = (): void => this._stopIfGenerating();

  /** Maps attached file name → file_id returned by backend upload. */
  private readonly pendingFileIds = new Map<string, string>();

  /** Signal tracking which files are currently being processed/uploaded. */
  protected readonly processingFiles = signal<string[]>([]);

  constructor(
    private readonly chatService: ChatService,
    private readonly exerciseService: ExerciseService,
    @Inject(PLATFORM_ID) platformId: Object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
    this.cache = new DiscussionCache(this.isBrowser);
    this.initDiscussionCache();

    if (this.isBrowser) {
      window.addEventListener('beforeunload', this._onBeforeUnload);
    }
  }

  ngOnDestroy(): void {
    if (this.isBrowser) {
      window.removeEventListener('beforeunload', this._onBeforeUnload);
    }
    // If a generation was running when the component is destroyed (e.g. navigation),
    // abort the fetch stream and notify the backend.
    this._stopIfGenerating();
  }

  /**
   * Abort the current generation immediately if one is in progress.
   * Uses forceAbort() (synchronous AbortController path) so the connection is
   * dropped before the browser unloads or the component is destroyed.
   */
  private _stopIfGenerating(): void {
    if (!this.isProcessing()) return;
    // Fire-and-forget: we cannot await inside beforeunload or ngOnDestroy.
    void this.chatService.forceAbort();
  }

  ngAfterViewInit(): void {
    this.scrollToBottom(true);
    setTimeout(() => this.attachScrollListener(), 100);
  }

  private attachScrollListener(): void {
    if (!this.isBrowser || this.scrollListenerAttached) return;
    const container = this.messagesContainer?.nativeElement;
    if (!container) return;
    container.addEventListener('scroll', () => {
      const threshold = 80;
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      this.userHasScrolledUp = distanceFromBottom > threshold;
    }, { passive: true });
    this.scrollListenerAttached = true;
  }

  protected onSend(text: string): void {
    void this.handleSendMessage(text);
  }

  protected async onFilesDropped(files: File[]): Promise<void> {
    for (const file of files) {
      this.processingFiles.update(pf => [...pf, file.name]);
      try {
        const fileId = await this.llmCapabilities.uploadFile(file);
        this.pendingFileIds.set(file.name, fileId);
        this.attachedFiles.update(c => [...c, file]);
      } catch (error) {
        if (this.isTokenLimitExceededError(error)) {
          this.showUploadError(
            `Le fichier « ${file.name} » dépasse la limite de taille autorisée. Veuillez utiliser un fichier plus petit.`
          );
        } else if (this.isBinaryFormatError(error)) {
          this.showUploadError(
            `Le type du fichier « ${file.name} » n'est pas supporté. Seuls les documents textuels sont acceptés (pas de fichiers binaires).`
          );
        } else {
          this.showUploadError(
            `Le fichier « ${file.name} » n'a pas pu être chargé.`
          );
        }
      } finally {
        this.processingFiles.update(pf => pf.filter(n => n !== file.name));
      }
    }
  }

  private isBinaryFormatError(error: unknown): boolean {
    if (!(error instanceof Error)) return false;
    return /binary format|type.*not.*support/i.test(error.message);
  }

  protected async handleSendMessage(messageContent: string): Promise<void> {
    if (this.isProcessing()) return;
    if (messageContent.trim().length === 0 &&
        this.componentBadges().length === 0 &&
        this.parameterBadges().length === 0 &&
        this.fieldBadges().length === 0 &&
        this.attachedFiles().length === 0) return;

    this.isProcessing.set(true);
    const selectedComponents = this.componentBadges().map(b => b.tag);
    const attachedFields = this.fieldBadges().map(f => f.name);
    const attachedParameters = this.parameterBadges().map(p => p.name);
    const filesToUpload = [...this.attachedFiles()];
    const acceptedFileNames = [...this.uploadedFiles().map(e => e.filename)];
    const fieldsToModify = [
      ...this.fieldBadges().map(f => this.FIELD_NAME_MAP[f.name] || f.name),
      ...this.parameterBadges().map(p => p.name),
    ].filter((name, index, self) => self.indexOf(name) === index);

    try {
      // Files in attachedFiles are already uploaded at attachment time
      acceptedFileNames.push(...filesToUpload.map(f => f.name));

      const hasPayloadAfterValidation = messageContent.trim().length > 0 ||
        this.componentBadges().length > 0 ||
        this.parameterBadges().length > 0 ||
        this.fieldBadges().length > 0 ||
        acceptedFileNames.length > 0;

      if (!hasPayloadAfterValidation) {
        this.attachedFiles.set([]);
        this.saveCache();
        return;
      }

      const currentMode = this.selectedAssistantMode();
      const messageSource: 'generation' | 'discussion' = currentMode === 'agent' ? 'generation' : 'discussion';

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: messageContent,
        components: this.componentBadges().map(b => b.name),
        timestamp: new Date(),
        attachedFields: attachedFields.length > 0 ? attachedFields : undefined,
        attachedParameters: attachedParameters.length > 0 ? attachedParameters : undefined,
        attachedFileNames: acceptedFileNames.length > 0 ? acceptedFileNames : undefined,
        source: messageSource,
      };
      this.messages.update(msgs => [...msgs, userMessage]);
      this.componentBadges.set([]);
      this.parameterBadges.set([]);
      this.fieldBadges.set([]);
      this.attachedFiles.set([]);
      this.uploadedFiles.set([]);
      this.pendingFileIds.clear();
      this.llmCapabilities.resetSessionFileCount();
      this.inputText.set('');
      this.userHasScrolledUp = false;
      this.saveCache();
      this.scrollToBottom(true);

      if (currentMode === 'ask') {
        const qaResponse = await this.chatService.askPlatonDocs(messageContent, 5, this.conversationId());
        const answerText = qaResponse.error
          ? qaResponse.error
          : (qaResponse.answer || 'Aucune reponse.');
        await this.typeAnswer(this.toPlainText(answerText), 'discussion');
        return;
      }

      const conversationHistory = this.messages()
        .filter(msg => msg.role === 'user' && msg.source !== 'discussion')
        .map(msg => ({
          role: msg.role as 'user' | 'ai' | 'system',
          content: msg.content,
          components: msg.components
        }));

      const generationId = crypto.randomUUID();
      this._activeGenerationId = generationId;

      await this.chatService.sendChatRequest(
        this.exerciseService.exerciseData(),
        messageContent,
        selectedComponents,
        conversationHistory,
        fieldsToModify,
        (event) => this.handleChatEvent(event, generationId),
        undefined,
        this.conversationMode() ?? undefined,
        this.forcePureExercise(),
        this.conversationId(),
      );
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // The fetch was aborted (either via the stop button or component destruction).
        // If a timeline message is in progress, mark it as stopped.
        if (this.generationTimelineMessageId) {
          this.timeline.forceFlush();
          this.timeline.markAllStopped();
          this.timeline.enqueueDetail('Génération interrompue.', 'warning');
          this.timeline.forceFlush();
          this.messages.update(msgs => msgs.map(m =>
            m.id === this.generationTimelineMessageId
              ? { ...m, generationTimeline: this.timeline.build(), state: 'stopped' as const }
              : m
          ));
          this.generationTimelineMessageId = null;
        }
        this.saveCache();
        this.scrollToBottom();
        return;
      }
      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: 'ai',
        content: error instanceof Error
          ? error.message
          : 'Erreur lors de l\'envoi du message.',
        components: [],
        timestamp: new Date()
      };
      this.messages.update(msgs => [...msgs, errorMessage]);
      this.saveCache();
      this.scrollToBottom();
    } finally {
      setTimeout(() => {
        this.isProcessing.set(false);
        this.cdr.markForCheck();
      }, 0);
    }
  }

  protected stopGeneration(): void {
    this.typingAborted = true;
    this._activeGenerationId = null;
    this.chatService.stopGeneration();

    // Safety fallback: if the backend's 'stopped' event is never received
    // (e.g. network issue), reset the processing state after 5 seconds.
    setTimeout(() => {
      if (this.isProcessing()) {
        if (this.generationTimelineMessageId) {
          this.timeline.forceFlush();
          this.timeline.markAllStopped();
          this.timeline.forceFlush();
          this.messages.update(msgs => msgs.map(m =>
            m.id === this.generationTimelineMessageId
              ? { ...m, generationTimeline: this.timeline.build(), state: 'stopped' as const }
              : m
          ));
          this.generationTimelineMessageId = null;
          this.saveCache();
          this.scrollToBottom();
        }
        this.isProcessing.set(false);
        this.cdr.markForCheck();
      }
    }, 5000);
  }
  protected dismissUploadFeedback(): void {
    this.uploadFeedback.set(null);
    if (this.uploadFeedbackTimer) {
      clearTimeout(this.uploadFeedbackTimer);
      this.uploadFeedbackTimer = null;
    }
  }

  protected handleChatEvent(event: { type: string; data: unknown }, generationId: string): void {
    switch (event.type) {
      case 'generation_started':
        this.startGenerationTimeline();
        return;
      case 'stopped': {
        // The backend confirmed the generation was explicitly stopped.
        // Mark the timeline as stopped and stop the loading animation.
        this.timeline.forceFlush();
        this.timeline.markAllStopped();
        this.timeline.enqueueDetail('Génération interrompue par l\'utilisateur.', 'warning');
        this.timeline.forceFlush();
        if (this.generationTimelineMessageId) {
          this.messages.update(msgs => msgs.map(m =>
            m.id === this.generationTimelineMessageId
              ? { ...m, generationTimeline: this.timeline.build(), state: 'stopped' as const }
              : m
          ));
          this.generationTimelineMessageId = null;
        }
        this.saveCache();
        this.scrollToBottom();
        setTimeout(() => {
          this.isProcessing.set(false);
          this.cdr.markForCheck();
        }, 0);
        return;
      }
      case 'variables_applied':
        this.timeline.markStep('generation', 'completed');
        this.timeline.markStep('sandbox', 'in_progress');
        this.refreshTimeline();
        return;
      case 'generation_mode': {
        const data = event.data as { mode_label?: string; mode?: string };
        const label = this.timeline.sanitize((data?.mode_label || data?.mode || '').toString());
        this.timeline.handleGenerationMode(label, (text, status) => this.enqueueDetail(text, status));
        return;
      }
      case 'ping':
        if (this.generationTimelineMessageId) this.refreshTimeline();
        return;
      case 'sandbox_retry': {
        const data = event.data as { attempt: number; max_attempts: number; error?: string };
        const cleanError = this.extractSandboxMessage(data.error);
        if (cleanError) {
          this.enqueueDetail(cleanError, 'error');
        }
        this.enqueueDetail(`Correction automatique — tentative ${data.attempt}/${data.max_attempts}`, 'start');
        this.refreshTimeline();
        return;
      }
      case 'complete': {
        if (generationId !== this._activeGenerationId) {
          return;
        }
        const data = event.data as { exercise_data?: unknown; url?: string; conversation_mode?: string };
        if (data.exercise_data) this.exerciseService.exerciseData.set(data.exercise_data as Parameters<typeof this.exerciseService.exerciseData.set>[0]);
        if (data.conversation_mode) this.conversationMode.set(data.conversation_mode);
        this.timeline.markStep('analysis', 'completed');
        this.timeline.markStep('generation', 'completed');
        this.timeline.markStep('sandbox', 'completed');
        this.finishTimeline('completed');
        if (data.url) setTimeout(() => window.open(data.url as string, '_blank'), 1000);
        this.saveCache();
        this.scrollToBottom();
        return;
      }
      case 'error': {
        if (generationId !== this._activeGenerationId) {
          return;
        }
        const data = event.data as { value?: string; conversation_mode?: string; exercise_data?: unknown };
        if (data.exercise_data) this.exerciseService.exerciseData.set(data.exercise_data as Parameters<typeof this.exerciseService.exerciseData.set>[0]);
        if (data.conversation_mode) this.conversationMode.set(data.conversation_mode);
        const rawValue = (data.value || '').toString();
        const sandboxMsg = this.extractSandboxMessage(rawValue);
        const errorText = sandboxMsg
          ? sandboxMsg
          : 'Une erreur interne est survenue. Veuillez r茅essayer.';
        this.enqueueDetail(errorText, 'error');
        this.timeline.markStep('analysis', 'completed');
        this.timeline.markStep('generation', 'completed');
        this.timeline.markStep('sandbox', 'error');
        this.finishTimeline('error');
        this.saveCache();
        this.scrollToBottom();
        return;
      }
      default:
        if (event.type.endsWith('_started') || event.type.endsWith('_completed')) {
          this.timeline.handleDetailedEvent(
            event.type,
            event.data as Record<string, unknown>,
            (t) => this.timeline.sanitize(t),
            (text, status, url) => this.enqueueDetail(text, status, url),
            (text, status, children) => this.enqueueGroupDetail(text, status, children)
          );
          this.refreshTimeline();
        }
        return;
    }
  }

  private extractSandboxMessage(raw: string | undefined): string | null {
    if (!raw) return null;

    const responseMatch = raw.match(/['"]message['"]:\s*['"]([^'"]+)['"]/);
    if (responseMatch?.[1]) {
      return this.timeline.sanitize(responseMatch[1]);
    }

    const previewMatch = raw.match(/Preview failed[^:]*:\s*(.+)$/i);
    if (previewMatch?.[1]) {
      const inner = previewMatch[1].trim();
      const innerMsg = this.extractSandboxMessage(inner);
      return innerMsg ?? this.timeline.sanitize(inner);
    }

    const runtimeErrorMatch = raw.match(/\[ERROR]\s*(.+)/);
    if (runtimeErrorMatch?.[1]) {
      return this.timeline.sanitize(runtimeErrorMatch[1].trim());
    }

    const graderRuntimeMatch = raw.match(/Grader runtime errors detected:\s*(.+)/is);
    if (graderRuntimeMatch?.[1]) {
      const inner = graderRuntimeMatch[1].trim().replace(/\[ERROR]\s*/g, '');
      return this.timeline.sanitize(inner);
    }

    const sandboxRuntimeMatch = raw.match(/Sandbox runtime errors detected:\s*(.+)/is);
    if (sandboxRuntimeMatch?.[1]) {
      const inner = sandboxRuntimeMatch[1].trim().replace(/\[ERROR]\s*/g, '');
      return this.timeline.sanitize(inner);
    }

    if (/Parse error|Expecting|got '|sandbox|compilation|ModuleNotFoundError|NameError|SyntaxError|TypeError|AttributeError|ImportError/i.test(raw)) {
      const firstLine = raw.split('\n')[0].trim();
      return this.timeline.sanitize(firstLine || raw);
    }

    return null;
  }

  private startGenerationTimeline(): void {
    this.timeline.start();
    const id = crypto.randomUUID();
    this.generationTimelineMessageId = id;
    const msg: Message = { id, role: 'system', content: '', components: [], timestamp: new Date(), state: 'in_progress', generationTimeline: this.timeline.build(), source: 'generation' };
    this.messages.update(msgs => [...msgs, msg]);
    this.saveCache(); this.scrollToBottom(true);
  }

  private refreshTimeline(): void {
    if (!this.generationTimelineMessageId) return;
    this.messages.update(msgs => msgs.map(m => m.id === this.generationTimelineMessageId ? { ...m, generationTimeline: this.timeline.build() } : m));
    this.saveCache(); this.scrollToBottom();
  }

  private finishTimeline(state: 'completed' | 'error'): void {
    if (!this.generationTimelineMessageId) return;
    this.timeline.forceFlush();
    this.messages.update(msgs => msgs.map(m => m.id === this.generationTimelineMessageId ? { ...m, generationTimeline: this.timeline.build(), state } : m));
    this.generationTimelineMessageId = null;
    this.saveCache(); this.scrollToBottom();
  }

  private enqueueDetail(text: string, status: GenerationDetailStatus, url?: string): void {
    this.timeline.enqueueDetail(text, status, url, () => this.refreshTimeline());
  }

  private enqueueGroupDetail(text: string, status: GenerationDetailStatus, children: { text: string; url?: string }[]): void {
    this.timeline.enqueueGroupDetail(text, status, children, () => this.refreshTimeline());
  }
  private showUploadError(message: string): void {
    this.uploadFeedback.set({ type: 'error', message });
    if (this.uploadFeedbackTimer) clearTimeout(this.uploadFeedbackTimer);
    this.uploadFeedbackTimer = setTimeout(() => {
      this.uploadFeedback.set(null);
      this.uploadFeedbackTimer = null;
    }, 6000);
  }

  private isTokenLimitExceededError(error: unknown): boolean {
    if (!(error instanceof Error)) return false;
    return /FILE_CONTENT_MAX_TOKENS/i.test(error.message) ||
      /limite de tokens|token limit/i.test(error.message);
  }

  protected removeComponentBadge(tag: string): void { this.componentBadges.update(b => b.filter(x => x.tag !== tag)); this.saveCache(); }
  protected removeParameterBadge(name: string): void { this.parameterBadges.update(p => p.filter(x => x.name !== name)); this.saveCache(); }
  protected removeFieldBadge(name: string): void { this.fieldBadges.update(f => f.filter(x => x.name !== name)); this.saveCache(); }
  protected removeAttachedFile(name: string): void {
    this.attachedFiles.update(c => c.filter(f => f.name !== name));
    const fileId = this.pendingFileIds.get(name);
    if (fileId) {
      this.pendingFileIds.delete(name);
      this.llmCapabilities.deleteSingleFile(fileId).catch(err =>
        console.warn('[DiscussionPanel] Could not delete file from backend:', err)
      );
    }
  }

  addMessage(message: Message): void { this.messages.update(msgs => [...msgs, message]); this.saveCache(); this.scrollToBottom(); }

  addComponentBadge(name: string, tag: string, type: 'formulaire' | 'widget'): void {
    if (!this.componentBadges().some(b => b.tag === tag)) { this.componentBadges.update(b => [...b, { name, tag, type }]); this.saveCache(); }
  }

  protected setAssistantMode(mode: AssistantMode): void {
    if (this.selectedAssistantMode() === mode) return;
    this.selectedAssistantMode.set(mode); this.saveCache();
  }

  protected onDragOver(event: DragEvent): void { event.preventDefault(); event.stopPropagation(); this.isDragOver = true; if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'; }
  protected onDragLeave(event: DragEvent): void { event.preventDefault(); event.stopPropagation(); this.isDragOver = false; }

  protected onDrop(event: DragEvent): void {
    event.preventDefault(); event.stopPropagation(); this.isDragOver = false;
    const externalFiles = event.dataTransfer?.files;
    if (externalFiles && externalFiles.length > 0) {
      if (this.llmCapabilities.fileUploadSupported()) this.onFilesDropped(Array.from(externalFiles));
      return;
    }
    try {
      const data = event.dataTransfer?.getData('application/json');
      if (!data) return;
      const dropped = JSON.parse(data) as { type: string; name: string; paramType?: string; category?: string };
      if (dropped.type === 'parameter') this.addParameterBadge(dropped.name, dropped.paramType ?? '');
      else if (dropped.type === 'field') this.addFieldBadge(dropped.name);
      else if (dropped.type === 'component') {
        const metadata = this.componentsMetadataService.getComponentByName(dropped.name);
        if (metadata) this.addComponentBadge(dropped.name, metadata.tag, (dropped.category ?? '').toLowerCase() as 'formulaire' | 'widget');
      }
    } catch (e) { console.error('[DiscussionPanel] Error processing dropped item:', e); }
  }

  addParameterBadge(name: string, type: string): void {
    if (!this.parameterBadges().some(p => p.name === name)) { this.parameterBadges.update(p => [...p, { name, type }]); this.saveCache(); }
  }

  addFieldBadge(name: string): void {
    if (!this.fieldBadges().some(f => f.name === name)) { this.fieldBadges.update(f => [...f, { name }]); this.saveCache(); }
  }

  protected openResetDiscussionConfirm(): void { this.showResetDiscussionConfirm.set(true); }
  protected cancelResetDiscussion(): void { this.showResetDiscussionConfirm.set(false); }

  protected toggleForcePureExercise(): void {
    if (this.isGenerationLocked()) return;
    this.forcePureExercise.update(v => !v);
    this.saveCache();
  }

  protected async confirmResetDiscussion(): Promise<void> {
    this.showResetDiscussionConfirm.set(false);
    await this.resetDiscussion();
  }

  async resetDiscussion(): Promise<void> {
    // Always purge uploaded files from the backend so the session slot is
    // freed immediately, regardless of which caller triggers the reset.
    if (this.llmCapabilities.fileUploadSupported() && this.llmCapabilities.sessionFileCount() > 0) {
      try { await this.llmCapabilities.deleteAllSessionFiles(); }
      catch (err) { console.error('[DiscussionPanel] Failed to delete session files on reset:', err); }
    }
    this.llmCapabilities.resetSessionFileCount();
    this._activeGenerationId = null;
    this.messages.set([]); this.componentBadges.set([]); this.parameterBadges.set([]);
    this.fieldBadges.set([]); this.attachedFiles.set([]); this.uploadedFiles.set([]);
    this.pendingFileIds.clear();
    this.inputText.set('');
    this.conversationMode.set(null);
    this.forcePureExercise.set(false);
    this.conversationId.set(this._newConversationId());
    this.saveCache();
  }

  private initDiscussionCache(): void {
    if (!this.isBrowser) return;
    this.cache.init();
    const restored = this.cache.read();
    if (!restored) return;
    this.messages.set(this.cache.deserializeMessages(restored.messages));
    this.componentBadges.set(Array.isArray(restored.componentBadges) ? restored.componentBadges : []);
    this.parameterBadges.set(Array.isArray(restored.parameterBadges) ? restored.parameterBadges : []);
    this.fieldBadges.set(Array.isArray(restored.fieldBadges) ? restored.fieldBadges : []);
    this.inputText.set(restored.inputText ?? '');
    this.selectedAssistantMode.set(restored.assistantMode === 'agent' ? 'agent' : 'ask');
    this.forcePureExercise.set(restored.forcePureExercise === true);
    if (restored.conversationId) {
      this.conversationId.set(restored.conversationId);
    }
    if (Array.isArray(restored.uploadedFiles) && restored.uploadedFiles.length > 0) {
      this.llmCapabilities.getSessionFiles()
        .then(_ => {})
        .catch(err => console.warn('[DiscussionPanel] Could not reconcile session files:', err));
    }
  }

  private saveCache(): void {
    if (!this.isBrowser) return;
    this.cache.refresh();
    this.cache.write({
      messages: this.cache.serializeMessages(this.messages()),
      componentBadges: this.componentBadges(), parameterBadges: this.parameterBadges(),
      fieldBadges: this.fieldBadges(), inputText: this.inputText(),
      assistantMode: this.selectedAssistantMode(), uploadedFiles: this.uploadedFiles(),
      forcePureExercise: this.forcePureExercise(),
      conversationId: this.conversationId(),
    });
  }

  private scrollToBottom(force = false): void {
    setTimeout(() => {
      const c = this.messagesContainer?.nativeElement;
      if (!c) return;
      if (force || !this.userHasScrolledUp) {
        c.scrollTop = c.scrollHeight;
      }
    }, 0);
  }

  private toPlainText(answer: string): string {
    return (answer || '')
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/__(.*?)__/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/^\s*#{1,6}\s*/gm, '')
      .replace(/\[(.*?)]\((.*?)\)/g, '$1')
      .trim();
  }

  private async typeAnswer(answer: string, source: 'generation' | 'discussion' = 'discussion'): Promise<void> {
    this.typingAborted = false;
    const id = crypto.randomUUID();
    this.messages.update(msgs => [...msgs, { id, role: 'ai', content: '', components: [], timestamp: new Date(), state: 'in_progress', source }]);
    this.saveCache(); this.scrollToBottom(true);
    if (!answer) {
      this.messages.update(msgs => msgs.map(m => m.id === id ? { ...m, content: 'Aucune réponse.', state: 'completed' } : m));
      this.saveCache(); return;
    }
    for (let i = 1; i <= answer.length; i++) {
      if (this.typingAborted) {
        this.messages.update(msgs => msgs.map(m => m.id === id ? { ...m, state: 'completed' } : m));
        this.saveCache();
        break;
      }
      let updated = false;
      this.messages.update(msgs => msgs.map(m => {
        if (m.id !== id) return m; updated = true;
        return { ...m, content: answer.slice(0, i), state: i === answer.length ? 'completed' : 'in_progress' };
      }));
      if (!updated) break;
      if (i % 8 === 0 || i === answer.length) { this.saveCache(); this.scrollToBottom(); }
      if (i < answer.length) await new Promise(r => setTimeout(r, this.askTypingDelayMs));
    }
  }

  protected togglePanelSwitcher(): void {
    this.isPanelSwitcherOpen.update(v => !v);
  }

  protected closePanelSwitcher(): void {
    this.isPanelSwitcherOpen.set(false);
  }

  protected doSwitchToTemplates(): void {
    this.closePanelSwitcher();
    this.switchToTemplates.emit();
  }
}







