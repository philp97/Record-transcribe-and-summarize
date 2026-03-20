# Transcribe Audio - Specification

## Overview
Windows-native meeting transcription and summarization tool. Captures audio from microphone + system audio via WASAPI loopback, transcribes with Whisper, and summarizes with Ollama.

**Stack:** Python (Windows native) · FastAPI (web UI) · Whisper (transcription) · Ollama (summarization) · PyAudioWPatch (system audio)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Windows                                                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  sounddevice ─ captures microphone audio               │ │
│  │  PyAudioWPatch ─ WASAPI loopback (system audio)        │ │
│  └─────────────────────────┬──────────────────────────────┘ │
│                            │ WAV audio (mixed)               │
│                            ▼                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Whisper (local) - transcribes audio to text           │ │
│  └─────────────────────────┬──────────────────────────────┘ │
│                            │ transcript                      │
│                            ▼                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Ollama API - summarizes with LLM                      │ │
│  └─────────────────────────┬──────────────────────────────┘ │
│                            │ summary                         │
│                            ▼                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  FastAPI + Web UI - display results                    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Audio Capture

- **Microphone:** Uses `sounddevice` (PortAudio backend), 16kHz mono float32
- **System audio:** Uses `PyAudioWPatch` with WASAPI loopback — captures output device audio natively
- **Mixing:** Mic and system audio are overlaid (additive mix) and resampled to 16kHz mono
- **Output format:** 16kHz, mono, 16-bit PCM WAV

## Data Storage

- Meetings saved to: `./meetings/`
- Each meeting: JSON file with transcript + summary + metadata


## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/api/status` | GET | System status |
| `/api/devices` | GET | List audio devices |
| `/api/record/start` | POST | Start recording |
| `/api/record/stop` | POST | Stop recording |
| `/api/meeting/process` | POST | Full pipeline |
| `/api/meetings` | GET | List meetings |
| `/api/meeting/{id}` | GET | Get meeting |
| `/api/meeting/{id}` | DELETE | Delete meeting |

## Ollama Configuration

- Host: http://localhost:11434
- Default model: qwen3.5:9b
- System prompt for summarization extracts: summary, key_points, action_items, open_questions
