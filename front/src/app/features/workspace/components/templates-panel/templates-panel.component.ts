import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TreeSelectComponent, TreeNode } from '../../../../shared/ui/tree-select/tree-select.component';
import { MarkdownModule } from 'ngx-markdown';
import { TemplateResponse } from '../../models/template.model';
import { TemplateParametersComponent } from '../template-parameters/template-parameters.component';

@Component({
  selector: 'app-templates-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, TreeSelectComponent, MarkdownModule, TemplateParametersComponent],
  templateUrl: './templates-panel.component.html',
  styleUrls: ['./templates-panel.component.scss']
})
export class TemplatesPanelComponent implements OnChanges {

  /* ================= SEARCH / FILTERS ================= */

  @Input({ required: true }) templatesSearchText!: string;
  @Output() templatesSearchTextChange = new EventEmitter<string>();
  @Input({ required: true }) isSearchingTemplates!: boolean;
  @Input({ required: true }) filteredTemplates!: TemplateResponse[];

  searchText: string = '';

  @Input({ required: true }) isTemplatesFiltersExpanded!: boolean;

  @Input({ required: true }) selectedComponents!: string[];
  @Input({ required: true }) filteredComponents!: string[];
  @Input({ required: true }) componentInput!: string;
  @Input({ required: true }) componentDropdownOpen!: boolean;

  @Input({ required: true }) selectedSujets!: string[];
  @Input({ required: true }) filteredSujets!: string[];
  @Input({ required: true }) sujetInput!: string;
  @Input({ required: true }) sujetDropdownOpen!: boolean;

  @Input({ required: true }) selectedNiveaux!: string[];
  @Input({ required: true }) filteredNiveaux!: string[];
  @Input({ required: true }) niveauInput!: string;
  @Input({ required: true }) niveauDropdownOpen!: boolean;

  @Input({ required: true }) selectedCercle!: string;
  @Input({ required: true }) CERCLE_TREE!: TreeNode;

  /* ================= OUTPUTS ================= */

  @Output() searchTemplates = new EventEmitter<void>();
  @Output() toggleTemplatesFilters = new EventEmitter<void>();

  @Output() addComponentFilter = new EventEmitter<string>();
  @Output() removeComponentFilter = new EventEmitter<string>();
  @Output() componentInputChange = new EventEmitter<string>();
  @Output() componentInputBlur = new EventEmitter<void>();

  @Output() addSujet = new EventEmitter<string>();
  @Output() removeSujet = new EventEmitter<string>();
  @Output() sujetInputChange = new EventEmitter<string>();
  @Output() sujetInputBlur = new EventEmitter<void>();

  @Output() addNiveau = new EventEmitter<string>();
  @Output() removeNiveau = new EventEmitter<string>();
  @Output() niveauInputChange = new EventEmitter<string>();
  @Output() niveauInputBlur = new EventEmitter<void>();

  @Output() selectCercle = new EventEmitter<string | null>();

  @Output() openComponentDropdown = new EventEmitter<void>();
  @Output() closeComponentDropdown = new EventEmitter<void>();
  @Output() openSujetDropdown = new EventEmitter<void>();
  @Output() closeSujetDropdown = new EventEmitter<void>();
  @Output() openNiveauDropdown = new EventEmitter<void>();
  @Output() closeNiveauDropdown = new EventEmitter<void>();
  @Output() useTemplate = new EventEmitter<TemplateResponse>();


  /* ================= TEMPLATE EXPANSION ================= */

  expandedTemplateIds = new Set<string>();
  activeFiltersCount = 0;

  private updateActiveFiltersCount(): void {
    let count = 0;
    if (Array.isArray(this.selectedComponents)) count += this.selectedComponents.length;
    if (Array.isArray(this.selectedSujets)) count += this.selectedSujets.length;
    if (Array.isArray(this.selectedNiveaux)) count += this.selectedNiveaux.length;
    if (this.selectedCercle) count += 1;
    this.activeFiltersCount = count;
  }

  toggleTemplate(templateId: string): void {
    if (this.expandedTemplateIds.has(templateId)) {
      this.expandedTemplateIds.delete(templateId);
    } else {
      this.expandedTemplateIds.clear();
      this.expandedTemplateIds.add(templateId);
    }
  }

  isTemplateExpanded(templateId: string): boolean {
    return this.expandedTemplateIds.has(templateId);
  }

  /* ================= HELPERS ================= */

  getInputs(template: TemplateResponse): any[] {
    return template?.config_variables?.inputs ?? [];
  }

  viewTemplate(templateId: string): void {
    window.open(`https://platon.univ-eiffel.fr/player/preview/${templateId}?version=latest&editor-preview`, '_blank');
  }

  onParameterChange(_change: {name: string, value: any}): void {
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['templatesSearchText']) {
      this.searchText = changes['templatesSearchText'].currentValue;
    }
    if (changes['selectedComponents'] || changes['selectedSujets'] || changes['selectedNiveaux'] || changes['selectedCercle']) {
      this.updateActiveFiltersCount();
    }
  }
}
