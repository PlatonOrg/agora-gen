import { Component, OnInit, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Router, RouterOutlet, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AuthService } from './core/auth/auth.service';
import { ContextService } from './features/workspace/services/context.service';
import { LlmCapabilitiesService } from './core/llm/llm-capabilities.service';

const PUBLIC_PATHS = ['/login', '/auth/callback'];

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: `<router-outlet />`,
  styles: [`:host { display: block; height: 100vh; overflow: hidden; }`]
})
export class App implements OnInit {
  private readonly isBrowser: boolean;
  private contextLoaded = false;

  constructor(
    private readonly authService: AuthService,
    private readonly contextService: ContextService,
    private readonly router: Router,
    private readonly llmCapabilitiesService: LlmCapabilitiesService,
    @Inject(PLATFORM_ID) platformId: Object
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  async ngOnInit(): Promise<void> {
    if (!this.isBrowser) return;

    await this.authService.waitForInitialization();

    try {
      await this.llmCapabilitiesService.loadCapabilities();
    } catch (e) {
      console.warn('[App] Could not load LLM capabilities:', e);
    }

    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe(async (event: NavigationEnd) => {
      await this.handleNavigation(event.urlAfterRedirects || event.url);
    });

    await this.handleNavigation(this.router.url);
  }

  private async handleNavigation(url: string): Promise<void> {
    const isPublic = PUBLIC_PATHS.some(p => url.startsWith(p));

    if (isPublic) {
      if (url.startsWith('/login') && this.authService.isAuthenticated()) {
        await this.ensureContextAndRedirect();
      }
      return;
    }

    if (!this.authService.isAuthenticated()) {
      this.router.navigate(['/login']);
      return;
    }

    await this.ensureContextAndRedirect();
  }

  private async ensureContextAndRedirect(): Promise<void> {
    if (!this.contextLoaded) {
      const profile = this.authService.getUserInfo();
      if (!profile) {
        this.router.navigate(['/login']);
        return;
      }

      await this.contextService.loadTopics();
      await this.contextService.loadLevels();
      await this.contextService.loadCirclesTree();
      this.contextLoaded = true;
    }

    const url = this.router.url;
    if (!url.startsWith('/workspace') && !url.startsWith('/logs') && !url.startsWith('/admin')) {
      await this.router.navigate(['/workspace']);
    }
  }
}
