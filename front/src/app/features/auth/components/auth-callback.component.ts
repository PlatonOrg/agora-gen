import { Component, OnInit, signal, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/auth/auth.service';
import { AgoraLogoComponent } from '../../../shared/ui/agora-logo/agora-logo.component';

@Component({
  selector: 'app-auth-callback',
  standalone: true,
  imports: [AgoraLogoComponent],
  template: `
    <div class="callback-container">
      <div class="logo-wrapper">
        <app-agora-logo />
      </div>
      <div class="content-wrapper">
        @if (isProcessing()) {
          <div class="loading">
            <div class="spinner"></div>
            <p>Traitement de l'authentification...</p>
          </div>
        } @else if (error()) {
          <div class="error">
            <p class="error-message">{{ error() }}</p>
            <button class="retry-button" (click)="retryLogin()">
              Réessayer
            </button>
          </div>
        } @else {
          <div class="success">
            <p>Authentification réussie ! Redirection...</p>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .callback-container {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background-color: var(--brand-background-primary);
      position: relative;
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

    .loading {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
    }

    .spinner {
      width: 48px;
      height: 48px;
      border: 4px solid var(--brand-border-color);
      border-top-color: var(--brand-color-primary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }

    .loading p, .success p {
      color: var(--brand-text-secondary);
      font-size: 1.125rem;
    }

    .error {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
    }

    .error-message {
      color: var(--brand-error);
      font-size: 1rem;
      text-align: center;
      max-width: 400px;
    }

    .retry-button {
      background-color: var(--brand-color-primary);
      color: white;
      border: none;
      border-radius: 0.375rem;
      padding: 0.75rem 1.5rem;
      font-size: 1rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .retry-button:hover {
      background-color: var(--brand-color-primary-shade);
    }
  `]
})
export class AuthCallbackComponent implements OnInit {
  protected isProcessing = signal(true);
  protected error = signal<string | null>(null);
  private isBrowser: boolean;

  constructor(
    private authService: AuthService,
    private router: Router,
    @Inject(PLATFORM_ID) platformId: Object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  ngOnInit(): void {
    if (!this.isBrowser) {
      console.log('[AuthCallback] Skipping callback processing on server');
      return;
    }

    console.log('[AuthCallback] Component initialized');
    console.log('[AuthCallback] Processing callback from PLaTon...');

    // Small delay to show the loading state
    setTimeout(() => {
      this.processCallback();
    }, 500);
  }

  private async processCallback(): Promise<void> {
    console.log('[AuthCallback] Processing callback, URL:', window.location.href);

    try {
      // Handle callback - this will exchange tokens with backend and set session cookie
      const success = await this.authService.handleCallback();

      if (success) {
        console.log('[AuthCallback] Authentication successful!');
        this.isProcessing.set(false);

        setTimeout(() => {
          console.log('[AuthCallback] Redirecting to workspace...');
          this.router.navigate(['/workspace']);
        }, 1000);
      } else {
        console.error('[AuthCallback] Authentication failed');
        this.error.set('Échec de l\'authentification. Veuillez réessayer.');
        this.isProcessing.set(false);
      }
    } catch (error: any) {
      console.error('[AuthCallback] Error processing callback:', error);
      this.error.set('Erreur lors du traitement de l\'authentification. Veuillez réessayer.');
      this.isProcessing.set(false);
    }
  }

  protected async retryLogin(): Promise<void> {
    try {
      await this.authService.initPlatonAuth();
    } catch (error) {
      console.error('[AuthCallback] Error retrying login:', error);
      await this.router.navigate(['/login']);
    }
  }
}

