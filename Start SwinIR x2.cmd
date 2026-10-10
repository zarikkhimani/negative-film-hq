@echo off
setlocal
set "SWINIR_DIR=%~dp0SwinIR"
if not exist "%SWINIR_DIR%\.venv\Scripts\python.exe" (
    echo SwinIR's local Python environment is missing.
    pause
    exit /b 1
)
"%SWINIR_DIR%\.venv\Scripts\python.exe" -u "%SWINIR_DIR%\upscale_x2.py" %*
set "SWINIR_EXIT=%ERRORLEVEL%"
pause
exit /b %SWINIR_EXIT%
