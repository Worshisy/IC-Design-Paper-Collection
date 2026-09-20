@echo off
REM One-click database update. Double-click this file.
REM   update.bat              refresh recent years, rebuild site, sync to iCloud
REM   update.bat --full       re-scrape every year from 2000 (slow)
REM   update.bat --no-sync    skip the iCloud copy
REM Anything you type after update.bat is passed straight to update_database.py.

setlocal
cd /d "%~dp0"

REM UTF-8 console: paper titles contain characters the default codepage cannot print.
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

REM Prefer a project venv, then py -3, then whatever python is on PATH.
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")
)

echo.
echo === Updating IEEE paper database ===
echo.
%PY% update_database.py %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Update finished. Open site\index.html to browse,
    echo or run:  %PY% serve.py    to browse with marks saved to disk.
) else (
    echo Update FAILED with exit code %RC%.
)
echo.
pause
endlocal
exit /b %RC%
