@echo off
rem One-time setup on Windows: installs the Python packages WordMine needs and checks the rest.
cd /d "%~dp0"
set PY=
for %%v in (3.14 3.13 3.12 3.11 3.10 3.9) do (
  if not defined PY py -%%v -c "print()" >nul 2>nul && set PY=py -%%v
)
if not defined PY (
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 15) else 1)" >nul 2>nul && (
    echo Your Python is 3.15 or newer. One of the Japanese libraries has no build for it yet.
    echo Please install Python 3.14 from https://www.python.org/downloads/ ^(tick "Add Python to PATH"^) and run this again.
    pause
    exit /b 1
  )
  python --version >nul 2>nul && set PY=python
)
if not defined PY (
  echo Python was not found. Install Python 3.14 from https://www.python.org/downloads/ and tick "Add Python to PATH", then run this again.
  pause
  exit /b 1
)
echo Using: %PY%
%PY% -m pip install --upgrade pip >nul
%PY% -m pip install -r requirements.txt || (echo. & echo pip failed - see the messages above. & pause & exit /b 1)
echo.
echo Checking the rest of the setup (Tesseract, Anki, ...):
echo.
%PY% -m wordmine check
echo.
echo Downloading the offline Japanese dictionary (JMdict, about 12 MB) so meanings work without internet...
%PY% -m wordmine dictionary || echo (Skipped: no internet right now. You can do this later from Settings in WordMine.)
echo.
echo If everything above says OK, double-click WordMine.bat to start.
echo FAIL lines tell you what to install; see README.md for the links.
pause
