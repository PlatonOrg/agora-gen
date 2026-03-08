import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HighlightModule } from 'ngx-highlightjs';
import { MonacoEditorModule } from 'ngx-monaco-editor-v2';
import { TemplateParameter } from './template-parameter.model';

export type { TemplateParameter };

@Component({
  selector: 'app-template-parameters',
  standalone: true,
  imports: [CommonModule, FormsModule, HighlightModule, MonacoEditorModule],
  templateUrl: './template-parameters.component.html',
  styleUrls: ['./template-parameters.component.scss'],
})
export class TemplateParametersComponent {
  parameters = input.required<TemplateParameter[]>();
  isEditable = input<boolean>(true);
  isDraggable = input<boolean>(false);

  parameterChange = output<{ name: string; value: any }>();

  private jsonStrings = new Map<string, string>();
  private currentDragImage: HTMLElement | null = null;
  private currentDragTarget: HTMLElement | null = null;

  private readonly supportedLanguages = new Set([
    'python', 'javascript', 'typescript', 'java', 'c', 'cpp', 'csharp',
    'css', 'html', 'xml', 'json', 'sql', 'bash', 'shell', 'plaintext'
  ]);

  protected getHighlightLanguage(language: string | undefined): string {
    if (!language) return 'plaintext';
    const aliases: { [key: string]: string } = { js: 'javascript', ts: 'typescript', py: 'python', 'c++': 'cpp', 'c#': 'csharp', sh: 'bash', zsh: 'bash' };
    const mapped = aliases[language.toLowerCase()] || language.toLowerCase();
    return this.supportedLanguages.has(mapped) ? mapped : 'plaintext';
  }

  protected onParameterChange(nameOrParam: string | TemplateParameter, value: any): void {
    const name = typeof nameOrParam === 'string' ? nameOrParam : nameOrParam.name;
    if (typeof nameOrParam !== 'string' && nameOrParam.type === 'number') value = parseFloat(value) || 0;
    this.parameterChange.emit({ name, value });
  }

  protected jsonStringValue(param: TemplateParameter): string {
    return typeof param.value === 'string' ? param.value : JSON.stringify(param.value, null, 2);
  }

  protected getJsonString(param: TemplateParameter): string {
    if (!this.jsonStrings.has(param.name)) this.jsonStrings.set(param.name, this.jsonStringValue(param));
    return this.jsonStrings.get(param.name)!;
  }

  protected setJsonString(param: TemplateParameter, value: string): void {
    this.jsonStrings.set(param.name, value);
    try { this.parameterChange.emit({ name: param.name, value: JSON.parse(value) }); }
    catch { this.parameterChange.emit({ name: param.name, value }); }
  }

  protected onListItemChange(param: TemplateParameter, index: number, newValue: string): void {
    if (!Array.isArray(param.value)) return;
    const updated = [...param.value]; updated[index] = newValue;
    this.parameterChange.emit({ name: param.name, value: updated });
  }

  protected addListItem(param: TemplateParameter): void {
    if (!Array.isArray(param.value)) return;
    this.parameterChange.emit({ name: param.name, value: [...param.value, ''] });
  }

  protected removeListItem(param: TemplateParameter, index: number): void {
    if (!Array.isArray(param.value)) return;
    this.parameterChange.emit({ name: param.name, value: param.value.filter((_, i) => i !== index) });
  }


  protected onDragStart(event: DragEvent, param: TemplateParameter): void {
    event.stopPropagation();
    event.dataTransfer!.effectAllowed = 'copy';
    event.dataTransfer!.setData('application/json', JSON.stringify({ type: 'parameter', name: param.name, paramType: param.type }));
    const dragImage = document.createElement('div');
    dragImage.style.cssText = 'position:absolute;top:-1000px;left:-1000px;padding:5px 10px;background:#171c8f;color:white;border-radius:4px;font-size:12px;font-weight:600;pointer-events:none;white-space:nowrap;box-shadow:0 2px 8px rgba(23,28,143,0.25);letter-spacing:0.02em;';
    dragImage.textContent = param.name;
    if (this.currentDragImage) document.body.removeChild(this.currentDragImage);
    this.currentDragImage = dragImage;
    document.body.appendChild(dragImage);
    event.dataTransfer!.setDragImage(dragImage, 0, 0);
    (event.currentTarget as HTMLElement).classList.add('dragging');
    this.currentDragTarget = event.currentTarget as HTMLElement;
  }

  protected onDragEnd(_event: DragEvent): void {
    if (this.currentDragImage) { document.body.removeChild(this.currentDragImage); this.currentDragImage = null; }
    if (this.currentDragTarget) { this.currentDragTarget.classList.remove('dragging'); this.currentDragTarget = null; }
  }
}

