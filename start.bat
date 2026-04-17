@echo off
echo === EduBot - Iniciando con modelo LLM ===
call venv\Scripts\activate.bat
echo.
echo Instalando / verificando dependencias...
pip install -r requirements.txt
echo.
echo Cargando SmolLM2 y levantando servidor...
echo La primera vez puede tardar varios minutos descargando el modelo (~750 MB).
echo Abre http://127.0.0.1:5000 cuando aparezca el mensaje de Flask.
echo.
set EDUBOT_USE_LLM=1
python app.py
pause
