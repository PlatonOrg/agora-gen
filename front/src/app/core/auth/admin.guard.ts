import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { UserProfileService } from './user-profile.service';

export const adminGuard: CanActivateFn = async () => {
  const userProfile = inject(UserProfileService);
  const router = inject(Router);

  // Ensure profile is loaded
  await userProfile.load();

  const role = userProfile.profile()?.role?.toLowerCase();
  if (role === 'admin') {
    return true;
  }

  return router.createUrlTree(['/workspace']);
};



