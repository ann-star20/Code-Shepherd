/**
 * 인증 컨텍스트 — 현재 사용자 정보, 로그인/로그아웃 핸들러 제공.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { authApi } from "./api";

export interface User {
  id: string;
  login: string;
  name: string | null;
  avatar_url: string | null;
  team?: string | null;
  skill_level?: string;
  created_at: string;
}

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  /** OAuth 콜백 후 토큰 저장 + /auth/me 로 사용자 상태 동기화 */
  completeLogin: (accessToken: string, refreshToken: string) => Promise<void>;
  /** localStorage 토큰으로 사용자 상태만 다시 로드 */
  reloadUser: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const reloadUser = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setUser(null);
      return;
    }
    const res = await authApi.getMe();
    setUser(res.data);
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setIsLoading(false);
      return;
    }
    reloadUser()
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, [reloadUser]);

  const completeLogin = useCallback(
    async (accessToken: string, refreshToken: string) => {
      localStorage.setItem("access_token", accessToken);
      localStorage.setItem("refresh_token", refreshToken);
      setIsLoading(true);
      try {
        await reloadUser();
      } finally {
        setIsLoading(false);
      }
    },
    [reloadUser]
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        completeLogin,
        reloadUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
