@echo off
setlocal
rem Validate Python before launching; do not trigger automatic installation.
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto launch_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto launch_python
echo Python 3.10 or newer is required. Install Python from https://www.python.org/downloads/ then launch again.
pause
exit /b 1
:launch_py
py -3 "%~dp0launch_coop.py" %*
goto finished
:launch_python
python "%~dp0launch_coop.py" %*
:finished
set "launcher_status=%errorlevel%"
if not "%launcher_status%"=="0" pause
exit /b %launcher_status%
