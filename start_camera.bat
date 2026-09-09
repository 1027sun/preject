@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    call setup_camera.bat
    if errorlevel 1 exit /b 1
)
if not exist "models\pose_landmarker_lite.task" (
    call setup_camera.bat
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -X utf8 camera_demo.py %*
if errorlevel 1 pause
