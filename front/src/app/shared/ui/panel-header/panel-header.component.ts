import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-panel-header',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './panel-header.component.html',
  styleUrl: './panel-header.component.scss',
})
export class PanelHeaderComponent {
  title = input.required<string>();
  collapsed = input<boolean>(false);
  collapseDirection = input<'left' | 'right'>('left');

  collapse = output<void>();
  expand = output<void>();

  protected onToggle(): void {
    if (this.collapsed()) {
      this.expand.emit();
    } else {
      this.collapse.emit();
    }
  }
}

