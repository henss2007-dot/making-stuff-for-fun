@echo off
rem Double-click to start WordMine. Run setup.bat once first.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m wordmine %* & goto :done)
python -m wordmine %*
:done
if errorlevel 1 (
  echo.
  echo WordMine stopped with an error. If this is the first run, double-click setup.bat first.
  pause
)
