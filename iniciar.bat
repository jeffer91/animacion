@echo off
REM Abre Animación en Windows. Crea el entorno si no existe e instala lo que falte.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creando el entorno por primera vez...
    py -3 -m venv .venv || python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -c "import PySide6, cv2, numpy, rembg, onnxruntime, imageio_ffmpeg" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias, esto tarda unos minutos...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
)
python app.py %*
if errorlevel 1 pause
