@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "import gmsh,PIL,openpyxl" >nul 2>&1
if errorlevel 1 (
  echo Установка Pillow, gmsh и openpyxl...
  python -m pip install -r requirements.txt
)
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw aura_plm.py
  exit /b 0
)
python aura_plm.py
if errorlevel 1 pause
