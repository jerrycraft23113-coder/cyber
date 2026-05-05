@echo off
set "LOG=C:\neutral_zone\sandbox_smoke.log"
set "PYEXE=C:\vanguard_duel\host\python310\python.exe"

echo [%DATE% %TIME%] sandbox started > "%LOG%"

if exist "%PYEXE%" (
    echo [%DATE% %TIME%] python found: %PYEXE% >> "%LOG%"
    "%PYEXE%" --version >> "%LOG%" 2>&1
    echo [%DATE% %TIME%] launching watchdog >> "%LOG%"
    "%PYEXE%" C:\vanguard_duel\sandbox\watchdog.py
) else (
    echo [%DATE% %TIME%] ERROR: python.exe not found at %PYEXE% >> "%LOG%"
)
