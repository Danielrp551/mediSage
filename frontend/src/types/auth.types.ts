export interface AuthenticatedUser {
  id: string;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  second_last_name: string | null;
  active: boolean;
  roles: string[];
  permissions: string[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  access_expires_at: string;
  refresh_expires_at: string;
}

export interface LoginResponseBody {
  success: true;
  tokens: TokenPair;
  user: AuthenticatedUser;
}

// Marca explícita de módulo (type-only file under isolatedModules).
export {};
