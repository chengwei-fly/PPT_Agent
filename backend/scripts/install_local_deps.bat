@echo off
REM Install local sibling-repo dependencies - Windows wrapper.
REM Equivalent to install_local_deps.sh for PowerShell / cmd.

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%..
set REPO_ROOT=%BACKEND_DIR%\..
set AGENTSCOPE_DIR=%REPO_ROOT%\AgentScope

echo [install_local_deps] repo root: %REPO_ROOT%
echo [install_local_deps] agentscope dir: %AGENTSCOPE_DIR%

if not exist "%AGENTSCOPE_DIR%\pyproject.toml" (
  echo ERROR: AgentScope not found at %AGENTSCOPE_DIR% 1>&2
  exit /b 1
)

echo [install_local_deps] Installing AgentScope editable ...
python -m pip install -e "%AGENTSCOPE_DIR%"

echo [install_local_deps] Verifying imports ...
python -c "from agentscope.agent import Agent; print('OK')"

echo [install_local_deps] Done.
endlocal
