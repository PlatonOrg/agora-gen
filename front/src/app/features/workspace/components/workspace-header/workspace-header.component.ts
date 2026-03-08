import { Component, input, output, signal, inject, OnInit, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { UserProfileService } from '../../../../core/auth/user-profile.service';
import { AuthService } from '../../../../core/auth/auth.service';
import { Router } from '@angular/router';
import { UserChipComponent } from '../../../../shared/ui/user-chip/user-chip.component';
import { OnboardingService } from '../../services/onboarding.service';

@Component({
  selector: 'app-workspace-header',
  standalone: true,
  imports: [CommonModule, UserChipComponent],
  templateUrl: './workspace-header.component.html',
  styleUrl: './workspace-header.component.scss',
})
export class WorkspaceHeaderComponent implements OnInit {
  isViewExerciseLoading = input.required<boolean>();
  isViewPleLoading = input.required<boolean>();
  templateName = input<string | null>(null);
  activeLeftTab = input<string | null>(null);

  viewExercise = output<void>();
  viewPle = output<void>();
  resetExercise = output<void>();
  publishExercise = output<void>();
  navigateToLogs = output<void>();
  toggleLeftPanel = output<void>();

  protected readonly userProfile = inject(UserProfileService);
  protected readonly onboarding = inject(OnboardingService);
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  protected isUserMenuOpen = signal<boolean>(false);
  protected isAdmin = computed(() => this.userProfile.profile()?.role === 'ADMIN');

  ngOnInit(): void {
    this.userProfile.load();
  }

  protected startTour(): void {
    this.closeUserMenu();
    this.onboarding.reset();
    this.onboarding.start();
  }

  protected toggleUserMenu(): void {
    this.isUserMenuOpen.update(v => !v);
  }

  protected closeUserMenu(): void {
    this.isUserMenuOpen.set(false);
  }

  protected goToLogs(): void {
    this.closeUserMenu();
    this.navigateToLogs.emit();
  }

  protected goToAdmin(): void {
    this.closeUserMenu();
    this.router.navigate(['/admin']);
  }

  protected async logout(): Promise<void> {
    this.closeUserMenu();
    await this.authService.logout();
    await this.router.navigate(['/login']);
  }

  protected truncateTemplateName(name: string): string {
    return name.length > 24 ? name.substring(0, 24) + '...' : name;
  }
}
