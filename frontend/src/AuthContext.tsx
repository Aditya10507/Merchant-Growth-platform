/**
 * AuthContext.tsx
 * ---------------
 * Holds the current merchant's session (or null if logged out) and
 * exposes login/signup/logout actions. Centralizing this in a context
 * means AuthPage and DashboardPage share one source of truth instead of
 * passing auth state through props.
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import * as api from "./api";
import type { AuthResponse } from "./types";

interface AuthContextValue {
  session: AuthResponse | null;
  signup: (businessName: string, email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthResponse | null>(null);

  const applySession = useCallback((auth: AuthResponse) => {
    api.setAuthToken(auth.access_token);
    setSession(auth);
  }, []);

  const signup = useCallback(
    async (businessName: string, email: string, password: string) => {
      const auth = await api.signup(businessName, email, password);
      applySession(auth);
    },
    [applySession]
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const auth = await api.login(email, password);
      applySession(auth);
    },
    [applySession]
  );

  const logout = useCallback(() => {
    api.setAuthToken(null);
    setSession(null);
  }, []);

  // Memoized so consumers don't re-render just because this provider re-rendered.
  const value = useMemo<AuthContextValue>(
    () => ({ session, signup, login, logout }),
    [session, signup, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
