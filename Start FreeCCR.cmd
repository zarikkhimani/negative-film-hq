@echo off
setlocal
set "FREECCR_DIR=%~dp0FreeCCR"
if not exist "%FREECCR_DIR%\.venv\Scripts\pythonw.exe" (
    echo FreeCCR's local Python environment is missing.
    pause
    exit /b 1
)
start "" /D "%FREECCR_DIR%" "%FREECCR_DIR%\.venv\Scripts\pythonw.exe" "%FREECCR_DIR%\launch_local.py" %*
