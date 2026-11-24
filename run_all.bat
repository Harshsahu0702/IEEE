@echo off
title OmniSense AI - Universal Monitoring Launcher
echo ===================================================
echo Starting OmniSense AI - Universal Platform
echo ===================================================

echo [1/4] Starting Standalone MQTT Broker...
start "OmniSense MQTT Broker" cmd /k "python backend/iot/run_broker.py"

timeout /t 2 /nobreak >nul

echo [2/4] Starting FastAPI Backend...
start "OmniSense Backend API" cmd /k "set PYTHONPATH=.&& set DEBUG=true&& python backend/main.py"

timeout /t 3 /nobreak >nul

echo [3/4] Starting React Frontend...
start "OmniSense Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 2 /nobreak >nul

echo [4/4] Starting Arduino Bridge (COM5)...
start "OmniSense Arduino Bridge" cmd /k "set PYTHONPATH=.&& python run_arduino_bridge.py"

echo ===================================================
echo All services launched!
echo Access Web Dashboard at: http://localhost:5173
echo API Docs at:             http://localhost:8000/docs
echo ===================================================
pause
