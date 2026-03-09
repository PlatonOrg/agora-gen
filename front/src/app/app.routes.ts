import { Routes } from '@angular/router';
import { AuthCallbackComponent } from './features/auth/components/auth-callback.component';
import { AuthenticationPageComponent } from './features/auth/components/authentication-page.component';
import { WorkspacePageComponent } from './features/workspace/components/workspace-page/workspace-page.component';
import { LoggingPageComponent } from './features/logging/components/logging-page/logging-page.component';
import { AdminDashboardPageComponent } from './features/admin/components/admin-dashboard-page/admin-dashboard-page.component';
import { adminGuard } from './core/auth/admin.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'login',
    pathMatch: 'full'
  },
  {
    path: 'login',
    component: AuthenticationPageComponent
  },
  {
    path: 'auth/callback',
    component: AuthCallbackComponent
  },
  {
    path: 'workspace',
    component: WorkspacePageComponent
  },
  {
    path: 'logs',
    component: LoggingPageComponent,
    canActivate: [adminGuard],
  },
  {
    path: 'admin',
    component: AdminDashboardPageComponent,
    canActivate: [adminGuard],
  }
];
