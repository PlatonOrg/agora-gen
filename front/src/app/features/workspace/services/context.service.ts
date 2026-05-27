import { Injectable, signal, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { ApiService } from '../../../core/api/api.service';
import {FilterTemplatesRequest, TemplateResponse} from '../models/template.model';
import { ComponentsMetadataService } from './components-metadata.service';

/**
 * Interfaces for context data
 */
export interface Circle {
  id: string;
  name: string;
  fullPath: string;
  parentId: string | null;
  hasChildren: boolean;
  writePermission: boolean;
}

export interface CircleTreeNode {
  name: string;
  children?: CircleTreeNode[];
}

export interface Topic {
  id: string;
  name: string;
  description: string;
}

export interface Level {
  id: string;
  name: string;
  description: string;
}

export interface Component {
  id: string;
  name: string;
  label: string;
  type: 'Formulaire' | 'Widget';
  url: string;
}

export interface ComponentMetadata {
  name: string;
  tag: string;
  category: string;
  description: string;
  usage: string;
  properties: any;
  url: string;
}

export interface ContextData {
  circles: Circle[];
  circlesTree: CircleTreeNode;
  topics: Topic[];
  levels: Level[];
  components: Component[];
  formulaireComponents: Component[];
  widgetComponents: Component[];
}

/**
 * Context Service for managing pedagogical context data
 * (circles, topics, levels, components)
 */
@Injectable({
  providedIn: 'root'
})
export class ContextService {
  private isBrowser: boolean;

  // Signals for reactive data
  private circlesSignal = signal<Circle[]>([]);
  private circlesTreeSignal = signal<CircleTreeNode | null>(null);
  private topicsSignal = signal<Topic[]>([]);
  private levelsSignal = signal<Level[]>([]);
  private componentsSignal = signal<Component[]>([]);
  private formulaireComponentsSignal = signal<Component[]>([]);
  private widgetComponentsSignal = signal<Component[]>([]);
  private componentMetadataSignal = signal<ComponentMetadata[]>([]);

  private isLoadedSignal = signal<boolean>(false);
  private isLoadingSignal = signal<boolean>(false);
  private errorSignal = signal<string | null>(null);

  constructor(
    private apiService: ApiService,
    private componentsMetadataService: ComponentsMetadataService,
    @Inject(PLATFORM_ID) platformId: Object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  // Getters for signals
  get circles() { return this.circlesSignal; }
  get circlesTree() { return this.circlesTreeSignal; }
  get topics() { return this.topicsSignal; }
  get levels() { return this.levelsSignal; }
  get components() { return this.componentsSignal; }
  get formulaireComponents() { return this.formulaireComponentsSignal; }
  get widgetComponents() { return this.widgetComponentsSignal; }
  get componentMetadata() { return this.componentMetadataSignal; }
  get isLoaded() { return this.isLoadedSignal; }
  get isLoading() { return this.isLoadingSignal; }
  get error() { return this.errorSignal; }

  /**
   * Load all context data from the backend
   */
  async loadAllContext(): Promise<void> {
    if (!this.isBrowser) {
      console.log('[ContextService] Skipping load on server');
      return;
    }

    if (this.isLoadingSignal()) {
      console.log('[ContextService] Already loading, skipping...');
      return;
    }

    console.log('[ContextService] Loading all context data...');
    this.isLoadingSignal.set(true);
    this.errorSignal.set(null);

    try {
      const data = await this.apiService.get<ContextData>('/context/all');

      console.log('[ContextService] ===== CONTEXT DATA LOADED =====');
      console.log('[ContextService] Circles:', data.circles.length);
      console.log('[ContextService] Topics:', data.topics.length);
      console.log('[ContextService] Levels:', data.levels.length);
      console.log('[ContextService] Components:', data.components.length);
      console.log('[ContextService] ================================');

      this.circlesSignal.set(data.circles);
      this.circlesTreeSignal.set(data.circlesTree);
      this.topicsSignal.set(data.topics);
      this.levelsSignal.set(data.levels);
      this.componentsSignal.set(data.components);
      this.formulaireComponentsSignal.set(data.formulaireComponents);
      this.widgetComponentsSignal.set(data.widgetComponents);

      // Load component metadata from docs
      await this.loadComponentMetadata();

      this.isLoadedSignal.set(true);
      console.log('[ContextService] Context data loaded successfully!');
    } catch (error: any) {
      console.error('[ContextService] Error loading context:', error);
      this.errorSignal.set(error.message || 'Failed to load context data');
    } finally {
      this.isLoadingSignal.set(false);
    }
  }

  /**
   * Load only circles tree
   */
  async loadCirclesTree(): Promise<CircleTreeNode | null> {
    try {
      const tree = await this.apiService.get<CircleTreeNode>('/context/circles/tree');
      this.circlesTreeSignal.set(tree);
      console.log('[ContextService] Circles tree loaded:', tree.name);
      return tree;
    } catch (error: any) {
      console.error('[ContextService] Error loading circles tree:', error);
      return null;
    }
  }

  /**
   * Load only topics
   */
  async loadTopics(): Promise<Topic[]> {
    try {
      const topics = await this.apiService.get<Topic[]>('/context/topics');
      this.topicsSignal.set(topics);
      console.log('[ContextService] Topics loaded:', topics.length);
      return topics;
    } catch (error: any) {
      console.error('[ContextService] Error loading topics:', error);
      return [];
    }
  }

  /**
   * Load only levels
   */
  async loadLevels(): Promise<Level[]> {
    try {
      const levels = await this.apiService.get<Level[]>('/context/levels');
      this.levelsSignal.set(levels);
      console.log('[ContextService] Levels loaded:', levels.length);
      return levels;
    } catch (error: any) {
      console.error('[ContextService] Error loading levels:', error);
      return [];
    }
  }

  /**
   * Load only components
   */
  async loadComponents(): Promise<Component[]> {
    try {
      const components = await this.apiService.get<Component[]>('/context/components');
      this.componentsSignal.set(components);
      this.formulaireComponentsSignal.set(components.filter(c => c.type === 'Formulaire'));
      this.widgetComponentsSignal.set(components.filter(c => c.type === 'Widget'));
      console.log('[ContextService] Components loaded:', components.length);
      return components;
    } catch (error: any) {
      console.error('[ContextService] Error loading components:', error);
      return [];
    }
  }

  /**
   * Get topic names as array of strings (for compatibility with existing form)
   */
  getTopicNames(): string[] {
    return this.topicsSignal().map(t => t.name);
  }

  /**
   * Get level names as array of strings (for compatibility with existing form)
   */
  getLevelNames(): string[] {
    return this.levelsSignal().map(l => l.name);
  }

  /**
   * Get formulaire component names
   */
  getFormulaireComponentNames(): string[] {
    return this.formulaireComponentsSignal().map(c => c.name);
  }

  /**
   * Get widget component names
   */
  getWidgetComponentNames(): string[] {
    return this.widgetComponentsSignal().map(c => c.name);
  }

  /**
   * Get the documentation URL for a component by its name
   */
  getComponentDocUrl(componentName: string): string | null {
    const component = this.componentsSignal().find(c => c.name === componentName);
    return component?.url || null;
  }

  /**
   * Load component metadata from resources/docs/components/metadata.json
   */
  private async loadComponentMetadata(): Promise<void> {
    try {
      const response = await fetch('/resources/docs/components/metadata.json');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const metadata: ComponentMetadata[] = await response.json();
      this.componentMetadataSignal.set(metadata);
      console.log('[ContextService] Component metadata loaded:', metadata.length, 'components');
    } catch (error) {
      console.error('[ContextService] Error loading component metadata:', error);
      // Set empty array as fallback
      this.componentMetadataSignal.set([]);
    }
  }
/*
  mapComponentTagsToNames(tags: string[]): string[] {
    if (!tags || !tags.length) {
      return [];
    }

    const components = this.componentsSignal();

    return tags
      .map(tag => {
        const comp = components.find(c => c.tag === tag);
        return comp ? comp.name : null;
      })
      .filter((name): name is string => name !== null);
  }*/

  /**
   * Get component tag by name (for backend API calls)
   */
  getComponentTag(componentName: string): string | null {
    // First try ComponentsMetadataService (loaded from API endpoint)
    const comp = this.componentsMetadataService.getComponentByName(componentName);
    if (comp?.tag) {
      return comp.tag;
    }
    // Fallback to local metadata signal
    const metadata = this.componentMetadataSignal().find(m => m.name === componentName);
    return metadata?.tag || null;
  }

  /**
   * Convert component names to tags for backend API
   */
  getComponentTags(componentNames: string[]): string[] {
    return componentNames
      .map(name => this.getComponentTag(name))
      .filter(tag => tag !== null) as string[];
  }

  getWritableCircles(): Circle[] {
    return this.circlesSignal().filter(c => c.writePermission);
  }

  /**
   * Get circle ID by name
   */
  getCircleId(circleName: string): string | null {
    // If circleName is a path like "Informatique > Algorithmique", take the last part
    const leafName = circleName.split(' > ').pop() || circleName;
    const circle = this.circlesSignal().find(c => c.name === leafName);
    return circle?.id || null;
  }

  /**
   * Get topic ID by name
   */
  getTopicId(topicName: string): string | null {
    const topic = this.topicsSignal().find(t => t.name === topicName);
    return topic?.id || null;
  }

  /**
   * Get level ID by name
   */
  getLevelId(levelName: string): string | null {
    const level = this.levelsSignal().find(l => l.name === levelName);
    return level?.id || null;
  }

  /**
   * Convert names to IDs for filtering
   */
  getFilterIds(circleName: string, topicNames: string[], levelNames: string[]): {
    cercleId: string | null;
    topicIds: string[];
    levelIds: string[];
  } {
    return {
      cercleId: circleName ? this.getCircleId(circleName) : null,
      topicIds: topicNames.map(name => this.getTopicId(name)).filter(id => id !== null) as string[],
      levelIds: levelNames.map(name => this.getLevelId(name)).filter(id => id !== null) as string[]
    };
  }

  /**
   * Filter templates based on criteria
   */
  async filterTemplates(cercle: string, sujets: string[], niveaux: string[], composants: string[] = [], search: string = ''): Promise<TemplateResponse[]> {
    try {
      // Convert names to IDs for backend API
      const { cercleId, topicIds, levelIds } = this.getFilterIds(cercle, sujets, niveaux);

      // Convert component names to tags for backend API
      const componentTags = this.getComponentTags(composants);

      const requestBody: FilterTemplatesRequest = {
        cercle: cercleId || '',
        sujets: topicIds,
        niveaux: levelIds,
        composants: componentTags,
        search: search || undefined
      };

      console.log('[ContextService] Filtering templates with:', {
        cercle: cercleId,
        sujets: topicIds,
        niveaux: levelIds,
        composants: componentTags,
        search: search || undefined
      });

      const templates = await this.apiService.post<TemplateResponse[]>('/context/selected_templates', requestBody);
      console.log('[ContextService] Templates filtered:', templates.length);
      return templates;
    } catch (error: any) {
      console.error('[ContextService] Error filtering templates:', error);
      return [];
    }
  }

  /**
   * Get list of universal template filenames
   */
  async getUnivTemplateList(): Promise<string[]> {
    try {
      const filenames = await this.apiService.get<string[]>('/context/univ_template_jsons');
      console.log('[ContextService] Universal template list loaded:', filenames.length);
      return filenames;
    } catch (error: any) {
      console.error('[ContextService] Error loading universal template list:', error);
      return [];
    }
  }

  /**
   * Get content of a universal template file
   */
  async getUnivTemplateContent(filename: string): Promise<string> {
    try {
      const content = await this.apiService.get<string>(`/context/univ_template_jsons/${encodeURIComponent(filename)}`);
      console.log('[ContextService] Universal template content loaded:', filename);
      return content;
    } catch (error: any) {
      console.error('[ContextService] Error loading universal template content for', filename, ':', error);
      return '';
    }
  }

  /**
   * Clear all loaded data
   */
  clear(): void {
    this.circlesSignal.set([]);
    this.circlesTreeSignal.set(null);
    this.topicsSignal.set([]);
    this.levelsSignal.set([]);
    this.componentsSignal.set([]);
    this.formulaireComponentsSignal.set([]);
    this.widgetComponentsSignal.set([]);
    this.isLoadedSignal.set(false);
    this.errorSignal.set(null);
  }
}



