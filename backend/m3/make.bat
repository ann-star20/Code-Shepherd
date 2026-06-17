@echo off
rem Makefile과 동일 타깃의 Windows 셸 — make 미설치 환경용 (.\make.bat eval 등)
setlocal
set PY=.venv\Scripts\python.exe

if "%1"=="eval"        ( %PY% -m eval.harness & goto :eof )
if "%1"=="eval-one"    (
  if "%PR%"=="" ( echo [오류] PR 변수 필요: set PR=pr_003 ^&^& .\make.bat eval-one & goto :eof )
  %PY% -m eval.harness --only %PR% & goto :eof
)
if "%1"=="eval-failed" ( %PY% -m eval.harness --failed & goto :eof )
if "%1"=="reindex"     ( %PY% -m src.ingestion & goto :eof )
if "%1"=="demo"        ( %PY% -m streamlit run app/streamlit_app.py & goto :eof )
if "%1"=="webhook"     ( %PY% -m src.adapters.webhook_adapter & goto :eof )
if "%1"=="test"        ( %PY% -m pytest tests/ -q & goto :eof )

echo 사용법: .\make.bat [eval^|eval-one^|eval-failed^|reindex^|demo^|webhook^|test]
echo   eval-one 은 PR 변수 필요: set PR=pr_003 ^&^& .\make.bat eval-one
