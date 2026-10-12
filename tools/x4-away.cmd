@echo off
rem Tell board agents they may run X4 on this machine while you are away.
rem   x4-away.cmd          away for 2 hours
rem   x4-away.cmd 5        away for 5 hours
rem   x4-away.cmd back     I am back: agents may not run X4
rem See bridge\tools\x4_run.py and docs\11-agent-testing.md.
if /I "%~1"=="back" (
  py "%~dp0..\bridge\tools\x4_run.py" back
) else if "%~1"=="" (
  py "%~dp0..\bridge\tools\x4_run.py" away
) else (
  py "%~dp0..\bridge\tools\x4_run.py" away %1
)
pause
