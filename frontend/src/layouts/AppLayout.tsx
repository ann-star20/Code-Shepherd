/**
 * 노션 스타일 사이드바 레이아웃.
 * 좌측 접이식 사이드바 + 상단바 + 콘텐츠 영역.
 * 역할(lead/member)별 메뉴 분기.
 */

import { useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  GitPullRequest,
  Home,
  LayoutDashboard,
  LogOut,
  Network,
  Search,
  Settings,
  Users,
} from "lucide-react";
import { useAuth } from "../lib/auth";
import { useQuery } from "@tanstack/react-query";
import { teamsApi } from "../lib/api";

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  leadOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "홈", path: "/", icon: <Home size={16} /> },
  { label: "팀 관리", path: "/team", icon: <Users size={16} /> },
  { label: "PR 리뷰", path: "/review", icon: <GitPullRequest size={16} /> },
  { label: "KMS 검색", path: "/kms", icon: <BookOpen size={16} /> },
  { label: "학습 경로", path: "/learning", icon: <LayoutDashboard size={16} /> },
  { label: "지식 그래프", path: "/graph", icon: <Network size={16} />, leadOnly: true },
  { label: "설정", path: "/settings", icon: <Settings size={16} /> },
];

function useUserRole(): "lead" | "member" | null {
  const { data } = useQuery({
    queryKey: ["teams"],
    queryFn: () => teamsApi.list().then((r) => r.data),
  });
  if (!data || !Array.isArray(data) || data.length === 0) return "member";
  return null; // 실제 role은 서버에서 가져와야 함; 여기선 단순화
}

export default function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const isActive = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

  return (
    <div className="flex h-screen overflow-hidden bg-notion-bg">
      {/* 사이드바 */}
      <aside
        className={`
          flex-shrink-0 flex flex-col bg-sidebar border-r border-sidebar-border
          transition-all duration-200 ease-in-out
          ${sidebarOpen ? "w-60" : "w-0 overflow-hidden"}
        `}
      >
        {/* 상단 — 로고 + 토글 */}
        <div className="flex items-center justify-between gap-2 px-3 py-3 border-b border-sidebar-border">
          <Link to="/" className="min-w-0 flex-shrink">
            <img
              src="/logo2.png"
              alt="code shepherd"
              className="h-7 w-auto max-w-[148px] object-contain object-left"
              data-testid="sidebar-logo"
            />
          </Link>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1 rounded hover:bg-sidebar-hover text-notion-text-secondary"
            aria-label="사이드바 닫기"
          >
            <ChevronLeft size={16} />
          </button>
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 overflow-y-auto py-2">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`
                flex items-center gap-2 px-3 py-1.5 mx-1 rounded text-sm
                transition-colors duration-100
                ${
                  isActive(item.path)
                    ? "bg-sidebar-active text-notion-text font-medium"
                    : "text-notion-text-secondary hover:bg-sidebar-hover hover:text-notion-text"
                }
              `}
            >
              {item.icon}
              {item.label}
            </Link>
          ))}
        </nav>

        {/* 하단 — 사용자 메뉴 */}
        <div className="border-t border-sidebar-border px-3 py-3">
          <div className="flex items-center gap-2 mb-2">
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.login}
                className="w-6 h-6 rounded-full"
              />
            ) : (
              <div className="w-6 h-6 rounded-full bg-gray-300 flex items-center justify-center text-xs">
                {user?.login?.[0]?.toUpperCase()}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-notion-text truncate">
                {user?.name ?? user?.login}
              </p>
              <p className="text-xs text-notion-text-secondary truncate">
                @{user?.login}
              </p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-notion-text-secondary hover:bg-sidebar-hover hover:text-notion-text transition-colors"
            data-testid="logout-button"
          >
            <LogOut size={14} />
            로그아웃
          </button>
        </div>
      </aside>

      {/* 메인 콘텐츠 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 상단 바 */}
        <header className="flex items-center gap-2 px-4 py-2 border-b border-notion-border bg-notion-bg">
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1 rounded hover:bg-sidebar-hover text-notion-text-secondary"
              aria-label="사이드바 열기"
            >
              <ChevronRight size={16} />
            </button>
          )}
          {/* 검색 바 자리 */}
          <div className="flex items-center gap-2 flex-1 max-w-md bg-notion-bg-secondary rounded px-3 py-1.5 text-sm text-notion-text-secondary border border-notion-border">
            <Search size={14} />
            <span>검색...</span>
          </div>
        </header>

        {/* 페이지 콘텐츠 */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
