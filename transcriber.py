"""
Transcribe Audio - Transcription Module
Uses OpenAI Whisper for local transcription
"""
import whisper
import torch
from pathlib import Path

# Model selection
DEFAULT_MODEL = "base"


def is_cuda_available():
    """Check if CUDA (GPU) is available."""
    return torch.cuda.is_available()


def get_device():
    """Get the best available device."""
    return "cuda" if is_cuda_available() else "cpu"


# Cache model globally
_model = None


def load_model(model_name: str = DEFAULT_MODEL):
    """Load Whisper model."""
    global _model
    
    if _model is not None:
        return _model
    
    device = get_device()
    print(f"Loading Whisper model '{model_name}' on {device}...")
    
    _model = whisper.load_model(model_name, device=device)
    print(f"Whisper model loaded")
    
    return _model


def transcribe(audio_path: str, model_name: str = DEFAULT_MODEL) -> dict:
    """
    Transcribe audio file to text.
    
    Args:
        audio_path: Path to WAV audio file
        model_name: Whisper model (tiny, base, small, medium, large, turbo)
    
    Returns:
        dict with text, language, duration
    """
    model = load_model(model_name)
    
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    print(f"Transcribing: {audio_path}")
    
    options = {
        "fp16": is_cuda_available(),
        "verbose": False,
    }
    
    result = model.transcribe(str(audio_path), **options)
    
    return {
        "text": result["text"].strip(),
        "language": result.get("language", "en"),
        "duration": result.get("duration", 0),
        "segments": result.get("segments", [])
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python transcriber.py <audio_file> [model]")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    
    print(f"Device: {get_device()}")
    result = transcribe(audio_file, model)
    print(f"\n--- Transcript ({result['duration']:.1f}s, lang={result['language']}) ---")
    print(result["text"])
