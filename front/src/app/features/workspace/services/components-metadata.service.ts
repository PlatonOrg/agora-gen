import { Injectable, signal, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

export interface ComponentPropertySchema {
  type: string;
  description?: string;
  default?: any;
  enum?: any[];
  items?: ComponentPropertySchema | { type: string };
  properties?: Record<string, ComponentPropertySchema>;
  required?: boolean;
}

export interface ComponentPropertyEntry {
  key: string;
  type: string;
  description: string;
  defaultValue: any;
  required: boolean;
  enumValues: any[] | null;
  isArrayOfStrings: boolean;
}

export interface ComponentMetadata {
  name: string;
  tag: string;
  category: 'Formulaire' | 'Widget';
  description: string;
  documentation?: string;
  properties: Record<string, ComponentPropertySchema>;
  doc_path?: string;
  url?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ComponentsMetadataService {
  private static readonly METADATA_URL = '/api/v1/components/metadata';

  private isBrowser: boolean;
  private componentsSignal = signal<ComponentMetadata[]>([]);
  private isLoadingSignal = signal<boolean>(false);
  private isLoadedSignal = signal<boolean>(false);

  constructor(@Inject(PLATFORM_ID) platformId: Object) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  get components() {
    return this.componentsSignal;
  }

  get isLoading() {
    return this.isLoadingSignal;
  }

  get isLoaded() {
    return this.isLoadedSignal;
  }

  async loadComponents(): Promise<ComponentMetadata[]> {
    if (!this.isBrowser) {
      return [];
    }

    if (this.isLoadedSignal()) {
      return this.componentsSignal();
    }

    if (this.isLoadingSignal()) {
      return new Promise((resolve) => {
        const checkLoaded = () => {
          if (this.isLoadedSignal()) {
            resolve(this.componentsSignal());
          } else {
            setTimeout(checkLoaded, 100);
          }
        };
        checkLoaded();
      });
    }

    this.isLoadingSignal.set(true);

    try {
      const response = await fetch(ComponentsMetadataService.METADATA_URL);
      if (!response.ok) {
        throw new Error(`Failed to load components metadata: ${response.status}`);
      }

      const data: ComponentMetadata[] = await response.json();

      if (!Array.isArray(data) || data.length === 0) {
        throw new Error('Components metadata is empty or invalid.');
      }

      this.componentsSignal.set(data);
      this.isLoadedSignal.set(true);
      return data;
    } catch (error: any) {
      console.error('[ComponentsMetadataService] Failed to load metadata:', error?.message);
      return [];
    } finally {
      this.isLoadingSignal.set(false);
    }
  }

  /**
   * Get component by name
   */
  getComponentByName(name: string): ComponentMetadata | null {
    return this.componentsSignal().find(c => c.name === name) || null;
  }

  /**
   * Get formulaire components
   */
  getFormulaireComponents(): ComponentMetadata[] {
    return this.componentsSignal().filter(c => c.category === 'Formulaire');
  }

  /**
   * Get widget components
   */
  getWidgetComponents(): ComponentMetadata[] {
    return this.componentsSignal().filter(c => c.category === 'Widget');
  }

  /**
   * Get formulaire component names
   */
  getFormulaireComponentNames(): string[] {
    return this.getFormulaireComponents().map(c => c.name);
  }

  /**
   * Get widget component names
   */
  getWidgetComponentNames(): string[] {
    return this.getWidgetComponents().map(c => c.name);
  }

  /**
   * Get video path for a component
   */
  getVideoPath(componentName: string): string {
    return `/api/v1/components/video/${componentName}`;
  }
}
