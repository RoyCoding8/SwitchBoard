@echo off
setlocal
cd /d "%~dp0"

:: Check if uv is installed
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 'uv' is not installed or not in PATH.
    echo Please install it from https://astral.sh/uv
    pause
    exit /b 1
)

echo [Switchboard] Starting AI Tool Manager...
uv run switchboard
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Application exited with error code %ERRORLEVEL%
    pause
)
endlocal
