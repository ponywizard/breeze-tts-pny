@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
echo Checking the SSH-forwarded LLM and STT. Keep the tunnel window open.
"python\python.exe" -X utf8 -c "import json,urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); r=json.load(o.open('http://127.0.0.1:18791/health',timeout=5)); print('LLM:',r.get('status')); assert r.get('status')=='ok'"
if errorlevel 1 goto failed
"python\python.exe" -X utf8 -c "import json,urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); r=json.load(o.open('http://127.0.0.1:18790/health',timeout=5)); print('STT:',r.get('ready')); assert r.get('ready') is True"
if errorlevel 1 goto failed
echo LAB CHECKS PASSED.
set "result=0"
goto finished
:failed
echo Lab check failed. Read the tunnel window and check that the lab is running.
set "result=1"
:finished
popd
if not "%BREEZE_PNY_SMOKE_NONINTERACTIVE%"=="1" pause
exit /b %result%
