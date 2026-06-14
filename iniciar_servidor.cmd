@echo off
title MangaWiki Personal - Servidor Local
echo ==============================================
echo        INICIANDO MANGAWIKI PERSONAL
echo ==============================================
echo.
echo 1. Verificando e instalando dependencias (requirements.txt)...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Hubo un problema al instalar las dependencias de Python.
    pause
    exit /b %errorlevel%
)
echo.
echo 2. Iniciando servidor Flask...
echo Abre tu navegador en: http://localhost:5000
echo.
python app.py
pause
