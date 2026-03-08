import { CommonModule } from '@angular/common';
import { Component, ElementRef, EventEmitter, HostListener, Input, Output, signal, ViewChild } from '@angular/core';

export interface TreeNode {
  name: string;
  children?: TreeNode[];
}

@Component({
  selector: 'app-tree-select',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="tree-select">
      <button
        #trigger
        type="button"
        class="tree-select__trigger"
        (click)="toggleDropdown()"
      >
        <span class="tree-select__label" [class.placeholder]="!value">
          {{ value || placeholder }}
        </span>
        <svg
          class="tree-select__chevron"
          [class.open]="isOpen()"
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      @if (isOpen()) {
        <div class="tree-select__backdrop" (click)="closeDropdown()"></div>
        <div
          #dropdown
          class="tree-select__dropdown"
          [style.top.px]="dropdownTop()"
          [style.left.px]="dropdownLeft()"
          [style.width.px]="dropdownWidth()"
          [style.maxHeight.px]="dropdownMaxHeight()"
        >
          @if (data.children?.length) { 
            @for (child of data.children; track child.name) {
              <ng-container
                *ngTemplateOutlet="treeNode; context: { node: child, level: 0, path: child.name }"
              ></ng-container>
            }
          }
        </div>
      }
    </div>

    <ng-template #treeNode let-node="node" let-level="level" let-path="path">
      <div
        class="tree-select__item"
        [class.selected]="value === path"
        [style.paddingLeft.px]="level * 12 + 4"
        (click)="handleSelect(path)"
      >
        @if (node.children?.length) {
          <button
            type="button"
            class="tree-select__toggle"
            (click)="toggleNode(path, $event)"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              [class.expanded]="isExpanded(path)"
            >
              <polyline *ngIf="!isExpanded(path)" points="6 9 12 15 18 9" />
              <polyline *ngIf="isExpanded(path)" points="6 15 12 9 18 15" />
            </svg>
          </button>
        } @else {
          <span class="tree-select__spacer"></span>
        }
        <span class="tree-select__item-label">{{ node.name }}</span>
      </div>

      @if (node.children?.length && isExpanded(path)) {
        <div class="tree-select__children">
          @for (child of node.children; track child.name) {
            <ng-container
              *ngTemplateOutlet="treeNode; context: { node: child, level: level + 1, path: path + ' > ' + child.name }"
            ></ng-container>
          }
        </div>
      }
    </ng-template>
  `,
  styleUrls: ['./tree-select.component.scss']
})
export class TreeSelectComponent {
  @Input() data!: TreeNode;
  @Input() value: string | null = null;
  @Input() placeholder = 'Sélectionnez une option';
  @Output() valueChange = new EventEmitter<string | null>();

  @ViewChild('trigger', { read: ElementRef }) triggerRef?: ElementRef<HTMLButtonElement>;

  protected isOpen = signal(false);
  protected dropdownTop = signal(0);
  protected dropdownLeft = signal(0);
  protected dropdownWidth = signal(0);
  protected dropdownMaxHeight = signal(400);
  private expandedPaths = new Set<string>();

  constructor(private host: ElementRef) {}

  toggleDropdown(): void {
    this.isOpen.update(value => {
      const next = !value;
      if (next) {
        this.calculateDropdownPosition();
      }
      return next;
    });
  }

  closeDropdown(): void {
    this.isOpen.set(false);
  }

  handleSelect(path: string): void {
    // If clicking the currently selected item, deselect it (go back to "Tous")
    const newValue = this.value === path ? null : path;
    this.valueChange.emit(newValue);
    this.closeDropdown();
  }

  toggleNode(path: string, event: MouseEvent): void {
    event.stopPropagation();
    if (this.expandedPaths.has(path)) {
      this.expandedPaths.delete(path);
    } else {
      this.expandedPaths.add(path);
    }
  }

  private calculateDropdownPosition(): void {
    const triggerEl = this.triggerRef?.nativeElement;
    if (!triggerEl) return;

    const rect = triggerEl.getBoundingClientRect();
    this.dropdownTop.set(rect.bottom + 4);
    this.dropdownLeft.set(rect.left);
    this.dropdownWidth.set(rect.width);

    const viewportHeight = window.innerHeight;
    const availableSpace = viewportHeight - (rect.bottom + 4) - 16;
    this.dropdownMaxHeight.set(Math.max(240, availableSpace));
  }

  protected isExpanded(path: string): boolean {
    return this.expandedPaths.has(path);
  }

  @HostListener('window:resize')
  @HostListener('window:scroll')
  onViewportChange(): void {
    if (this.isOpen()) {
      this.calculateDropdownPosition();
    }
  }

  @HostListener('document:mousedown', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.isOpen()) return;
    if (!this.host.nativeElement.contains(event.target)) {
      this.closeDropdown();
    }
  }
}
