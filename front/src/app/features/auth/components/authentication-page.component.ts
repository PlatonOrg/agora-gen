import { Component, signal, output } from '@angular/core';
import { AgoraLogoComponent } from '../../../shared/ui/agora-logo/agora-logo.component';
import { AuthService } from '../../../core/auth/auth.service';

@Component({
  selector: 'app-authentication-page',
  standalone: true,
  imports: [AgoraLogoComponent],
  template: `
    <div class="auth-container">
      <div class="logo-wrapper">
        <app-agora-logo />
      </div>
      <div class="content-wrapper">
        <button
          class="auth-button"
          (click)="handleAuthenticate()"
          [disabled]="isLoading()"
        >
          {{ isLoading() ? "Redirection vers PLaTon..." : "S'authentifier sur PLaTon" }}
        </button>
        @if (error()) {
          <p class="error-message">
            {{ error() }}
          </p>
        }
      </div>
    </div>
  `,
  styles: [`
    .auth-container {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background-color: var(--brand-background-primary);
      position: relative;
      transition: background-color 0.3s ease;
    }

    .logo-wrapper {
      position: absolute;
      top: 2rem;
    }

    .content-wrapper {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
    }

    .auth-button {
      background-color: var(--brand-color-primary);
      color: var(--brand-color-primary-contrast);
      border: none;
      border-radius: 0.375rem;
      padding: 1.3rem 3rem;
      font-size: 1.25rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.3s ease;
      font-family: var(--brand-font);
      outline: none;
    }

    .auth-button:hover:not(:disabled) {
      background-color: var(--brand-color-primary-shade);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(var(--brand-color-primary-rgb), 0.3);
    }

    .auth-button:active:not(:disabled) {
      transform: translateY(0);
    }

    .auth-button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .error-message {
      color: var(--brand-text-error);
      margin-top: 0.5rem;
      max-width: 28rem;
      text-align: center;
    }
  `]
})
export class AuthenticationPageComponent {
  authenticated = output<void>();

  protected error = signal<string | null>(null);
  protected isLoading = signal<boolean>(false);

  constructor(private readonly authService: AuthService) {}

  protected async handleAuthenticate(): Promise<void> {
    this.error.set(null);
    this.isLoading.set(true);

    console.log('[AuthenticationPage] Initializing Platon authentication...');

    try {
      // Call backend to get redirect URL and state
      await this.authService.initPlatonAuth();
      // Note: initPlatonAuth() will redirect the page, so we won't reach here
    } catch (error: any) {
      console.error('[AuthenticationPage] Error initializing authentication:', error);
      this.error.set('Erreur lors de l\'initialisation de l\'authentification. Veuillez réessayer.');
      this.isLoading.set(false);
    }
  }
}
