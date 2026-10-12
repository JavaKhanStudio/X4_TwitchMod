@echo off
rem Double-click me. Starts the X4 <-> Twitch companion + dashboard on Windows.
rem
rem This exists because .ps1 files are not double-clickable (Windows opens them in
rem Notepad, and the execution policy blocks them anyway) -- so this wrapper calls
rem run-companion.ps1 next to it with the policy bypassed for this one process.
rem Any arguments you pass are forwarded (e.g. --source stdin for a Twitch-less test).
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-companion.ps1" %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo [companion exited with code %RC% -- see the messages above]
  pause
)
endlocal
