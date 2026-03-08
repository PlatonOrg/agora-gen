import { Injectable, signal, computed, inject } from '@angular/core';
import { ContextService } from '../services/context.service';
import { TemplateResponse } from '../models/template.model';

@Injectable({ providedIn: 'root' })
export class WorkspaceFiltersStore {
  private contextService = inject(ContextService);

  readonly selectedCercle = signal<string>('');
  readonly selectedSujets = signal<string[]>([]);
  readonly selectedNiveaux = signal<string[]>([]);
  readonly selectedComponents = signal<string[]>([]);
  readonly templatesSearchText = signal<string>('');
  readonly sujetInput = signal<string>('');
  readonly niveauInput = signal<string>('');
  readonly componentInput = signal<string>('');
  readonly sujetDropdownOpen = signal<boolean>(false);
  readonly niveauDropdownOpen = signal<boolean>(false);
  readonly componentDropdownOpen = signal<boolean>(false);
  readonly filteredTemplates = signal<TemplateResponse[]>([]);
  readonly isSearchingTemplates = signal<boolean>(false);

  readonly filteredSujets = computed(() => {
    const input = this.sujetInput().toLowerCase();
    const current = this.selectedSujets();
    return this.contextService.getTopicNames()
      .filter(s => !current.includes(s) && s.toLowerCase().includes(input))
      .slice(0, 20);
  });

  readonly filteredNiveaux = computed(() => {
    const input = this.niveauInput().toLowerCase();
    const current = this.selectedNiveaux();
    return this.contextService.getLevelNames()
      .filter(n => !current.includes(n) && n.toLowerCase().includes(input))
      .slice(0, 20);
  });

  addSujet(value: string): void {
    const trimmed = value.trim();
    const current = this.selectedSujets();
    const available = this.contextService.getTopicNames();
    if (trimmed && available.includes(trimmed) && !current.includes(trimmed) && current.length < 5) {
      this.selectedSujets.set([...current, trimmed]);
      this.sujetInput.set('');
      this.sujetDropdownOpen.set(false);
    }
  }

  removeSujet(sujet: string): void {
    this.selectedSujets.update(s => s.filter(x => x !== sujet));
  }

  onSujetInput(value: string): void {
    this.sujetInput.set(value);
    const available = this.contextService.getTopicNames();
    const hasMatches = available.some(s => s.toLowerCase().includes(value.toLowerCase()));
    this.sujetDropdownOpen.set(hasMatches && value.length > 0);
  }

  onSujetInputBlur(): void {
    const current = this.sujetInput().trim();
    const available = this.contextService.getTopicNames();
    if (current && !available.includes(current)) this.sujetInput.set('');
    setTimeout(() => this.sujetDropdownOpen.set(false), 200);
  }

  addNiveau(value: string): void {
    const trimmed = value.trim();
    const current = this.selectedNiveaux();
    const available = this.contextService.getLevelNames();
    if (trimmed && available.includes(trimmed) && !current.includes(trimmed) && current.length < 5) {
      this.selectedNiveaux.set([...current, trimmed]);
      this.niveauInput.set('');
      this.niveauDropdownOpen.set(false);
    }
  }

  removeNiveau(niveau: string): void {
    this.selectedNiveaux.update(n => n.filter(x => x !== niveau));
  }

  onNiveauInput(value: string): void {
    this.niveauInput.set(value);
    const available = this.contextService.getLevelNames();
    const hasMatches = available.some(n => n.toLowerCase().includes(value.toLowerCase()));
    this.niveauDropdownOpen.set(hasMatches && value.length > 0);
  }

  onNiveauInputBlur(): void {
    const current = this.niveauInput().trim();
    const available = this.contextService.getLevelNames();
    if (current && !available.includes(current)) this.niveauInput.set('');
    setTimeout(() => this.niveauDropdownOpen.set(false), 200);
  }

  addComponentFilter(value: string, availableComponents: string[]): void {
    const trimmed = value.trim();
    const current = this.selectedComponents();
    if (trimmed && !current.includes(trimmed) && current.length < 5) {
      this.selectedComponents.set([...current, trimmed]);
      this.componentInput.set('');
      this.componentDropdownOpen.set(false);
    }
  }

  removeComponentFilter(component: string): void {
    this.selectedComponents.update(c => c.filter(x => x !== component));
  }

  onComponentInput(value: string, availableComponents: string[]): void {
    this.componentInput.set(value);
    const hasMatches = availableComponents.some(c => c.toLowerCase().includes(value.toLowerCase()));
    this.componentDropdownOpen.set(hasMatches && value.length > 0);
  }

  onComponentInputBlur(availableComponents: string[]): void {
    const current = this.componentInput().trim();
    if (current && !availableComponents.includes(current)) this.componentInput.set('');
    setTimeout(() => this.componentDropdownOpen.set(false), 200);
  }

  selectCercle(cercle: string | null): void {
    this.selectedCercle.set(cercle || '');
  }

  async searchTemplates(): Promise<void> {
    if (this.isSearchingTemplates()) return;
    this.isSearchingTemplates.set(true);
    this.filteredTemplates.set([]);
    try {
      const templates = await this.contextService.filterTemplates(
        this.selectedCercle(),
        this.selectedSujets(),
        this.selectedNiveaux(),
        this.selectedComponents(),
        this.templatesSearchText(),
      );
      this.filteredTemplates.set(templates);
    } finally {
      this.isSearchingTemplates.set(false);
    }
  }
}

