@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
"python\python.exe" -X utf8 "installer\collect_windows_playtest.py"
set "result=%errorlevel%"
popd
if not "%BREEZE_PNY_SMOKE_NONINTERACTIVE%"=="1" pause
exit /b %result%
