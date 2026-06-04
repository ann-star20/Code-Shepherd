/**
 * 라우터 + 인증 가드
 */

import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import AppLayout from "./layouts/AppLayout";

// Pages
import Login from "./pages/Login";
import DashboardHome from "./pages/DashboardHome";
import Team from "./pages/Team";
import Settings from "./pages/Settings";
import KmsPlaceholder from "./pages/kms/Placeholder";
import ReviewPlaceholder from "./pages/review/Placeholder";
import LearningPlaceholder from "./pages/learning/Placeholder";
import GraphPlaceholder from "./pages/graph/Placeholder";

function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-notion-text-secondary text-sm">로딩 중...</div>
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-notion-text-secondary text-sm">로딩 중...</div>
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
      />

      {/* OAuth callback — 토큰을 받아 저장 후 대시보드로 */}
      <Route path="/auth/callback" element={<OAuthCallback />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardHome />} />
          <Route path="/team" element={<Team />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/kms" element={<KmsPlaceholder />} />
          <Route path="/review" element={<ReviewPlaceholder />} />
          <Route path="/learning" element={<LearningPlaceholder />} />
          <Route path="/graph" element={<GraphPlaceholder />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function OAuthCallback() {
  const params = new URLSearchParams(window.location.search);
  const accessToken = params.get("access_token");
  const refreshToken = params.get("refresh_token");

  if (accessToken) {
    localStorage.setItem("access_token", accessToken);
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
  }

  return <Navigate to="/" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
