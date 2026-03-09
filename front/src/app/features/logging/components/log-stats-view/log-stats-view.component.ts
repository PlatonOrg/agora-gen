import { Component, OnInit, OnDestroy, signal, inject, computed, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogsService } from '../../../../core/logging/logs.service';
import { LlmCapabilitiesService } from '../../../../core/llm/llm-capabilities.service';
import { LlmOptionsPollingService } from '../../../../core/llm/llm-options-polling.service';
import { AppConfig, LLMOptionEntry, RuntimeSettingEntry } from '../../models/log.model';
import { LogStatusViewComponent, LoadingState } from '../log-status-view/log-status-view.component';

interface EditableSetting {
  key: string;
  value: string;
  originalValue: string;
  value_type: 'float' | 'int' | 'str' | 'bool';
  description: string;
  default: string;
  min_value: number | null;
  max_value: number | null;
  options: string[] | null;
}

@Component({
  selector: 'app-log-stats-view',
  standalone: true,
  imports: [CommonModule, FormsModule, LogStatusViewComponent],
  templateUrl: './log-stats-view.component.html',
  styleUrl: './log-stats-view.component.scss',
})
export class LogStatsViewComponent implements OnInit, OnDestroy {
  private readonly logsService = inject(LogsService);
  private readonly llmCapabilities = inject(LlmCapabilitiesService);
  protected readonly llmPolling = inject(LlmOptionsPollingService);

  protected readonly config = signal<AppConfig | null>(null);
  protected readonly state = signal<LoadingState>('loading');
  protected readonly errorMessage = signal<string | null>(null);

  /** Available LLM provider/model pairs for the dropdown. */
  protected readonly llmOptions = computed(() => this.llmPolling.options());

  /** Tracks whether an LLM config save is in progress. */
  protected readonly isSaving = signal<boolean>(false);

  /** Transient feedback message after a save attempt. */
  protected readonly saveMessage = signal<string | null>(null);
  protected readonly saveMessageType = signal<'success' | 'error'>('success');

  /** Derived: true when the selected option differs from the current config. */
  protected readonly hasUnsavedChanges = computed(() => {
    const currentProvider = this.llmPolling.currentProviderName();
    const currentModel = this.llmPolling.currentModelName();
    if (!currentProvider || !currentModel) return false;
    const currentKey = this.buildOptionKey(currentProvider, currentModel);
    return this.selectedOptionKey() !== currentKey;
  });

  /** Runtime settings loaded from the backend. */
  protected readonly runtimeSettings = signal<EditableSetting[]>([]);

  /** Tracks whether a runtime settings save is in progress. */
  protected readonly isSettingsSaving = signal<boolean>(false);

  /** Transient feedback for runtime settings save. */
  protected readonly settingsSaveMessage = signal<string | null>(null);
  protected readonly settingsSaveMessageType = signal<'success' | 'error'>('success');

  /** Derived: true when any runtime setting has been edited. */
  protected readonly hasSettingsChanges = computed(() => {
    return this.runtimeSettings().some((s: EditableSetting) => s.value !== s.originalValue);
  });

  /** The key currently selected in the dropdown ("provider::model"). */
  protected readonly selectedOptionKey = signal<string>('');

  /** Whether the info tooltip for the LLM selector is open. */
  protected readonly llmInfoOpen = signal<boolean>(false);

  /** Pixel position of the info tooltip (fixed, from button rect). */
  protected readonly llmInfoPosition = signal<{ top: number; left: number } | null>(null);

  constructor() {
    effect(() => {
      const freshOptions = this.llmPolling.options();
      if (freshOptions.length === 0) return;

      const currentKey = this.selectedOptionKey();
      const stillValid = freshOptions.some(
        (o: LLMOptionEntry) => this.buildOptionKey(o.provider, o.model) === currentKey,
      );

      if (!stillValid) {
        const fallbackProvider = this.llmPolling.currentProviderName();
        const fallbackModel = this.llmPolling.currentModelName();
        if (fallbackProvider && fallbackModel) {
          this.selectedOptionKey.set(this.buildOptionKey(fallbackProvider, fallbackModel));
        }
      }
    });
  }

  async ngOnInit(): Promise<void> {
    try {
      const [configData, settingsData] = await Promise.all([
        this.logsService.getConfig(),
        this.logsService.getRuntimeSettings().catch((err: unknown) => {
          console.warn('[LogStatsView] getRuntimeSettings failed:', err);
          return null;
        }),
      ]);

      this.config.set(configData);

      await this.llmPolling.loadOnce();

      const initialProvider = this.llmPolling.currentProviderName();
      const initialModel = this.llmPolling.currentModelName();
      if (initialProvider && initialModel) {
        this.selectedOptionKey.set(this.buildOptionKey(initialProvider, initialModel));
      }

      this.llmPolling.startPolling();

      if (settingsData) {
        this.runtimeSettings.set(
          settingsData.settings.map((s: RuntimeSettingEntry) => ({
            ...s,
            originalValue: s.value,
          })),
        );
      }

      this.state.set('success');
    } catch (err: unknown) {
      this.state.set('error');
      this.errorMessage.set(err instanceof Error ? err.message : 'Erreur inconnue');
    }
  }

  ngOnDestroy(): void {
    this.llmPolling.stopPolling();
  }

  /** Build a unique key for an option entry. */
  protected buildOptionKey(provider: string, model: string): string {
    return `${provider}::${model}`;
  }

  /** Format the display label for a dropdown option. */
  protected formatOptionLabel(option: LLMOptionEntry): string {
    return `${option.model}  [${option.provider}]`;
  }

  /** Called when the admin selects a new option from the dropdown. */
  protected onOptionChange(key: string): void {
    this.selectedOptionKey.set(key);
    this.clearSaveMessage();
  }

  /** Persist the selected provider/model to the backend. */
  protected async applyLlmConfig(): Promise<void> {
    const key = this.selectedOptionKey();
    const [provider, model] = key.split('::');
    if (!provider || !model) return;

    this.isSaving.set(true);
    this.clearSaveMessage();

    try {
      await this.logsService.setLlmConfig({ provider, model });

      const updatedConfig = await this.logsService.getConfig();
      this.config.set(updatedConfig);

      await this.llmCapabilities.loadCapabilities().catch(() => {});

      this.showSaveMessage('Configuration LLM mise a jour.', 'success');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erreur lors de la mise a jour.';
      this.showSaveMessage(message, 'error');
    } finally {
      this.isSaving.set(false);
    }
  }

  /** Open or close the LLM info tooltip, anchored to the clicked button. */
  protected showLlmInfo(event: MouseEvent): void {
    event.stopPropagation();
    if (this.llmInfoOpen()) {
      this.llmInfoOpen.set(false);
      this.llmInfoPosition.set(null);
    } else {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      this.llmInfoPosition.set({ top: rect.bottom + 8, left: rect.left + rect.width / 2 });
      this.llmInfoOpen.set(true);
    }
  }

  // -- Runtime Settings ---------------------------------------------------

  /** Called when the admin edits a setting value in the form. */
  protected onSettingChange(key: string, rawValue: string): void {
    this.runtimeSettings.update((settings: EditableSetting[]) =>
      settings.map((s: EditableSetting) => s.key === key ? { ...s, value: rawValue } : s),
    );
    this.clearSettingsSaveMessage();
  }

  /** Reset a single setting to its default value. */
  protected resetSettingToDefault(key: string): void {
    this.runtimeSettings.update((settings: EditableSetting[]) =>
      settings.map((s: EditableSetting) => s.key === key ? { ...s, value: s.default } : s),
    );
  }

  /** Reset all settings to their last-saved values (undo local edits). */
  protected discardSettingsChanges(): void {
    this.runtimeSettings.update((settings: EditableSetting[]) =>
      settings.map((s: EditableSetting) => ({ ...s, value: s.originalValue })),
    );
    this.clearSettingsSaveMessage();
  }

  /** Persist all changed runtime settings to the backend. */
  protected async applyRuntimeSettings(): Promise<void> {
    const changed = this.runtimeSettings().filter((s: EditableSetting) => s.value !== s.originalValue);
    if (changed.length === 0) return;

    const payload: Record<string, string> = {};
    for (const s of changed) {
      payload[s.key] = s.value;
    }

    this.isSettingsSaving.set(true);
    this.clearSettingsSaveMessage();

    try {
      const response = await this.logsService.updateRuntimeSettings({ settings: payload });

      this.runtimeSettings.update((settings: EditableSetting[]) =>
        settings.map((s: EditableSetting) => {
          const updatedValue = response.updated[s.key];
          return updatedValue !== undefined ? { ...s, value: updatedValue, originalValue: updatedValue } : s;
        }),
      );

      // Refresh file-support capabilities in case FILE_UPLOAD_MAX_COUNT changed.
      await this.llmCapabilities.loadCapabilities().catch(() => {});

      this.showSettingsSaveMessage(`${changed.length} parametre(s) mis a jour.`, 'success');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erreur lors de la mise a jour.';
      this.showSettingsSaveMessage(message, 'error');
    } finally {
      this.isSettingsSaving.set(false);
    }
  }

  /** Format a setting key into a human-readable label. */
  protected formatSettingLabel(key: string): string {
    return key.replace(/_/g, ' ');
  }

  /** Whether a single setting has been changed from its saved value. */
  protected isSettingDirty(setting: EditableSetting): boolean {
    return setting.value !== setting.originalValue;
  }

  private showSaveMessage(message: string, type: 'success' | 'error'): void {
    this.saveMessage.set(message);
    this.saveMessageType.set(type);
    setTimeout(() => this.clearSaveMessage(), 4000);
  }

  private clearSaveMessage(): void {
    this.saveMessage.set(null);
  }

  private showSettingsSaveMessage(message: string, type: 'success' | 'error'): void {
    this.settingsSaveMessage.set(message);
    this.settingsSaveMessageType.set(type);
    setTimeout(() => this.clearSettingsSaveMessage(), 4000);
  }

  private clearSettingsSaveMessage(): void {
    this.settingsSaveMessage.set(null);
  }

  /**
   * Extracts just the model name from a potentially full path.
   * e.g. "/opt/models/intfloat_multilingual-e5-large-instruct" → "intfloat_multilingual-e5-large-instruct"
   * e.g. "intfloat/multilingual-e5-large-instruct" → "intfloat/multilingual-e5-large-instruct"
   */
  protected extractModelName(value: string): string {
    if (!value) return value;
    // If it looks like an absolute path, extract the last segment
    if (value.startsWith('/') || value.startsWith('\\') || value.includes('\\')) {
      const parts = value.replace(/\\/g, '/').split('/');
      return parts[parts.length - 1] || value;
    }
    return value;
  }
}
