@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
echo Connecting LLM/STT to @SSH_TARGET@.
echo Enter your usual SSH password if asked; typing is not displayed.
echo A quiet connected window is normal. Leave it open while playing.
echo Press Ctrl+C when the playtest is finished.
ssh -NT -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:18790:127.0.0.1:18790 -L 127.0.0.1:18791:127.0.0.1:18791 "@SSH_TARGET@"
set "result=%errorlevel%"
echo The SSH tunnel has closed. Read any message above.
if not "%BREEZE_PNY_SMOKE_NONINTERACTIVE%"=="1" pause
exit /b %result%
