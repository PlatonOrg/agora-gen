export interface PlatonUser {
  id: string;
  username: string;
  firstName: string | null;
  lastName: string | null;
  email: string | null;
  role: string | null;
  active: boolean | null;
  hasPassword: boolean | null;
  createdAt: string | null;
  updatedAt: string | null;
  lastLogin: string | null;
  firstLogin: string | null;
  lastActivity: string | null;
  discordId: string | null;
}

