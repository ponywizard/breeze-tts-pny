@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
set "BREEZE_PNY_NO_PAUSE=1"
if not defined BREEZE_PNY_SMOKE_URL set "BREEZE_PNY_SMOKE_URL=http://127.0.0.1:18792"
if not exist "test-results\voice-samples" mkdir "test-results\voice-samples"
echo Checking six adapters and Spike. Start the companion first.
echo Voice checks for mod @MOD_VERSION@ >"test-results\voice-check.txt"
for %%C in (applejack fluttershy pinkie_pie rainbow_dash rarity twilight_sparkle spike) do (
  echo Checking %%C...
  call check-voice.cmd --url "%BREEZE_PNY_SMOKE_URL%" --character %%C --output "test-results\voice-samples\%%C.wav" >>"test-results\voice-check.txt" 2>&1
  if errorlevel 1 goto failed
)
echo VOICE CHECKS PASSED. Open test-results\voice-samples and play the WAVs.
set "result=0"
goto finished
:failed
echo Voice check failed. Read test-results\voice-check.txt and the companion window.
set "result=1"
:finished
popd
if not "%BREEZE_PNY_SMOKE_NONINTERACTIVE%"=="1" pause
exit /b %result%
