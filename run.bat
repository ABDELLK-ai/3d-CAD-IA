@echo off
echo =========================================
echo   3D CAD Studio - Installation + Run
echo =========================================
echo.

REM Create virtual environment if not exists
if not exist ".venv" (
    echo [1/4] Creation de l'environnement virtuel...
    python -m venv .venv
) else (
    echo [1/4] Environnement virtuel existant.
)

REM Activate venv
echo [2/4] Activation de l'environnement...
call .venv\Scripts\activate.bat

REM Install dependencies
echo [3/4] Installation des dependances...
pip install -r requirements.txt

REM Create .env from example if not exists
if not exist ".env" (
    echo [4/4] Creation du fichier .env...
    copy .env.example .env
    echo IMPORTANT: Editez le fichier .env et ajoutez votre cle API Gemini!
) else (
    echo [4/4] Fichier .env existant.
)

REM Launch FastApi Server + Three.js UI
echo.
echo ========================================================
echo   Lancement du serveur 3D CAD Studio (FastAPI + Three.js)
echo   Ouvrez http://localhost:8501 dans votre navigateur
echo ========================================================
echo.
python server.py
