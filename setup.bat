@echo off
echo === AIBull Setup ===

REM Create virtual environment
python -m venv .venv
call .venv\Scripts\activate.bat

REM Install Python dependencies
pip install -r requirements.txt

REM Copy env file if not exists
if not exist .env (
    copy .env.example .env
    echo Created .env — please fill in your API keys
)

REM Install Node deps and build frontend
cd frontend
call npm install
call npm run build
cd ..

echo.
echo === Setup complete! ===
echo Run:  python desktop.py
echo Or for dev:  start_dev.bat
pause
