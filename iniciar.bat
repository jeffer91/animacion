@echo off
REM Abre Animación en Windows. La primera vez crea el entorno e instala las dependencias.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Preparando el entorno por primera vez, esto tarda unos minutos...
    py -3 -m venv .venv || python -m venv .venv
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)
python app.py %*
if errorlevel 1 pause
