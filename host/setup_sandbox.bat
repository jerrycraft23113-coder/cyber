@echo off
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
"%PYEXE%" C:\vanguard_duel\sandbox\watchdog.py
