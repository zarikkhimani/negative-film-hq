@echo off
setlocal
set "PHOTO_ROOT=%~dp0"
if not exist "%PHOTO_ROOT%FreeCCR\.venv\Scripts\pythonw.exe" (
    echo NegativeLab needs FreeCCR's local Python environment.
    pause
    exit /b 1
)
start "" /D "%PHOTO_ROOT%NegativeLab" "%PHOTO_ROOT%FreeCCR\.venv\Scripts\pythonw.exe" "%PHOTO_ROOT%NegativeLab\app.py" %*
