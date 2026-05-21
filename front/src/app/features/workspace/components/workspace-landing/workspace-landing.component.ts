import { Component, computed, inject, input, OnInit, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { AgoraLogoComponent } from '../../../../shared/ui/agora-logo/agora-logo.component';
import { ContextService, Circle } from '../../services/context.service';
import { ComponentsMetadataService, ComponentMetadata } from '../../services/components-metadata.service';
import { ChatService } from '../../services/chat.service';
import { DifficultyLevel, ExerciseGenerationContext } from '../../models/exercise.model';

@Component({
  selector: 'app-workspace-landing',
  standalone: true,
  imports: [CommonModule, FormsModule, AgoraLogoComponent],
  templateUrl: './workspace-landing.component.html',
  styleUrl: './workspace-landing.component.scss',
})
export class WorkspaceLandingComponent implements OnInit {
  private readonly context = inject(ContextService);
  private readonly componentsMeta = inject(ComponentsMetadataService);
  private readonly chatService = inject(ChatService);
  private readonly sanitizer = inject(DomSanitizer);

  readonly initialContext = input<ExerciseGenerationContext | null>(null);
  readonly contextSubmitted = output<ExerciseGenerationContext>();
  readonly cancelled = output<void>();

  // ── Context data ──────────────────────────────────────────────────────────
  readonly availableNiveaux = computed(() => this.context.getLevelNames());
  readonly availableSujets  = computed(() => this.context.getTopicNames());
  readonly isContextLoading = computed(() => this.context.isLoading() && !this.context.isLoaded());
  readonly formulaireComponents = computed<ComponentMetadata[]>(() =>
    this.componentsMeta.getFormulaireComponents()
  );

  // ── Cercle search ─────────────────────────────────────────────────────────
  readonly cercleInput       = signal('');
  readonly selectedCercle    = signal('');
  readonly cercleDropdownOpen = signal(false);
  readonly filteredCircles = computed<Circle[]>(() => {
    const input = this.cercleInput().toLowerCase();
    const all   = this.context.circles();
    if (!input) return all.slice(0, 10);
    return all
      .filter((c: Circle) => c.name.toLowerCase().includes(input) || c.fullPath.toLowerCase().includes(input))
      .slice(0, 10);
  });

  // ── Form selections ───────────────────────────────────────────────────────
  readonly selectedNiveaux  = signal<string[]>([]);
  readonly selectedDomaines = signal<string[]>([]);
  readonly concept          = signal('');
  readonly selectedComponent = signal<string[]>([]);
  readonly difficulte       = signal<DifficultyLevel>('moyen');

  // ── Optional section ──────────────────────────────────────────────────────
  readonly showObjectifs          = signal(false);
  toggleObjectifs(): void { this.showObjectifs.update((v: boolean) => !v); }
  readonly showPedagogy = signal(true)
  protected togglePedagogy() : void { this.showPedagogy.update((v : boolean) => !v)}
  readonly objectifsPedagogiques  = signal('');
  readonly publicVise             = signal('');
  readonly prerequis              = signal('');

  // ── Preview modal ─────────────────────────────────────────────────────────
  readonly showPreviewModal  = signal(false);
  readonly previewUrl        = signal<string | null>(null);
  readonly safePreviewUrl    = computed<SafeResourceUrl | null>(() => {
    const url = this.previewUrl();
    return url ? this.sanitizer.bypassSecurityTrustResourceUrl(url) : null;
  });
  readonly previewLoading    = signal(false);
  readonly previewError      = signal<string | null>(null);
  readonly previewingFor     = signal<string | null>(null);

  // ── Validation ────────────────────────────────────────────────────────────
  readonly isFormValid = computed(() => this.concept().trim().length >= 3);

  readonly difficulties: { id: DifficultyLevel; label: string; color: string }[] = [
    { id: 'facile',    label: 'Facile',    color: 'easy'   },
    { id: 'moyen',     label: 'Moyen',     color: 'medium' },
    { id: 'difficile', label: 'Difficile', color: 'hard'   },
  ];

  ngOnInit(): void {
    if (!this.context.isLoaded() && !this.context.isLoading()) {
      this.context.loadAllContext();
    }
    if (this.componentsMeta.getFormulaireComponents().length === 0) {
      this.componentsMeta.loadComponents();
    }
    const ctx = this.initialContext();
    if (ctx) this.prefillFromContext(ctx);
  }

  private prefillFromContext(ctx: ExerciseGenerationContext): void {
    if (ctx.cercle) { this.selectedCercle.set(ctx.cercle); this.cercleInput.set(ctx.cercle); }
    this.selectedNiveaux.set([...ctx.niveaux]);
    this.selectedDomaines.set([...ctx.domaines]);
    this.concept.set(ctx.concept);
    if (ctx.selected_component?.length) this.selectedComponent.set([...ctx.selected_component]);
    this.difficulte.set(ctx.difficulte);
    if (ctx.objectifs_pedagogiques) { this.objectifsPedagogiques.set(ctx.objectifs_pedagogiques); this.showObjectifs.set(true); }
    if (ctx.public_vise) { this.publicVise.set(ctx.public_vise); this.showObjectifs.set(true); }
    if (ctx.prerequis) { this.prerequis.set(ctx.prerequis); this.showObjectifs.set(true); }
  }

  // ── Niveaux / Domaines ────────────────────────────────────────────────────
  toggleNiveau(n: string): void {
    this.selectedNiveaux.update((ns: string[]) => ns.includes(n) ? ns.filter((x: string) => x !== n) : [...ns, n]);
  }
  toggleDomaine(d: string): void {
    this.selectedDomaines.update((ds: string[]) => ds.includes(d) ? ds.filter((x: string) => x !== d) : [...ds, d]);
  }
  isNiveauSelected(n: string)  { return this.selectedNiveaux().includes(n);  }
  isDomaineSelected(d: string) { return this.selectedDomaines().includes(d); }

  // ── Cercle ────────────────────────────────────────────────────────────────
  onCercleInput(event: Event): void {
    this.cercleInput.set((event.target as HTMLInputElement).value);
    this.selectedCercle.set('');
    this.cercleDropdownOpen.set(true);
  }
  onCercleBlur(): void {
    setTimeout(() => {
      this.cercleDropdownOpen.set(false);
      if (!this.selectedCercle()) this.cercleInput.set('');
    }, 200);
  }
  selectCircle(circle: Circle): void {
    this.selectedCercle.set(circle.fullPath || circle.name);
    this.cercleInput.set(circle.fullPath || circle.name);
    this.cercleDropdownOpen.set(false);
  }
  clearCercle(): void {
    this.selectedCercle.set('');
    this.cercleInput.set('');
  }

  // ── Component selection ───────────────────────────────────────────────────
  toggleComponent(name: string): void {
    this.selectedComponent.update((current : string[]) => {
      const values = current ?? [];

      return values.includes(name)
        ? values.filter(v => v !== name)
        : [...values, name];
    });
  }

  isComponentSelected(name: string) { return this.selectedComponent().includes(name) }

  // ── Preview ───────────────────────────────────────────────────────────────
  async openPreview(meta: ComponentMetadata, event: Event): Promise<void> {
    event.stopPropagation();
    this.previewLoading.set(true);
    this.previewError.set(null);
    this.previewUrl.set(null);
    this.showPreviewModal.set(true);
    this.previewingFor.set(meta.name);

    try {
      // Find first template that uses this component
      const templates = await this.context.filterTemplates('', [], [], [meta.tag], '');
      if (templates.length > 0) {
        const tpl = templates[0];
        const result = await this.chatService.previewTemplate(tpl.id, tpl.compil_variables ?? {});
        this.previewUrl.set(result.preview_url);
      } else if (meta.url) {
        this.previewUrl.set(meta.url);
      } else {
        this.previewError.set('Aucun aperçu disponible pour ce composant.');
      }
    } catch {
      this.previewError.set('Impossible de charger l\'aperçu.');
    } finally {
      this.previewLoading.set(false);
    }
  }

  closePreview(): void {
    this.showPreviewModal.set(false);
    this.previewUrl.set(null);
    this.previewError.set(null);
    this.previewingFor.set(null);
  }

  // ── Submit ────────────────────────────────────────────────────────────────
  submit(mode: 'ask' | 'agent'): void {
    if (mode === 'agent' && !this.isFormValid()) return;
    this.contextSubmitted.emit({
      cercle:                 this.selectedCercle()          || undefined,
      niveaux:                this.selectedNiveaux(),
      domaines:               this.selectedDomaines(),
      concept:                this.concept(),
      selected_component:      this.selectedComponent().length ? this.selectedComponent() : undefined,
      difficulte:              this.difficulte(),
      objectifs_pedagogiques:  this.objectifsPedagogiques()   || undefined,
      public_vise:             this.publicVise()               || undefined,
      prerequis:              this.prerequis()                || undefined,
      mode,
    });
  }
}
