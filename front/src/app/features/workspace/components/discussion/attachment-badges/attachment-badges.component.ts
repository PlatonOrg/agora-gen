import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-attachment-badges',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './attachment-badges.component.html',
  styleUrl: './attachment-badges.component.scss',
})
export class AttachmentBadgesComponent {
  components = input<string[]>([]);
  fields = input<string[]>([]);
  parameters = input<string[]>([]);
  fileNames = input<string[]>([]);
  processingFileNames = input<string[]>([]);
  compact = input<boolean>(false);

  removable = input<boolean>(false);

  removeComponent = input<((tag: string) => void) | null>(null);
  removeField = input<((name: string) => void) | null>(null);
  removeParameter = input<((name: string) => void) | null>(null);
  removeFile = input<((name: string) => void) | null>(null);

  protected truncate(name: string, max = 26): string {
    if (name.length <= max) return name;
    const ext = name.includes('.') ? '.' + name.split('.').pop() : '';
    return name.slice(0, max - ext.length - 1) + '…' + ext;
  }
}

