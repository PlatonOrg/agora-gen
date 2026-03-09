import {
  ChangeDetectionStrategy,
  Component, input, output, signal, ViewChild, ElementRef,
  AfterViewInit, inject, PLATFORM_ID, computed
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { LlmCapabilitiesService } from '../../../../../core/llm/llm-capabilities.service';
import { FileValidationService } from '../../../services/file-validation.service';
import { AssistantMode, ComponentBadge } from '../discussion.models';
import { AttachmentBadgesComponent } from '../attachment-badges/attachment-badges.component';

@Component({
  selector: 'app-chat-input',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, AttachmentBadgesComponent],
  templateUrl: './chat-input.component.html',
  styleUrl: './chat-input.component.scss',
})
export class ChatInputComponent implements AfterViewInit {
  isProcessing = input<boolean>(false);
  assistantMode = input<AssistantMode>('ask');
  componentBadges = input<ComponentBadge[]>([]);
  parameterBadges = input<{ name: string; type: string }[]>([]);
  fieldBadges = input<{ name: string }[]>([]);
  attachedFiles = input<File[]>([]);
  processingFiles = input<string[]>([]);

  modeChange = output<AssistantMode>();
  send = output<string>();
  stop = output<void>();
  removeComponent = output<string>();
  removeParameter = output<string>();
  removeField = output<string>();
  removeFile = output<string>();
  filesDropped = output<File[]>();

  @ViewChild('inputEl') inputEl!: ElementRef<HTMLDivElement>;

  protected inputText = signal<string>('');
  protected isFocused = false;

  readonly llmCapabilities = inject(LlmCapabilitiesService);
  private readonly fileValidation = inject(FileValidationService);
  private readonly isBrowser: boolean;

  constructor() {
    this.isBrowser = isPlatformBrowser(inject(PLATFORM_ID));
  }

  protected readonly placeholder = computed(() =>
    this.assistantMode() === 'ask'
      ? 'Posez une question sur PLaTon ou la documentation…'
      : 'Décrivez l\'exercice à créer ou la modification souhaitée…'
  );

  protected readonly fileCount = computed(() => this.llmCapabilities.sessionFileCount());
  protected readonly maxFiles = computed(() => this.llmCapabilities.maxFiles());

  protected readonly fileAcceptAttribute = computed<string | null>(() => {
    const exts = this.llmCapabilities.acceptedExtensions();
    return exts.length === 0 ? null : exts.join(',');
  });

  protected readonly canSend = computed(() =>
    !this.isProcessing() && (
      this.inputText().trim().length > 0 ||
      this.componentBadges().length > 0 ||
      this.parameterBadges().length > 0 ||
      this.fieldBadges().length > 0 ||
      this.attachedFiles().length > 0
    )
  );

  protected readonly hasBadges = computed(() =>
    this.componentBadges().length > 0 ||
    this.parameterBadges().length > 0 ||
    this.fieldBadges().length > 0 ||
    this.attachedFiles().length > 0 ||
    this.processingFiles().length > 0
  );

  protected readonly componentNames = computed(() => this.componentBadges().map(b => b.name));
  protected readonly fieldNames = computed(() => this.fieldBadges().map(f => f.name));
  protected readonly parameterNames = computed(() => this.parameterBadges().map(p => p.name));
  protected readonly fileNames = computed(() => this.attachedFiles().map(f => f.name));

  ngAfterViewInit(): void {
    this.syncPlaceholder();
  }

  protected onInput(event: Event): void {
    const text = (event.target as HTMLDivElement).textContent ?? '';
    this.inputText.set(text);
    this.syncPlaceholder();
  }

  protected onKeyDown(event: KeyboardEvent): void {
    if (this.isProcessing()) {
      if (event.key === 'Escape') this.stop.emit();
      event.preventDefault();
      return;
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submitMessage();
    }
  }

  protected onPaste(event: ClipboardEvent): void {
    event.preventDefault();
    const text = event.clipboardData?.getData('text/plain');
    if (!text) return;
    const sel = window.getSelection();
    if (!sel?.rangeCount) return;
    sel.deleteFromDocument();
    const node = document.createTextNode(text);
    const range = sel.getRangeAt(0);
    range.insertNode(node);
    range.setStartAfter(node);
    range.setEndAfter(node);
    sel.removeAllRanges();
    sel.addRange(range);
    this.inputEl.nativeElement.dispatchEvent(new Event('input', { bubbles: true }));
  }

  protected onMouseDown(event: MouseEvent): void {
    if (this.isProcessing()) event.preventDefault();
  }

  protected onFocusEvent(): void {
    this.isFocused = true;
  }

  protected onBlurEvent(): void {
    this.isFocused = false;
  }

  protected onFocus(event: FocusEvent): void {
    this.isFocused = true;
    if (this.isProcessing()) (event.target as HTMLElement).blur();
  }

  protected onSubmit(event: Event): void {
    event.preventDefault();
    this.submitMessage();
  }

  protected submitMessage(): void {
    if (!this.canSend()) return;
    const text = this.inputText().trim();
    this.send.emit(text);
    this.inputText.set('');
    if (this.inputEl?.nativeElement) this.inputEl.nativeElement.textContent = '';
    this.syncPlaceholder();
  }

  protected setMode(mode: AssistantMode): void {
    if (this.assistantMode() !== mode) this.modeChange.emit(mode);
  }

  protected onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';
    if (files.length > 0) this.dispatchFiles(files);
  }

  private dispatchFiles(files: File[]): void {
    const maxFiles = this.maxFiles();
    const remaining = maxFiles - this.fileCount();
    if (remaining <= 0) return;
    const { accepted, rejected } = this.fileValidation.filterFiles(files, this.llmCapabilities.acceptedExtensions());
    if (rejected.length > 0) console.warn('[ChatInput] Rejected files:', rejected.map(f => f.name));
    const existing = new Set(this.attachedFiles().map(f => f.name));
    const toAdd = accepted.filter(f => !existing.has(f.name)).slice(0, remaining);
    if (toAdd.length > 0) this.filesDropped.emit(toAdd);
  }

  protected readonly removeComponentFn = (name: string) => {
    const badge = this.componentBadges().find(b => b.name === name);
    this.removeComponent.emit(badge ? badge.tag : name);
  };
  protected readonly removeFieldFn = (name: string) => this.removeField.emit(name);
  protected readonly removeParameterFn = (name: string) => this.removeParameter.emit(name);
  protected readonly removeFileFn = (name: string) => this.removeFile.emit(name);

  setTextFromSignal(text: string): void {
    if (this.inputEl?.nativeElement) this.inputEl.nativeElement.textContent = text;
    this.inputText.set(text);
    this.syncPlaceholder();
  }

  private syncPlaceholder(): void {
    if (!this.inputEl?.nativeElement) return;
    const el = this.inputEl.nativeElement;
    if (this.inputText().trim().length === 0 && !this.isProcessing()) {
      el.setAttribute('data-empty', 'true');
    } else {
      el.removeAttribute('data-empty');
    }
  }
}





