# Record-transcribe-and-summarize
# 🎙️ Transcribe Audio

**Local-first meeting transcription & AI summarization for Windows.**

Record your meetings, get a full transcript and structured AI summary — all running locally, no cloud, no data ever leaves your machine.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/whisper-local_AI-green?logo=openai&logoColor=white" alt="Whisper">
  <img src="https://img.shields.io/badge/ollama-LLM-orange" alt="Ollama">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
</p>

---

## ✨ Features

- 🎤 **Mic + System Audio** — Capture your microphone and desktop audio simultaneously (WASAPI loopback)
- 📝 **AI Transcription** — OpenAI Whisper runs 100% locally (GPU accelerated if available)
- 🤖 **Smart Summaries** — Ollama LLM extracts key points, action items, and open questions
- 📊 **Meeting History** — All meetings saved locally as JSON with full search
- 🌐 **Web UI** — Clean, dark-themed browser interface
- 🔒 **Privacy First** — Everything runs on your machine. Zero cloud dependencies.

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│  Microphone (sounddevice)                            │
│  System Audio (PyAudioWPatch / WASAPI loopback)      │
│       │                                              │
│       ▼                                              │
│  Whisper (local) ── transcribes audio → text         │
│       │                                              │
│       ▼                                              │
│  Ollama LLM ── summarizes → structured JSON          │
│       │                                              │
│       ▼                                              │
│  FastAPI + Web UI ── serves results on localhost      │
└──────────────────────────────────────────────────────┘
```

## 📦 Prerequisites

| Requirement | Purpose | Link |
|-------------|---------|------|
| **Python 3.10+** | Runtime | [python.org/downloads](https://www.python.org/downloads/) |
| **Ollama** | AI summarization | [ollama.com/download](https://ollama.com/download) |
| **FFmpeg** | Audio decoding for Whisper | [ffmpeg.org](https://ffmpeg.org/download.html) |

> **Note:** Check "Add Python to PATH" during Python installation.

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/philp97/transcribe-audio.git
cd transcribe-audio
```

### 2. Download FFmpeg

Place `ffmpeg.exe` and `ffprobe.exe` in the project root. You can download a static build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).

### 3. Start Ollama

```bash
ollama pull qwen3.5:9b
ollama serve
```

### 4. Run the app

**Option A: One-click (Windows)**
```
Double-click run.bat
```

**Option B: Manual**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 5. Open the UI

Navigate to **[http://localhost:8765](http://localhost:8765)** in your browser.

## 🎧 System Audio Setup

To record audio from applications (Zoom, Teams, YouTube, etc.), the app uses **WASAPI loopback** via [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch). Your speakers/headphones will appear as loopback devices in the System Audio dropdown.

> Just select your output device from "System Audio" — no extra software required.

## 📁 Project Structure

```
transcribe-audio/
├── main.py              # FastAPI server & API endpoints
├── recorder.py          # Audio recording (mic + WASAPI loopback)
├── transcriber.py       # Whisper transcription
├── summarizer.py        # Ollama LLM summarization
├── frontend/
│   └── index.html       # Web UI (single-page app)
├── requirements.txt     # Python dependencies
├── run.bat              # Windows one-click launcher
├── SPEC.md              # Technical specification
├── meetings/            # Saved meetings (auto-created)
├── temp/                # Temp audio files (auto-created)
└── .gitignore
```

## 🔌 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | `GET` | Web UI |
| `/api/status` | `GET` | System status (Ollama, recording state) |
| `/api/devices` | `GET` | List audio devices |
| `/api/record/start` | `POST` | Start recording |
| `/api/record/stop` | `POST` | Stop recording |
| `/api/transcribe` | `POST` | Transcribe an audio file |
| `/api/summarize` | `POST` | Summarize a transcript |
| `/api/meeting/process` | `POST` | Full pipeline: record → transcribe → summarize → save |
| `/api/meetings` | `GET` | List all saved meetings |
| `/api/meeting/{id}` | `GET` | Get a specific meeting |
| `/api/meeting/{id}` | `DELETE` | Delete a meeting |
| `/ws` | `WebSocket` | Real-time status updates |

## ⚡ GPU Acceleration

Whisper supports CUDA GPU acceleration. If transcription is slow:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

The app auto-detects CUDA. Check with:
```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| `Failed to import sounddevice` | Install PortAudio — see [PortAudio docs](https://www.portaudio.com/download.html) |
| `Ollama not available` | Run `ollama serve` in a terminal |
| Slow transcription | First run downloads the Whisper model (~140MB). Use GPU for speed. |
| No audio devices | Check mic permissions in Windows Settings |
| No system audio devices | Ensure `PyAudioWPatch` is installed: `pip install PyAudioWPatch` |

## 🔧 Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API URL (env var) |
| Whisper model | `base` | Options: `tiny`, `base`, `small`, `medium`, `large`, `turbo` |
| Server port | `8765` | Set in `main.py` |

## 📄 License

[MIT](LICENSE)
