/**
 * 팀 관리 화면 — 멤버 CRUD (팀 전환·생성은 사이드바).
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { teamsApi, usersApi } from "../lib/api";
import { useTeamContext } from "../contexts/TeamContext";
import { Search, Trash2, UserMinus, UserPlus } from "lucide-react";

interface Member {
  id: string;
  user_id: string;
  role: "lead" | "member";
  joined_at: string;
}

interface UserResult {
  id: string;
  login: string;
  name: string | null;
  avatar_url: string | null;
}

export default function Team() {
  const queryClient = useQueryClient();
  const {
    teams,
    currentTeamId,
    setCurrentTeamId,
    clearCurrentTeam,
    role,
  } = useTeamContext();
  const [memberSearch, setMemberSearch] = useState("");
  const [searchResults, setSearchResults] = useState<UserResult[]>([]);

  const selectedTeamId = currentTeamId;

  useEffect(() => {
    if (!selectedTeamId && teams.length > 0) {
      setCurrentTeamId(teams[0].id);
    }
  }, [selectedTeamId, teams, setCurrentTeamId]);

  const { data: members = [] } = useQuery<Member[]>({
    queryKey: ["team-members", selectedTeamId],
    queryFn: () =>
      selectedTeamId
        ? teamsApi.getMembers(selectedTeamId).then((r) => r.data)
        : [],
    enabled: !!selectedTeamId,
  });

  const isLead = role === "lead";

  const deleteTeam = useMutation({
    mutationFn: (id: string) => teamsApi.delete(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["teams"] });
      if (selectedTeamId === id) clearCurrentTeam();
    },
  });

  const addMember = useMutation({
    mutationFn: ({ userId }: { userId: string }) =>
      teamsApi.addMember(selectedTeamId!, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team-members", selectedTeamId] });
      setMemberSearch("");
      setSearchResults([]);
    },
  });

  const removeMember = useMutation({
    mutationFn: (userId: string) =>
      teamsApi.removeMember(selectedTeamId!, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team-members", selectedTeamId] });
    },
  });

  const updateRole = useMutation({
    mutationFn: ({ userId, role: newRole }: { userId: string; role: string }) =>
      teamsApi.updateMemberRole(selectedTeamId!, userId, newRole),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team-members", selectedTeamId] });
    },
  });

  const handleSearch = async (query: string) => {
    setMemberSearch(query);
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }
    const res = await usersApi.search(query);
    setSearchResults(res.data);
  };

  if (teams.length === 0) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-semibold text-notion-text mb-4">팀 멤버 관리</h1>
        <p className="text-sm text-notion-text-secondary">
          참여 중인 팀이 없습니다. 사이드바에서 팀을 만들어 주세요.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-notion-text mb-2">팀 멤버 관리</h1>
      <p className="text-sm text-notion-text-secondary mb-6">
        팀 전환·생성은 사이드바 워크스페이스에서 할 수 있습니다.
      </p>

      <div className="flex flex-wrap items-center gap-2 mb-6">
        <label htmlFor="team-page-switcher" className="text-sm text-notion-text-secondary">
          편집할 팀
        </label>
        <select
          id="team-page-switcher"
          value={selectedTeamId ?? ""}
          onChange={(e) => setCurrentTeamId(e.target.value)}
          className="text-sm border border-notion-border rounded px-2 py-1.5"
          data-testid="team-page-switcher"
        >
          {teams.map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </select>
        {isLead && selectedTeamId && (
          <button
            type="button"
            onClick={() => deleteTeam.mutate(selectedTeamId)}
            className="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50"
            data-testid={`delete-team-${selectedTeamId}`}
          >
            팀 삭제
          </button>
        )}
      </div>

      {selectedTeamId ? (
        <div className="bg-white border border-notion-border rounded-lg">
          <div className="px-4 py-3 border-b border-notion-border">
            <h2 className="text-sm font-medium text-notion-text">멤버 관리</h2>
            {!isLead && (
              <p className="text-xs text-notion-text-secondary mt-1">
                멤버 추가·제거는 팀장만 가능합니다.
              </p>
            )}
          </div>

          <div className="p-4">
            {isLead && (
              <div className="mb-4">
                <div className="relative">
                  <Search
                    size={14}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-notion-text-secondary"
                  />
                  <input
                    type="text"
                    value={memberSearch}
                    onChange={(e) => void handleSearch(e.target.value)}
                    placeholder="사용자 검색 (login 또는 이름)"
                    className="w-full text-sm border border-notion-border rounded pl-8 pr-3 py-2 focus:outline-none focus:ring-1 focus:ring-notion-text"
                    data-testid="user-search-input"
                  />
                </div>

                {searchResults.length > 0 && (
                  <div className="mt-1 border border-notion-border rounded bg-white shadow-sm max-h-40 overflow-y-auto">
                    {searchResults.map((u) => (
                      <div
                        key={u.id}
                        className="flex items-center justify-between px-3 py-2 hover:bg-sidebar-hover"
                      >
                        <div className="flex items-center gap-2">
                          {u.avatar_url ? (
                            <img
                              src={u.avatar_url}
                              alt={u.login}
                              className="w-5 h-5 rounded-full"
                            />
                          ) : (
                            <div className="w-5 h-5 rounded-full bg-gray-200" />
                          )}
                          <span className="text-sm text-notion-text">{u.login}</span>
                          {u.name && (
                            <span className="text-xs text-notion-text-secondary">
                              {u.name}
                            </span>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={() => addMember.mutate({ userId: u.id })}
                          className="p-1 rounded hover:bg-sidebar-active text-notion-text-secondary"
                          data-testid={`add-member-${u.id}`}
                          aria-label={`${u.login} 추가`}
                        >
                          <UserPlus size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="space-y-2">
              {members.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between py-2 border-b border-notion-border last:border-0"
                  data-testid={`member-${m.user_id}`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-xs">
                      {m.user_id}
                    </div>
                    <div>
                      <span className="text-sm text-notion-text">
                        User #{m.user_id}
                      </span>
                      <span
                        className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
                          m.role === "lead"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-gray-100 text-gray-600"
                        }`}
                        data-testid={`member-role-${m.user_id}`}
                      >
                        {m.role === "lead" ? "팀장" : "팀원"}
                      </span>
                    </div>
                  </div>

                  {isLead && (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() =>
                          updateRole.mutate({
                            userId: m.user_id,
                            role: m.role === "lead" ? "member" : "lead",
                          })
                        }
                        className="text-xs px-2 py-1 rounded border border-notion-border hover:bg-sidebar-hover text-notion-text-secondary"
                        data-testid={`toggle-role-${m.user_id}`}
                      >
                        {m.role === "lead" ? "팀원으로" : "팀장으로"}
                      </button>
                      <button
                        type="button"
                        onClick={() => removeMember.mutate(m.user_id)}
                        className="p-1.5 rounded hover:bg-red-100 text-notion-text-secondary hover:text-red-500"
                        data-testid={`remove-member-${m.user_id}`}
                        aria-label="멤버 제거"
                      >
                        <UserMinus size={14} />
                      </button>
                    </div>
                  )}
                </div>
              ))}

              {members.length === 0 && (
                <p className="text-sm text-notion-text-secondary text-center py-4">
                  멤버가 없습니다
                </p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-sm text-notion-text-secondary">팀을 선택해 주세요.</p>
      )}
    </div>
  );
}
