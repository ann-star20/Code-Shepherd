/**
 * 팀 관리 화면.
 * - 내 팀 목록
 * - 팀 생성
 * - 팀 수정/삭제 (lead)
 * - 사용자 검색으로 팀원 추가 (lead)
 * - 멤버 제거/역할변경 (lead)
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { teamsApi, usersApi } from "../lib/api";
import { Plus, Search, Trash2, UserMinus, UserPlus, Users } from "lucide-react";

interface Team {
  id: number;
  name: string;
  created_at: string;
}

interface Member {
  id: number;
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
  const [newTeamName, setNewTeamName] = useState("");
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);
  const [memberSearch, setMemberSearch] = useState("");
  const [searchResults, setSearchResults] = useState<UserResult[]>([]);

  const { data: teams = [] } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: () => teamsApi.list().then((r) => r.data),
  });

  const { data: members = [] } = useQuery<Member[]>({
    queryKey: ["team-members", selectedTeamId],
    queryFn: () =>
      selectedTeamId
        ? teamsApi.getMembers(selectedTeamId).then((r) => r.data)
        : [],
    enabled: !!selectedTeamId,
  });

  const createTeam = useMutation({
    mutationFn: (name: string) => teamsApi.create(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["teams"] });
      setNewTeamName("");
    },
  });

  const deleteTeam = useMutation({
    mutationFn: (id: number) => teamsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["teams"] });
      setSelectedTeamId(null);
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
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      teamsApi.updateMemberRole(selectedTeamId!, userId, role),
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

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-notion-text mb-6">팀 관리</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 팀 목록 */}
        <div className="md:col-span-1">
          <div className="bg-white border border-notion-border rounded-lg">
            <div className="flex items-center justify-between px-4 py-3 border-b border-notion-border">
              <h2 className="text-sm font-medium text-notion-text">내 팀</h2>
            </div>

            <div className="p-3">
              {/* 팀 생성 */}
              <div className="flex gap-2 mb-3">
                <input
                  type="text"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  placeholder="새 팀 이름"
                  className="flex-1 text-sm border border-notion-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-notion-text"
                  data-testid="new-team-input"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && newTeamName.trim()) {
                      createTeam.mutate(newTeamName.trim());
                    }
                  }}
                />
                <button
                  onClick={() => newTeamName.trim() && createTeam.mutate(newTeamName.trim())}
                  className="p-1.5 rounded bg-notion-text text-white hover:bg-opacity-80"
                  data-testid="create-team-button"
                  aria-label="팀 생성"
                >
                  <Plus size={14} />
                </button>
              </div>

              {/* 팀 목록 */}
              {teams.map((team) => (
                <div
                  key={team.id}
                  onClick={() => setSelectedTeamId(team.id)}
                  className={`
                    flex items-center justify-between px-3 py-2 rounded cursor-pointer
                    ${selectedTeamId === team.id
                      ? "bg-sidebar-active"
                      : "hover:bg-sidebar-hover"
                    }
                  `}
                  data-testid={`team-item-${team.id}`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Users size={14} className="text-notion-text-secondary flex-shrink-0" />
                    <span className="text-sm text-notion-text truncate">{team.name}</span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteTeam.mutate(team.id);
                    }}
                    className="p-1 rounded hover:bg-red-100 text-notion-text-secondary hover:text-red-500"
                    aria-label="팀 삭제"
                    data-testid={`delete-team-${team.id}`}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}

              {teams.length === 0 && (
                <p className="text-xs text-notion-text-secondary text-center py-4">
                  팀이 없습니다
                </p>
              )}
            </div>
          </div>
        </div>

        {/* 멤버 관리 */}
        <div className="md:col-span-2">
          {selectedTeamId ? (
            <div className="bg-white border border-notion-border rounded-lg">
              <div className="px-4 py-3 border-b border-notion-border">
                <h2 className="text-sm font-medium text-notion-text">멤버 관리</h2>
              </div>

              <div className="p-4">
                {/* 사용자 검색 + 추가 */}
                <div className="mb-4">
                  <div className="relative">
                    <Search
                      size={14}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-notion-text-secondary"
                    />
                    <input
                      type="text"
                      value={memberSearch}
                      onChange={(e) => handleSearch(e.target.value)}
                      placeholder="사용자 검색 (login 또는 이름)"
                      className="w-full text-sm border border-notion-border rounded pl-8 pr-3 py-2 focus:outline-none focus:ring-1 focus:ring-notion-text"
                      data-testid="user-search-input"
                    />
                  </div>

                  {/* 검색 결과 드롭다운 */}
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
                              <span className="text-xs text-notion-text-secondary">{u.name}</span>
                            )}
                          </div>
                          <button
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

                {/* 멤버 목록 */}
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

                      <div className="flex items-center gap-1">
                        {/* 역할 변경 */}
                        <button
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
                        {/* 멤버 제거 */}
                        <button
                          onClick={() => removeMember.mutate(m.user_id)}
                          className="p-1.5 rounded hover:bg-red-100 text-notion-text-secondary hover:text-red-500"
                          data-testid={`remove-member-${m.user_id}`}
                          aria-label="멤버 제거"
                        >
                          <UserMinus size={14} />
                        </button>
                      </div>
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
            <div className="h-full flex items-center justify-center">
              <p className="text-sm text-notion-text-secondary">
                왼쪽에서 팀을 선택하세요
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
