import { Injectable, signal, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { ApiService } from '../api/api.service';

/**
 * Response from /auth/platon/init endpoint
 */
export interface AuthInitResponse {
  redirectUrl: string;
  state: string;
}

/**
 * Response from /auth/platon/callback endpoint
 */
export interface AuthCallbackResponse {
  success: boolean;
  user: {
    id: string;
    username: string;
    role: string;
  };
}

/**
 * Response from the backend /auth/user endpoint
 */
export interface UserProfileResponse {
  id: string;
  email: string;
  username: string;
  role: string;
  permissions: string[];
}

/**
 * User information from session
 */
export interface UserInfo {
  id: string;
  username: string;
  email?: string;
  role?: string;
  permissions?: string[];
}

export interface AuthState {
  isAuthenticated: boolean;
  user: UserInfo | null;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  // Store OAuth state temporarily (only during login flow)
  private readonly OAUTH_STATE_KEY = 'agora_oauth_state';

  private isBrowser: boolean;
  private apiService: ApiService;

  private authState = signal<AuthState>({
    isAuthenticated: false,
    user: null
  });

  // Promise that resolves when session check is complete
  private sessionCheckPromise: Promise<void> | null = null;

  constructor(
    apiService: ApiService,
    @Inject(PLATFORM_ID) platformId: Object
  ) {
    this.apiService = apiService;
    this.isBrowser = isPlatformBrowser(platformId);

    // Check for existing session on service initialization (only in browser)
    if (this.isBrowser) {
      this.sessionCheckPromise = this.checkSession();
    } else {
      this.sessionCheckPromise = Promise.resolve();
    }
  }

  /**
   * Get the current authentication state
   */
  getAuthState() {
    return this.authState;
  }

  /**
   * Wait for session check to complete during service initialization
   */
  async waitForInitialization(): Promise<void> {
    if (this.sessionCheckPromise) {
      await this.sessionCheckPromise;
    }
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    return this.authState().isAuthenticated;
  }

  /**
   * Initialize Platon authentication flow
   * Calls /auth/platon/init to get redirect URL and state
   */
  async initPlatonAuth(): Promise<void> {
    if (!this.isBrowser) {
      console.log('[AuthService] Cannot init auth: not in browser context');
      return;
    }

    try {
      console.log('[AuthService] Initializing Platon authentication...');
      const response = await this.apiService.post<AuthInitResponse>('/auth/platon/init', {});
      
      console.log('[AuthService] Received redirect URL and state');
      console.log('[AuthService] State:', response.state);
      console.log('[AuthService] Redirect URL:', response.redirectUrl);

      // Store state temporarily (will be cleared after callback)
      if (this.isBrowser) {
        sessionStorage.setItem(this.OAUTH_STATE_KEY, response.state);
      }

      // Redirect to Platon
      console.log('[AuthService] Redirecting to Platon login...');
      window.location.href = response.redirectUrl;
    } catch (error) {
      console.error('[AuthService] Error initializing Platon auth:', error);
      throw error;
    }
  }

  /**
   * Handle the callback from Platon
   * Extracts tokens from URL and exchanges them with backend
   */
  async handleCallback(): Promise<boolean> {
    if (!this.isBrowser) {
      console.log('[AuthService] Cannot handle callback: not in browser context');
      return false;
    }

    console.log('[AuthService] Handling callback from Platon...');
    console.log('[AuthService] Current URL:', window.location.href);

    // Extract tokens from URL
    const urlParams = new URLSearchParams(window.location.search);
    const platonAccessToken = urlParams.get('access-token');
    const platonRefreshToken = urlParams.get('refresh-token');

    if (!platonAccessToken) {
      console.error('[AuthService] No access-token found in callback URL');
      return false;
    }

    // Get stored state
    const state = sessionStorage.getItem(this.OAUTH_STATE_KEY);
    if (!state) {
      console.error('[AuthService] No OAuth state found - session may have expired');
      return false;
    }

    console.log('[AuthService] Found access-token and state, exchanging with backend...');

    try {
      // Call backend callback endpoint
      const response = await this.apiService.post<AuthCallbackResponse>(
        '/auth/platon/callback',
        {
          state: state,
          platonAccessToken: platonAccessToken,
          platonRefreshToken: platonRefreshToken || undefined
        }
      );

      if (response.success) {
        console.log('[AuthService] ===== AUTHENTICATION SUCCESSFUL =====');
        console.log('[AuthService] User ID:', response.user.id);
        console.log('[AuthService] Username:', response.user.username);
        console.log('[AuthService] Role:', response.user.role);
        console.log('[AuthService] ====================================');

        // Clear OAuth state (no longer needed)
        sessionStorage.removeItem(this.OAUTH_STATE_KEY);

        // Update auth state with user info
        this.authState.set({
          isAuthenticated: true,
          user: {
            id: response.user.id,
            username: response.user.username,
            role: response.user.role
          }
        });

        // Fetch full user profile to get permissions
        await this.getUserProfile();

        return true;
      } else {
        console.error('[AuthService] Backend callback returned success=false');
        return false;
      }
    } catch (error: any) {
      console.error('[AuthService] Error exchanging tokens with backend:', error);
      // Clear state on error
      sessionStorage.removeItem(this.OAUTH_STATE_KEY);
      return false;
    }
  }


  /**
   * Get the current user information
   */
  getUserInfo(): UserInfo | null {
    return this.authState().user;
  }

  /**
   * Get user profile from backend (verifies session via HTTP-only cookie)
   */
  async getUserProfile(): Promise<UserProfileResponse | null> {
    if (!this.isBrowser) {
      return null;
    }

    try {
      const profile = await this.apiService.get<UserProfileResponse>('/auth/user');
      console.log('[AuthService] User profile from backend:', profile);

      // Update auth state with profile data
      this.authState.set({
        isAuthenticated: true,
        user: {
          id: profile.id,
          username: profile.username,
          email: profile.email,
          role: profile.role,
          permissions: profile.permissions
        }
      });

      return profile;
    } catch (error: any) {
      console.error('[AuthService] Error getting user profile:', error);
      // If 401, session expired or not authenticated
      if (error.message?.includes('401') || error.message?.includes('Not authenticated')) {
        this.authState.set({
          isAuthenticated: false,
          user: null
        });
      }
      return null;
    }
  }

  /**
   * Check for existing session on app initialization
   * Calls /auth/user to verify if HTTP-only cookie session is still valid
   */
  private async checkSession(): Promise<void> {
    if (!this.isBrowser) {
      return;
    }

    console.log('[AuthService] Checking for existing session...');
    
    try {
      const profile = await this.getUserProfile();
      if (profile) {
        console.log('[AuthService] Valid session found');
        console.log('[AuthService] User:', profile.username);
        console.log('[AuthService] Role:', profile.role);
      } else {
        console.log('[AuthService] No valid session found');
        this.authState.set({
          isAuthenticated: false,
          user: null
        });
      }
    } catch (error) {
      console.log('[AuthService] Session check failed (not authenticated)');
      this.authState.set({
        isAuthenticated: false,
        user: null
      });
    }
  }

  /**
   * Logout and clear session
   */
  async logout(): Promise<void> {
    console.log('[AuthService] Logging out...');

    // Logout from backend (clears session and cookie)
    try {
      await this.apiService.post('/auth/logout', {});
      console.log('[AuthService] Backend session terminated');
    } catch (error) {
      console.error('[AuthService] Error logging out from backend:', error);
    }

    // Clear any temporary OAuth state
    if (this.isBrowser) {
      sessionStorage.removeItem(this.OAUTH_STATE_KEY);
    }

    // Reset auth state
    this.authState.set({
      isAuthenticated: false,
      user: null
    });
  }
}

