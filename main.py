"""
Transcribe Audio - FastAPI Server
Windows-native meeting transcription and summarization
"""
import os
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import modules
from recorder import (
    start_recording_threaded, stop_recording, is_recording,
    get_recording_status, list_input_devices, list_output_devices
)
from transcriber import transcribe
from summarizer import summarize, is_ollama_available, list_ollama_models

# ============================================================================
# Configuration
# ============================================================================

# Base directory - this script's location
BASE_DIR = Path(__file__).parent
APP_DIR = BASE_DIR
MEETINGS_DIR = APP_DIR / "meetings"
MEETINGS_DIR.mkdir(parents=True, exist_ok=True)

STORAGE_DIR = MEETINGS_DIR

app = FastAPI(title="Transcribe Audio", version="1.0.0")

# CORS - allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connections
ws_connections: List[WebSocket] = []

# ============================================================================
# WebSocket
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_connections.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        if ws in ws_connections:
            ws_connections.remove(ws)


async def broadcast(message: dict):
    """Broadcast to all WebSocket clients."""
    for ws in ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            pass


# ============================================================================
# Models
# ============================================================================

class StartRecordingResponse(BaseModel):
    status: str
    session_id: str

class StartRecordingRequest(BaseModel):
    mic_index: Optional[int] = None
    system_index: Optional[int] = None

class StopRecordingResponse(BaseModel):
    status: str
    session_id: str
    audio_path: str
    duration_seconds: float

class TranscribeRequest(BaseModel):
    audio_path: str

class SummarizeRequest(BaseModel):
    transcript: str
    model: Optional[str] = None

class ProcessMeetingRequest(BaseModel):
    audio_path: str
    model: Optional[str] = None

class ProcessMeetingBase64Request(BaseModel):
    audio_base64: str
    model: Optional[str] = None

class MeetingModel(BaseModel):
    id: str
    created_at: str
    audio_path: str
    duration_seconds: float
    transcript: Optional[str] = None
    summary: Optional[dict] = None

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def get_index():
    """Serve the web UI."""
    index_path = BASE_DIR / "frontend" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(status_code=404, detail="Web UI not found")


@app.get("/api/status")
async def get_status():
    """Get system status."""
    return {
        "ollama_available": is_ollama_available(),
        "recording": is_recording(),
        "recording_status": get_recording_status(),
        "ollama_models": list_ollama_models() if is_ollama_available() else [],
        "storage_dir": str(STORAGE_DIR)
    }


@app.get("/api/devices")
async def get_devices():
    """List available audio devices."""
    try:
        input_devices = list_input_devices()
        output_devices = list_output_devices()
        return {
            "input_devices": input_devices,
            "output_devices": output_devices
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/record/start")
async def api_start_recording(request: StartRecordingRequest = None):
    """Start audio recording."""
    if is_recording():
        raise HTTPException(status_code=400, detail="Already recording")
    
    try:
        mic_index = request.mic_index if request else None
        system_index = request.system_index if request else None
        session_id = start_recording_threaded(mic_index=mic_index, system_index=system_index)
        await broadcast({"type": "status", "status": "recording", "session_id": session_id})
        return {"status": "recording", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/record/stop")
async def api_stop_recording():
    """Stop audio recording."""
    if not is_recording():
        raise HTTPException(status_code=400, detail="Not recording")
    
    try:
        result = stop_recording()
        await broadcast({"type": "status", "status": "stopped", **result})
        return {"status": "stopped", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/transcribe")
async def api_transcribe(request: TranscribeRequest):
    """Transcribe audio file."""
    if not Path(request.audio_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    try:
        await broadcast({"type": "status", "status": "transcribing"})
        result = transcribe(request.audio_path, model_name=request.model or "base")
        await broadcast({"type": "transcription_done", "transcript": result["text"]})
        return {
            "status": "done",
            "transcript": result["text"],
            "language": result["language"],
            "duration": result["duration"]
        }
    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/summarize")
async def api_summarize(request: SummarizeRequest):
    """Summarize transcript."""
    if not request.transcript:
        raise HTTPException(status_code=400, detail="Empty transcript")
    
    try:
        await broadcast({"type": "status", "status": "summarizing"})
        result = summarize(request.transcript, model=request.model)
        await broadcast({"type": "summary_done", "summary": result})
        return result
    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/meeting/process")
async def api_process_meeting(request: ProcessMeetingRequest):
    """Complete pipeline: transcribe + summarize + save."""
    audio_file = Path(request.audio_path)
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    meeting_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().isoformat()
    
    try:
        # Step 1: Transcribe
        await broadcast({"type": "status", "status": "transcribing"})
        try:
            transcript_result = transcribe(str(audio_file), model_name=request.model or "base")
        except Exception as e:
            print(f"Transcription error: {e}")
            raise
        transcript = transcript_result["text"]
        await broadcast({"type": "transcription_done", "transcript": transcript, "progress": 50})
        
        # Step 2: Summarize
        await broadcast({"type": "status", "status": "summarizing"})
        try:
            summary_result = summarize(transcript)
        except Exception as e:
            print(f"Summarization error: {e}")
            raise
        await broadcast({"type": "summary_done", "summary": summary_result, "progress": 100})
        
        # Step 3: Save meeting
        meeting = {
            "id": meeting_id,
            "created_at": created_at,
            "audio_path": str(audio_file),
            "duration_seconds": transcript_result.get("duration", 0),
            "transcript": transcript,
            "summary": summary_result
        }
        
        meeting_path = STORAGE_DIR / f"{meeting_id}.json"
        meeting_path.write_text(json.dumps(meeting, indent=2), encoding='utf-8')
        
        await broadcast({"type": "meeting_saved", "meeting_id": meeting_id})
        
        return meeting
        
    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/meeting/process-base64")
async def api_process_meeting_base64(request: ProcessMeetingBase64Request):
    """Process meeting from base64-encoded audio (from browser MediaRecorder)."""
    import base64
    
    meeting_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().isoformat()
    
    try:
        audio_data = base64.b64decode(request.audio_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {e}")
    
    audio_path = BASE_DIR / "temp" / f"meeting_{meeting_id}.webm"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(audio_data)
    
    try:
        # Step 1: Transcribe
        await broadcast({"type": "status", "status": "transcribing"})
        transcript_result = transcribe(str(audio_path), model_name=request.model or "base")
        transcript = transcript_result["text"]
        await broadcast({"type": "transcription_done", "transcript": transcript, "progress": 50})
        
        # Step 2: Summarize
        await broadcast({"type": "status", "status": "summarizing"})
        summary_result = summarize(transcript)
        await broadcast({"type": "summary_done", "summary": summary_result, "progress": 100})
        
        # Step 3: Save meeting
        meeting = {
            "id": meeting_id,
            "created_at": created_at,
            "audio_path": str(audio_path),
            "duration_seconds": transcript_result.get("duration", 0),
            "transcript": transcript,
            "summary": summary_result
        }
        
        meeting_path = STORAGE_DIR / f"{meeting_id}.json"
        meeting_path.write_text(json.dumps(meeting, indent=2), encoding='utf-8')
        
        await broadcast({"type": "meeting_saved", "meeting_id": meeting_id})
        
        return meeting
        
    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
        if audio_path.exists():
            audio_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/meetings")
async def get_meetings():
    """List all saved meetings."""
    meetings = []
    
    for file in sorted(STORAGE_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(file.read_text(encoding='utf-8'))
            # Remove transcript for list view
            data_no_transcript = {k: v for k, v in data.items() if k != "transcript"}
            meetings.append(data_no_transcript)
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    return {"meetings": meetings}


@app.get("/api/meeting/{meeting_id}")
async def get_meeting(meeting_id: str):
    """Get a specific meeting."""
    meeting_path = STORAGE_DIR / f"{meeting_id}.json"
    
    if not meeting_path.exists():
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    try:
        return json.loads(meeting_path.read_text(encoding='utf-8'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/meeting/{meeting_id}")
async def delete_meeting(meeting_id: str):
    """Delete a meeting."""
    meeting_path = STORAGE_DIR / f"{meeting_id}.json"
    
    if not meeting_path.exists():
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    try:
        meeting_path.unlink()
        return {"status": "deleted", "meeting_id": meeting_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 50)
    print("Transcribe Audio - Meeting Summarizer")
    print("=" * 50)
    print(f"Storage: {STORAGE_DIR}")
    print(f"Ollama: {'Available' if is_ollama_available() else 'Not available'}")
    print()
    print("Web UI: http://localhost:8765")
    print("API: http://localhost:8765/api")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=8765)
