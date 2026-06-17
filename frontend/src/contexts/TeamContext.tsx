/**
 * 전역 활성 팀 컨텍스트 — 팀 선택 persist, 멤버 역할 조회.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { teamsApi } from "../lib/api";
import { useAuth } from "../lib/auth";

const STORAGE_KEY = "codeshepherd:currentTeamId";

export interface Team {
  id: string;
  name: string;
  github_repo: string;
  created_at: string;
}

export type TeamRole = "lead" | "member";

interface TeamContextValue {
  teams: Team[];
  teamsLoading: boolean;
  currentTeamId: string | null;
  currentTeam: Team | null;
  setCurrentTeamId: (id: string | null) => void;
  clearCurrentTeam: () => void;
  role: TeamRole | null;
  roleLoading: boolean;
  createTeam: (name: string, githubRepo: string) => Promise<Team>;
}

const TeamContext = createContext<TeamContextValue | null>(null);

function readStoredTeamId(): string | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw && raw.length > 0 ? raw : null;
}

export function TeamProvider({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [currentTeamId, setCurrentTeamIdState] = useState<string | null>(() =>
    readStoredTeamId()
  );

  const { data: teams = [], isLoading: teamsLoading } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: () => teamsApi.list().then((r) => r.data),
    enabled: isAuthenticated,
  });

  const persistTeamId = useCallback((id: string | null) => {
    if (id == null) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, id);
    }
    setCurrentTeamIdState(id);
  }, []);

  useEffect(() => {
    if (teamsLoading || !isAuthenticated) return;

    if (teams.length === 0) {
      if (currentTeamId != null) persistTeamId(null);
      return;
    }

    const storedValid =
      currentTeamId != null && teams.some((t) => t.id === currentTeamId);

    if (storedValid) return;

    if (teams.length === 1) {
      persistTeamId(teams[0].id);
      return;
    }

    if (currentTeamId != null && !storedValid) {
      persistTeamId(null);
    }
  }, [teams, teamsLoading, isAuthenticated, currentTeamId, persistTeamId]);

  const { data: members = [], isLoading: roleLoading } = useQuery({
    queryKey: ["team-members", currentTeamId],
    queryFn: () =>
      currentTeamId
        ? teamsApi.getMembers(currentTeamId).then((r) => r.data)
        : [],
    enabled: !!currentTeamId && isAuthenticated,
  });

  const role = useMemo((): TeamRole | null => {
    if (!currentTeamId || !user) return null;
    const uid = String(user.id);
    const row = members.find((m: { user_id: string }) => String(m.user_id) === uid);
    if (!row) return null;
    return row.role === "lead" ? "lead" : "member";
  }, [currentTeamId, user, members]);

  const createTeamMutation = useMutation({
    mutationFn: ({ name, githubRepo }: { name: string; githubRepo: string }) =>
      teamsApi.create(name, githubRepo).then((r) => r.data as Team),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
  });

  const createTeam = useCallback(
    async (name: string, githubRepo: string) => {
      const team = await createTeamMutation.mutateAsync({ name, githubRepo });
      persistTeamId(team.id);
      return team;
    },
    [createTeamMutation, persistTeamId]
  );

  const currentTeam = useMemo(
    () => teams.find((t) => t.id === currentTeamId) ?? null,
    [teams, currentTeamId]
  );

  const value: TeamContextValue = {
    teams,
    teamsLoading,
    currentTeamId,
    currentTeam,
    setCurrentTeamId: persistTeamId,
    clearCurrentTeam: () => persistTeamId(null),
    role,
    roleLoading,
    createTeam,
  };

  return (
    <TeamContext.Provider value={value}>{children}</TeamContext.Provider>
  );
}

export function useTeamContext(): TeamContextValue {
  const ctx = useContext(TeamContext);
  if (!ctx) throw new Error("useTeamContext must be used within TeamProvider");
  return ctx;
}
