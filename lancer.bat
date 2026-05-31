@echo off
chcp 65001 >nul
title Image Comparator Pro
cd /d "%~dp0"
python app.py
if errorlevel 1 (
    echo.
    echo Une erreur s'est produite. Verifiez que les dependances sont installees :
    echo    pip install -r requirements.txt
    pause
)
