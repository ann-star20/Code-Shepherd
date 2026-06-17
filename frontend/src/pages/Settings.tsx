/**
 * 설정 화면 — 사용자 정보, 로그아웃.
 */

import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { LogOut, User } from "lucide-react";

export default function Settings() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-notion-text mb-6">설정</h1>

      {/* 프로필 섹션 */}
      <div className="bg-white border border-notion-border rounded-lg mb-4">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-notion-border">
          <User size={16} className="text-notion-text-secondary" />
          <h2 className="text-sm font-medium text-notion-text">내 프로필</h2>
        </div>
        <div className="px-4 py-4 flex items-center gap-4">
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.login}
              className="w-16 h-16 rounded-full border border-notion-border"
            />
          ) : (
            <div className="w-16 h-16 rounded-full bg-gray-200 flex items-center justify-center text-xl font-bold text-gray-500">
              {user?.login?.[0]?.toUpperCase()}
            </div>
          )}
          <div>
            <p className="text-base font-medium text-notion-text">{user?.name}</p>
            <p className="text-sm text-notion-text-secondary">@{user?.login}</p>
          </div>
        </div>
      </div>

      {/* 로그아웃 */}
      <div className="bg-white border border-notion-border rounded-lg">
        <div className="px-4 py-4">
          <button
            onClick={handleLogout}
            data-testid="settings-logout-button"
            className="flex items-center gap-2 px-4 py-2 rounded bg-red-50 text-red-600 hover:bg-red-100 transition-colors text-sm font-medium"
          >
            <LogOut size={16} />
            로그아웃
          </button>
        </div>
      </div>
    </div>
  );
}
