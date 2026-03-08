import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ComponentsPanelComponent } from '../components-panel/components-panel.component';
import { ComponentMetadata } from '../../services/components-metadata.service';
import { PanelHeaderComponent } from '../../../../shared/ui/panel-header/panel-header.component';
import { WorkspaceStore } from '../../state/workspace.store';

@Component({
  selector: 'app-side-panel',
  standalone: true,
  imports: [CommonModule, ComponentsPanelComponent, PanelHeaderComponent],
  templateUrl: './side-panel.component.html',
  styleUrls: ['./side-panel.component.scss']
})
export class SidePanelComponent {
  readonly wsStore = inject(WorkspaceStore);
  @Input() isComponentsPanelExpanded!: () => boolean;
  @Input() isComponentsPanelCollapsed!: () => boolean;
  @Input() formulaireComponents!: () => ComponentMetadata[];
  @Input() widgetComponents!: () => ComponentMetadata[];
  @Output() addComponent = new EventEmitter<string>();
  @Output() toggleTooltip = new EventEmitter<{ name: string; event: MouseEvent }>();
  @Output() componentsTabClick = new EventEmitter<void>();
  @Output() addComponentToDiscussion = new EventEmitter<string>();
  @Output() collapseComponents = new EventEmitter<void>();
  @Output() expandComponents = new EventEmitter<void>();
}
