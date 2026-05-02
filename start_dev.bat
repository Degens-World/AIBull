@echo off
echo === AIBull Dev Mode ===
call .venv\Scripts\activate.bat

REM Start backend
start "AIBull Backend" cmd /k "python -m uvicorn backend.main:app --host 127.0.0.1 --port 8421 --reload"

REM Start frontend dev server (with hot reload)
start "AIBull Frontend" cmd /k "cd frontend && npm run dev"

echo Backend: http://localhost:8421
echo Frontend (dev): http://localhost:5173
echo.
echo Open http://localhost:5173 in your browser for development
echo Or run python desktop.py after building frontend for the desktop app
