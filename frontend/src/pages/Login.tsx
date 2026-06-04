/**
 * 로그인 페이지 — GitHub OAuth 시작.
 */

import { authApi } from "../lib/api";

export default function Login() {
  const handleGitHubLogin = () => {
    window.location.href = authApi.getAuthorizeUrl();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-notion-bg-secondary">
      <div className="w-full max-w-sm bg-white rounded-xl border border-notion-border shadow-sm p-8">
        <div className="text-center mb-8">
          <img
            src="/logo1.png"
            alt="code shepherd"
            width={128}
            height={128}
            className="mx-auto h-auto w-32 object-contain"
            data-testid="login-logo"
          />
          <p className="mt-4 text-sm text-notion-text-secondary">
            조직 지식 관리와 개발자 온보딩을 한곳에서
          </p>
        </div>

        <button
          onClick={handleGitHubLogin}
          data-testid="github-login-button"
          className="
            w-full flex items-center justify-center gap-3
            bg-[#2b3d56] text-white font-medium text-sm
            py-2.5 px-4 rounded-lg
            hover:bg-[#354d6b] transition-colors
            focus:outline-none focus:ring-2 focus:ring-[#e87722] focus:ring-offset-2
          "
        >
          <svg viewBox="0 0 16 16" className="w-5 h-5 fill-current">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
          GitHub으로 로그인
        </button>

        <p className="mt-4 text-center text-xs text-notion-text-secondary">
          GitHub 계정으로 팀 협업 환경에 접속합니다
        </p>
      </div>
    </div>
  );
}
