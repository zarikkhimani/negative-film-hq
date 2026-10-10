@echo off
setlocal
set "DT_ROOT=%~dp0darktable"
if not exist "%DT_ROOT%\app\bin\darktable.exe" (
    echo darktable is missing from "%DT_ROOT%\app\bin".
    pause
    exit /b 1
)
set "APPDATA=%DT_ROOT%\local-data\appdata"
set "LOCALAPPDATA=%DT_ROOT%\local-data\localappdata"
set "XDG_CACHE_HOME=%DT_ROOT%\local-data\cache"
set "CUDA_CACHE_PATH=%DT_ROOT%\local-data\cache\nvidia"
for %%D in ("%APPDATA%" "%LOCALAPPDATA%" "%DT_ROOT%\local-data\config" "%DT_ROOT%\local-data\cache" "%DT_ROOT%\local-data\tmp") do if not exist "%%~D" mkdir "%%~D"
start "" /D "%DT_ROOT%" "%DT_ROOT%\app\bin\darktable.exe" --configdir "%DT_ROOT%\local-data\config" --cachedir "%DT_ROOT%\local-data\cache" --tmpdir "%DT_ROOT%\local-data\tmp" %*
