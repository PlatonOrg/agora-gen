import { Injectable, inject } from '@angular/core';
import { TemplateResponse } from '../models/template.model';
import { ExerciseData } from '../models/exercise.model';
import { ComponentsMetadataService } from '../services/components-metadata.service';

const TEMPLATE_STANDARD_KEYS = new Set([
  'sandbox', 'title', 'statement', 'form', 'solution',
  'builder', 'grader', 'hint', 'theories', 'author',
]);

@Injectable({ providedIn: 'root' })
export class WorkspaceTemplateService {
  private readonly componentsMetadata = inject(ComponentsMetadataService);

  getComponentNameByTag(tag: string): string {
    const all = this.componentsMetadata.components();
    return all.find(c => c.tag === tag)?.name ?? tag;
  }

  buildExerciseFromTemplate(template: TemplateResponse, current: ExerciseData): ExerciseData {
    const compiled = template.compil_variables ?? {};

    const sandboxVars: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(compiled)) {
      if (!TEMPLATE_STANDARD_KEYS.has(key)) sandboxVars[key] = value;
    }

    return {
      ...current,
      name: template.name ?? '',
      description: template.description ?? '',
      titre: compiled['title'] ?? '',
      enonce: compiled['statement'] ?? '',
      forme: compiled['form'] ?? '',
      solution: compiled['solution'] ?? '',
      indications: compiled['hint'] ?? [],
      theories: compiled['theories'] ?? [],
      sandbox: compiled['sandbox'] ?? 'python',
      construction: compiled['builder'] ?? '',
      evaluation: compiled['grader'] ?? '',
      components: (template.components ?? []).map(tag => this.getComponentNameByTag(tag)),
      component_instances: template.component_instances ?? [],
      template_id: template.id,
      sandbox_variables: sandboxVars,
      config_variables: JSON.parse(JSON.stringify(template.config_variables ?? {})),
      metadata: {
        levels: template.levels ?? [],
        topics: template.topics ?? [],
      },
    };
  }
}

