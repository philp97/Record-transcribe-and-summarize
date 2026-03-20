"""
Transcribe Audio - Summarization Module
Uses Ollama (local LLM) to summarize transcripts
"""
import json
import os
import urllib.request
import urllib.error

# Ollama configuration
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Preferred models in order
PREFERRED_MODELS = [
    "qwen3.5:9b",
    "qwen3.5:cloud",
    "glm-4.7-flash:latest",
    "minimax-m2.7:cloud",
]

SYSTEM_PROMPT = """You are a professional meeting notes analyst. Given a meeting transcript, provide a structured summary with:

1. **Summary**: Brief overview (2-4 sentences) of what was discussed
2. **Key Points**: Important decisions and focal points (list)
3. **Action Items**: Tasks assigned with who should do them (list of objects with task and assignee)
4. **Open Questions**: Unresolved items or questions left unanswered (list)

Return ONLY valid JSON with this exact structure:
{
    "summary": "...",
    "key_points": ["...", "..."],
    "action_items": [{"task": "...", "assignee": "..."}, ...],
    "open_questions": ["..."]
}

No text outside the JSON."""


def is_ollama_available() -> bool:
    """Check if Ollama is running."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except:
        return False


def list_ollama_models() -> list:
    """Get available Ollama models."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            return [m.get("name", "unknown") for m in data.get("models", [])]
    except:
        return []


def get_default_model() -> str:
    """Get the best available Ollama model."""
    models = list_ollama_models()
    
    if not models:
        return PREFERRED_MODELS[0]
    
    models_lower = [m.lower() for m in models]
    
    for pref in PREFERRED_MODELS:
        pref_lower = pref.lower()
        for i, model in enumerate(models_lower):
            if pref_lower in model or model in pref_lower:
                return models[i]
    
    return models[0] if models else PREFERRED_MODELS[0]


def _call_ollama(prompt: str, model: str) -> str:
    """Call Ollama API."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1024
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read())
        return result.get("response", "")


def summarize(transcript: str, model: str = None) -> dict:
    """
    Summarize a meeting transcript.
    
    Args:
        transcript: Meeting transcript text
        model: Ollama model name
    
    Returns:
        dict with summary, key_points, action_items, open_questions
    """
    if not model:
        model = get_default_model()
    
    print(f"Summarizing with: {model}")
    
    prompt = f"{SYSTEM_PROMPT}\n\nTRANSCRIPT:\n---\n{transcript}\n---"
    
    try:
        response = _call_ollama(prompt, model)
        
        # Clean response
        response = response.strip()
        
        # Remove markdown code blocks
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
        
        result = json.loads(response)
        
        # Validate
        required_keys = ["summary", "key_points", "action_items", "open_questions"]
        for key in required_keys:
            if key not in result:
                result[key] = []
        
        # Normalize action items
        for item in result.get("action_items", []):
            if isinstance(item, str):
                item["task"] = item
                item["assignee"] = None
            elif not isinstance(item, dict):
                item = {"task": str(item), "assignee": None}
            if "assignee" not in item:
                item["assignee"] = None
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Raw: {response[:500]}")
        return {
            "summary": "Error parsing summary.",
            "key_points": [],
            "action_items": [],
            "open_questions": []
        }
    except Exception as e:
        print(f"Summarization error: {e}")
        raise


if __name__ == "__main__":
    # Test
    if not is_ollama_available():
        print("Ollama not available")
        exit(1)
    
    models = list_ollama_models()
    print(f"Models: {models}")
    
    sample = """
    John: Hey team, let's start the sprint planning meeting.
    John: We need to finish the user authentication feature by next Friday.
    Sarah: I can work on the frontend part, that should take about 2 days.
    Mike: I'll handle the backend API, need to integrate with OAuth.
    John: Great. Sarah takes frontend, Mike takes backend. I'll do code review.
    Mike: We need staging credentials from DevOps.
    John: I'll email them today. Anything else?
    Sarah: Should we sync daily at 9am?
    John: Sure, let's do that.
    """
    
    result = summarize(sample)
    print(json.dumps(result, indent=2))
