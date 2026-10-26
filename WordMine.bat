@echo off
rem Double-click to start WordMine. Run setup.bat once first.
cd /d "%~dp0"
set PY=
for %%v in (3.14 3.13 3.12 3.11 3.10 3.9) do (
  if not defined PY py -%%v -c "print()" >nul 2>nul && set PY=py -%%v
)
if not defined PY set PY=python
%PY% -m wordmine %*
if errorlevel 1 (
  echo.
  echo WordMine stopped with an error. If this is the first run, double-click setup.bat first.
  pause
)
