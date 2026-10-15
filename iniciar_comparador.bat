@echo off
title JAEN AI: COMPARADOR ADMINISTRATIVO

:: Cambiar al directorio del script
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [*] Primera ejecucion: Instalando componentes de IA...
    py -3.12 -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

:: Abrir navegador inmediatamente
start http://127.0.0.1:8000

:: Iniciar FastAPI (la ventana de CMD se mantendra abierta en segundo plano procesando peticiones)
python -m uvicorn app:app --host 127.0.0.1 --port 8000