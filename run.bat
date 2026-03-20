@echo off
chcp 65001 >nul
title Transcribe Audio

echo ================================================
echo Transcribe Audio - Meeting Summarizer
echo ================================================
echo.

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Add local folder to PATH for FFmpeg
set PATH=%SCRIPT_DIR%;%PATH%

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install --quiet sounddevice numpy openai-whisper fastapi uvicorn python-multipart websockets pydantic PyAudioWPatch

REM Check PortAudio
echo Checking PortAudio...
python -c "import sounddevice" 2>nul
if errorlevel 1 (
    echo Note: If audio fails, copy portaudio.dll to the app folder
) else (
    echo PortAudio OK
)

REM Check FFmpeg
echo Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo WARNING: FFmpeg not found!
) else (
    echo FFmpeg OK
)

REM Check Ollama
echo Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo WARNING: Ollama is not running. Start with: ollama serve
) else (
    echo Ollama is running!
)

REM Check CUDA
python -c "import torch; print('CUDA:', 'Available' if torch.cuda.is_available() else 'Using CPU')" 2>nul

echo.
echo ================================================
echo Starting server...
echo ================================================
echo.
echo Web UI: http://localhost:8765
echo Press Ctrl+C to stop
echo.

python main.py

pause
