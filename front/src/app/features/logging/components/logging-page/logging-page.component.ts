import { Component, signal, inject, computed } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { LogConversationsViewComponent } from '../log-conversations-view/log-conversations-view.component';
import { LogStatsViewComponent } from '../log-stats-view/log-stats-view.component';
import { AdminDashboardPageComponent } from '../../../admin/components/admin-dashboard-page/admin-dashboard-page.component';
import { UserProfileService } from '../../../../core/auth/user-profile.service';
import { AuthService } from '../../../../core/auth/auth.service';
import { UserChipComponent } from '../../../../shared/ui/user-chip/user-chip.component';
import { LogPromptsViewComponent } from '../log-prompts-view/log-prompts-view.component';

export type LogTab = 'conversations' | 'config' | 'statistics' | 'prompts';

interface NavItem { tab: LogTab; label: string; icon: string; }

@Component({
  selector: 'app-logging-page',
  standalone: true,
  imports: [
    CommonModule,
    LogConversationsViewComponent,
    LogStatsViewComponent,
    AdminDashboardPageComponent,
    UserChipComponent,
    LogPromptsViewComponent,
  ],
  templateUrl: './logging-page.component.html',
  styleUrl: './logging-page.component.scss',
})
export class LoggingPageComponent {
  private readonly router = inject(Router);
  private readonly authService = inject(AuthService);
  protected readonly userProfile = inject(UserProfileService);

  protected readonly activeTab = signal<LogTab>('conversations');
  protected readonly isUserMenuOpen = signal(false);

  protected readonly navItems: NavItem[] = [
    {
      tab: 'conversations',
      label: 'Conversations',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
    },
    {
      tab: 'statistics',
      label: 'Statistiques',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
    },
    {
      tab: 'config',
      label: 'Configuration',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>`,
    },
    {
      tab: 'prompts',
      label: 'Prompts',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
    },
  ];

  protected readonly activeLabel = computed(() =>
    this.navItems.find(n => n.tab === this.activeTab())?.label ?? ''
  );

  protected goBack(): void {
    this.router.navigate(['/workspace']);
  }

  protected toggleUserMenu(): void {
    this.isUserMenuOpen.update(v => !v);
  }

  protected closeUserMenu(): void {
    this.isUserMenuOpen.set(false);
  }

  protected async logout(): Promise<void> {
    this.closeUserMenu();
    await this.authService.logout();
    await this.router.navigate(['/login']);
  }
}
