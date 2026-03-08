import { GenerationStepState, GenerationDetailStatus, GenerationTimelineData, GenerationTimelineDetail } from './discussion.models';

const STEP_ORDER = ['analysis', 'generation', 'sandbox'] as const;
type Step = typeof STEP_ORDER[number];

const STEP_LABELS: Record<Step, string> = {
  analysis: 'Analyse et recherche',
  generation: 'Génération du contenu',
  sandbox: 'Vérification et prévisualisation',
};

export class GenerationTimeline {
  private stepStates: Record<string, GenerationStepState> = { analysis: 'pending', generation: 'pending', sandbox: 'pending' };
  private details: GenerationTimelineDetail[] = [];
  private typingQueue: GenerationTimelineDetail[] = [];
  private typingText = '';
  private typingStatus: GenerationDetailStatus = 'info';
  private currentTypingItem: GenerationTimelineDetail | null = null;
  private isTyping = false;
  private flushed = false;
  private hasTopMatchesDetail = false;
  private hasGenerationModeDetail = false;
  private readonly typingDelayMs: number;

  constructor(typingDelayMs = 12) {
    this.typingDelayMs = typingDelayMs;
  }

  reset(): void {
    this.stepStates = { analysis: 'pending', generation: 'pending', sandbox: 'pending' };
    this.details = [];
    this.typingQueue = [];
    this.typingText = '';
    this.typingStatus = 'info';
    this.currentTypingItem = null;
    this.isTyping = false;
    this.flushed = false;
    this.hasTopMatchesDetail = false;
    this.hasGenerationModeDetail = false;
  }

  start(): void {
    this.reset();
    this.stepStates['analysis'] = 'in_progress';
  }

  markStep(step: Step, state: GenerationStepState): void {
    this.stepStates = { ...this.stepStates, [step]: state };
  }

  markAllStopped(): void {
    for (const step of STEP_ORDER) {
      if (this.stepStates[step] === 'in_progress') {
        this.stepStates = { ...this.stepStates, [step]: 'stopped' };
      }
    }
  }

  build(): GenerationTimelineData {
    return {
      steps: STEP_ORDER.map(s => ({ key: s, label: STEP_LABELS[s], state: this.stepStates[s] })),
      details: this.details.slice(-20),
      typingText: this.typingText,
      typingStatus: this.typingStatus,
      isTyping: this.isTyping && this.typingText.length > 0,
    };
  }

  enqueueDetail(text: string, status: GenerationDetailStatus, url?: string, onRefresh?: () => void): void {
    const sanitized = this.sanitize(text);
    if (!sanitized) return;
    this.typingQueue.push({ id: crypto.randomUUID(), text: sanitized, status, url });
    void this.flush(onRefresh);
  }

  enqueueGroupDetail(text: string, status: GenerationDetailStatus, children: { text: string; url?: string }[], onRefresh?: () => void): void {
    const sanitized = this.sanitize(text);
    if (!sanitized) return;
    const sanitizedChildren = children.map(c => ({ text: this.sanitize(c.text), url: c.url })).filter(c => c.text.length > 0);
    this.typingQueue.push({ id: crypto.randomUUID(), text: sanitized, status, children: sanitizedChildren });
    void this.flush(onRefresh);
  }

  forceFlush(): void {
    this.flushed = true;
    if (this.currentTypingItem) {
      this.details.push(this.currentTypingItem);
      this.currentTypingItem = null;
    }
    const remaining = [...this.typingQueue];
    this.typingQueue = [];
    for (const item of remaining) {
      this.details.push(item);
    }
    this.typingText = '';
    this.isTyping = false;
  }

  private async flush(onRefresh?: () => void): Promise<void> {
    if (this.isTyping) return;
    this.isTyping = true;
    while (this.typingQueue.length > 0) {
      if (this.flushed) break;
      const next = this.typingQueue.shift();
      if (!next) continue;
      this.currentTypingItem = next;
      this.typingText = '';
      this.typingStatus = next.status;
      for (const char of next.text) {
        if (this.flushed) break;
        this.typingText += char;
        onRefresh?.();
        await this.delay(this.typingDelayMs);
      }
      if (!this.flushed) {
        this.details.push(next);
        this.currentTypingItem = null;
        this.typingText = '';
        onRefresh?.();
      }
    }
    if (!this.flushed) {
      this.isTyping = false;
      onRefresh?.();
    }
  }

  handleDetailedEvent(eventType: string, data: any, sanitize: (t: string) => string, enqueue: (text: string, status: GenerationDetailStatus, url?: string) => void, enqueueGroup?: (text: string, status: GenerationDetailStatus, children: { text: string; url?: string }[]) => void): void {
    const isStarted = eventType.endsWith('_started');
    const isCompleted = eventType.endsWith('_completed');
    const rawStep = eventType.replace(/_(started|completed)$/, '');
    const group = this.mapToGroup(rawStep);

    if (group) {
      if (isStarted) {
        if (group === 'generation' && this.stepStates['analysis'] !== 'completed') {
          this.markStep('analysis', 'completed');
        }
        this.markStep(group, 'in_progress');
      } else if (isCompleted) {
        this.markStep(group, 'completed');
      }
    }

    if (rawStep === 'retrieval' && isCompleted && !this.hasTopMatchesDetail && Array.isArray(data?.top_resources) && data.top_resources.length > 0) {
      const top3 = data.top_resources
        .slice(0, 3)
        .map((v: any) => ({ text: sanitize(String(v?.name || v?.resource_id || '')), url: sanitize(String(v?.url || '')) || undefined }))
        .filter((v: any) => v.text.length > 0);
      if (top3.length > 0) {
        if (enqueueGroup) {
          enqueueGroup('Exercices similaires trouvés :', 'info', top3);
        } else {
          enqueue('Exercices similaires trouvés :', 'info');
          for (const item of top3) enqueue('  — ' + item.text, 'info', item.url);
        }
        this.hasTopMatchesDetail = true;
      }
    }

    if (rawStep === 'component_selection' && isCompleted) {
      const tags: string[] = Array.isArray(data?.selected_tags) ? data.selected_tags : [];
      if (tags.length > 0) {
        enqueue(`Composants sélectionnés : ${tags.join(', ')}`, 'info');
      }
    }
  }

  handleGenerationMode(label: string, enqueue: (text: string, status: GenerationDetailStatus) => void): void {
    if (label && !this.hasGenerationModeDetail) {
      enqueue(`Approche : ${this.formatModeLabel(label)}`, 'info');
      this.hasGenerationModeDetail = true;
    }
  }

  private formatModeLabel(raw: string): string {
    const normalized = raw.toLowerCase().trim();
    if (normalized === 'exercise sans template' || normalized === 'pure') {
      return 'génération libre à partir de zéro';
    }
    if (normalized === 'exercise avec template' || normalized === 'template') {
      return 'génération guidée par un modèle existant';
    }
    return raw;
  }

  private mapToGroup(step: string): Step | null {
    if (['retrieval', 'template_loading', 'examples', 'component_selection'].includes(step)) return 'analysis';
    if (['llm_generation', 'exercise_mapping', 'template_generation'].includes(step)) return 'generation';
    if (step === 'preview') return 'sandbox';
    return null;
  }

  sanitize(input: string): string {
    return (input || '')
      .replace(/[\u4E00-\u9FFF]/g, '')
      .replace(/\uFFFD/g, '')
      .replace(/G\u8305n\u8305ration/gi, 'Génération')
      .replace(/l\u9225\u6a88xercice/gi, "l'exercice")
      .replace(/aper\u83bdu/gi, 'aperçu')
      .replace(/D\u8305posez ici/gi, 'Déposez ici')
      .trim();
  }

  private delay(ms: number): Promise<void> {
    return new Promise(r => setTimeout(r, ms));
  }
}



