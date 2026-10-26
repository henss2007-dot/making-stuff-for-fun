@echo off
rem One-time setup on Windows: installs the Python packages WordMine needs and checks the rest.
cd /d "%~dp0"
where py >nul 2>nul && set PY=py -3
if not defined PY set PY=python
%PY% --version >nul 2>nul || (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add Python to PATH", then run this again.
  pause
  exit /b 1
)
echo Installing Python packages...
%PY% -m pip install --upgrade pip >nul
%PY% -m pip install -r requirements.txt || (echo. & echo pip failed - see the messages above. & pause & exit /b 1)
echo.
echo Checking the rest of the setup (Tesseract, Anki, ...):
echo.
%PY% -m wordmine check
echo.
echo If everything above says OK, double-click WordMine.bat to start.
echo FAIL lines tell you what to install; see README.md for the links.
pause
