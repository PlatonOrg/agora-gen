import { Component, input, output, inject, computed, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ContextService, Circle } from '../../services/context.service';
import { ExerciseStatus, PublishExerciseRequest } from '../../models/publish.model';

@Component({
  selector: 'app-publish-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="dialog-overlay" (click)="onCancel()">
      <div class="dialog" (click)="$event.stopPropagation()">
        <div class="dialog-header">
          <div class="dialog-header__icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          </div>
          <h3 class="dialog-title">Publier l'exercice</h3>
          <button class="dialog-close" type="button" (click)="onCancel()" aria-label="Fermer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div class="dialog-body">
          @if (writableCircles().length === 0) {
            <p class="dialog-warning">
              Vous ne disposez de droits d'écriture sur aucun cercle. Contactez un administrateur pour obtenir les permissions nécessaires.
            </p>
          } @else {
            <div class="form-group">
              <label class="form-label" for="circle-select">Cercle de destination</label>
              <select id="circle-select" class="form-select" [(ngModel)]="selectedCircleId">
                @for (circle of writableCircles(); track circle.id) {
                  <option [value]="circle.id">{{ circle.name }}</option>
                }
              </select>
            </div>

            <div class="form-group">
              <label class="form-label" for="status-select">Statut</label>
              <select id="status-select" class="form-select" [(ngModel)]="selectedStatus">
                <option value="READY">Prêt à l'emploi</option>
                <option value="DRAFT">Brouillon</option>
                <option value="NOT_TESTED">Non testé</option>
                <option value="BUGGED">Bugué</option>
              </select>
            </div>

            <p class="dialog-warning">
              Assurez-vous que l'exercice est complet et correctement testé avant de le publier. Les utilisateurs finaux verront cet exercice comme une ressource officielle si vous le publiez en "Prêt à l'emploi".
            </p>
          }
        </div>

        <div class="dialog-footer">
          <button type="button" class="btn btn--cancel" (click)="onCancel()" [disabled]="isLoading()">Annuler</button>
          <button
            type="button"
            class="btn btn--primary"
            (click)="onPublish()"
            [disabled]="!canPublish() || isLoading()">
            @if (isLoading()) {
              <span class="publish-spinner"></span> Publication…
            } @else {
              Publier
            }
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .dialog-overlay {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 500;
      backdrop-filter: blur(2px);
      animation: fade-in 0.15s ease both;
    }
    @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }

    .dialog {
      background: var(--brand-background-components);
      border: 1px solid var(--brand-border-color);
      border-radius: 12px;
      box-shadow: 0 16px 48px rgba(15, 23, 42, 0.22);
      width: min(420px, calc(100vw - 2rem));
      animation: scale-in 0.18s cubic-bezier(0.34, 1.56, 0.64, 1) both;
    }
    @keyframes scale-in { from { transform: scale(0.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }

    .dialog-header {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--brand-border-color);
    }

    .dialog-header__icon {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      background: rgba(var(--brand-color-primary-rgb), 0.08);
      border: 1px solid rgba(var(--brand-color-primary-rgb), 0.18);
      color: var(--brand-color-primary);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .dialog-title {
      flex: 1;
      margin: 0;
      font-size: 0.9375rem;
      font-weight: 700;
      color: var(--brand-text-primary);
      letter-spacing: -0.01em;
    }

    .dialog-close {
      background: none;
      border: none;
      color: var(--brand-text-secondary);
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.15s, color 0.15s;
    }
    .dialog-close:hover { background: var(--brand-background-hover); color: var(--brand-text-primary); }

    .dialog-body {
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .dialog-warning {
      font-size: 0.8125rem;
      color: #ca8a04;
      background: rgba(234, 179, 8, 0.06);
      border: 1px solid rgba(234, 179, 8, 0.25);
      border-radius: 6px;
      padding: 0.75rem 1rem;
      margin: 0;
    }

    .form-group {
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
    }

    .form-label {
      font-size: 0.6875rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--brand-text-secondary);
    }

    .form-select {
      padding: 0.4375rem 0.625rem;
      border: 1px solid var(--brand-border-color);
      border-radius: 6px;
      font-size: 0.8125rem;
      color: var(--brand-text-primary);
      background: var(--brand-background-card, #fafafa);
      width: 100%;
      transition: border-color 0.15s;
    }
    .form-select:focus { outline: none; border-color: var(--brand-color-primary); }

    .dialog-footer {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
      padding: 0.875rem 1.25rem;
      border-top: 1px solid var(--brand-border-color);
    }

    .btn {
      padding: 0.4375rem 1rem;
      border-radius: 6px;
      font-size: 0.8125rem;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid transparent;
      transition: opacity 0.15s, background 0.15s;
    }
    .btn:disabled { opacity: 0.45; cursor: not-allowed; }
    .btn:hover:not(:disabled) { opacity: 0.88; }

    .btn--cancel {
      background: var(--brand-background-hover);
      border-color: var(--brand-border-color);
      color: var(--brand-text-primary);
    }

    .btn--primary {
      background: var(--brand-color-primary);
      color: #fff;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .publish-spinner {
      display: inline-block;
      width: 12px;
      height: 12px;
      border: 2px solid rgba(255,255,255,0.35);
      border-top-color: #fff;
      border-radius: 50%;
      animation: pub-spin 0.6s linear infinite;
    }
    @keyframes pub-spin { to { transform: rotate(360deg); } }
  `],
})
export class PublishDialogComponent {
  private readonly contextService = inject(ContextService);

  exerciseName = input<string>('');
  exerciseDescription = input<string>('');
  exerciseTemplateId = input<string | null | undefined>(null);
  isLoading = input<boolean>(false);

  publishRequest = output<PublishExerciseRequest>();
  cancelRequest = output<void>();

  selectedCircleId = '';
  selectedStatus: ExerciseStatus = 'READY';

  writableCircles = computed<Circle[]>(() =>
    this.contextService.circles().filter(c => c.writePermission)
  );

  constructor() {
    effect(() => {
      const circles = this.writableCircles();
      if (circles.length > 0 && !this.selectedCircleId) {
        this.selectedCircleId = circles[0].id;
      }
    });
  }

  canPublish(): boolean {
    return !!this.selectedCircleId && !!this.selectedStatus;
  }

  onPublish(): void {
    if (!this.canPublish()) return;

    const request: PublishExerciseRequest = {
      name: this.exerciseName() || 'Exercice sans nom',
      parentId: this.selectedCircleId,
      templateId: this.exerciseTemplateId() ?? null,
      templateVersion: null,
      code: null,
      desc: this.exerciseDescription() || '',
      type: 'EXERCISE',
      status: this.selectedStatus,
      levels: [],
      topics: [],
      files: [],
    };

    this.publishRequest.emit(request);
  }

  onCancel(): void {
    this.cancelRequest.emit();
  }
}


