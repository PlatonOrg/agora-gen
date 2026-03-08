import { Injectable, signal, inject, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { ApiService } from '../api/api.service';
import { PlatonUser } from './user.model';

@Injectable({ providedIn: 'root' })
export class UserProfileService {
  private readonly api = inject(ApiService);
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));

  readonly profile = signal<PlatonUser | null>(null);
  readonly loading = signal<boolean>(false);

  async load(): Promise<void> {
    if (!this.isBrowser) return;
    if (this.profile()) return;
    this.loading.set(true);
    try {
      const user = await this.api.get<PlatonUser>('/context/users/me');
      this.profile.set(user);
    } catch (error: unknown) {
      console.warn('[UserProfileService] Could not load user profile:', error);
      this.profile.set(null);
    } finally {
      this.loading.set(false);
    }
  }

  clear(): void {
    this.profile.set(null);
  }
}


