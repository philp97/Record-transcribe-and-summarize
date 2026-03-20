"""
Transcribe Audio - Windows Audio Recording Module
Uses sounddevice for mic capture and PyAudioWPatch for system audio (WASAPI loopback)
"""
import sounddevice as sd
import numpy as np
import wave
import uuid
import threading
import time
from pathlib import Path

# Try to import PyAudioWPatch for WASAPI loopback
try:
    import pyaudiowpatch as pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    print("Warning: PyAudioWPatch not installed. System audio capture unavailable.")
    print("  Install with: pip install PyAudioWPatch")

# Storage paths
APP_DIR = Path(__file__).parent
TMP_DIR = APP_DIR / "temp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'float32'

# Global recording state
_recording = False
_recording_session_id = None
_recording_start_time = None
_recording_thread = None
_system_thread = None
_mic_data = []
_system_data = []
_recording_lock = threading.Lock()
_mic_stream = None
_system_sample_rate = None


def list_devices():
    """List all available audio devices."""
    try:
        devices = sd.query_devices()
        if isinstance(devices, dict):
            return [devices]
        return list(devices)
    except Exception as e:
        print(f"Error listing devices: {e}")
        return []


def list_input_devices():
    """List all input devices with their indices."""
    try:
        devices = sd.query_devices()
        input_devices = []
        
        if isinstance(devices, dict):
            if devices.get('max_input_channels', 0) > 0:
                return [{
                    'index': devices.get('index', 0),
                    'name': devices.get('name', 'Default Input'),
                    'channels': devices.get('max_input_channels', 1),
                    'sample_rate': devices.get('default_samplerate', 44100),
                    'hostapi': devices.get('hostapi', 0)
                }]
            return []
        
        for i, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                input_devices.append({
                    'index': i,
                    'name': dev.get('name', f'Device {i}'),
                    'channels': dev.get('max_input_channels', 1),
                    'sample_rate': dev.get('default_samplerate', 44100),
                    'hostapi': dev.get('hostapi', 0)
                })
        
        return input_devices
    except Exception as e:
        print(f"Error listing input devices: {e}")
        return []


def list_output_devices():
    """List WASAPI loopback devices for system audio capture using PyAudioWPatch."""
    if not HAS_PYAUDIO:
        return []
    
    try:
        p = pyaudio.PyAudio()
        loopback_devices = []
        
        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            print("Warning: WASAPI host API not available")
            p.terminate()
            return []
        
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            # PyAudioWPatch marks loopback devices with isLoopbackDevice flag
            if dev.get("isLoopbackDevice", False):
                loopback_devices.append({
                    'index': dev['index'],
                    'name': dev['name'],
                    'channels': dev['maxInputChannels'],
                    'sample_rate': int(dev['defaultSampleRate']),
                    'hostapi': dev.get('hostApi', 0)
                })
        
        p.terminate()
        
        if loopback_devices:
            print(f"Found {len(loopback_devices)} WASAPI loopback device(s)")
        else:
            print("Warning: No WASAPI loopback devices found")
        
        return loopback_devices
    except Exception as e:
        print(f"Error listing loopback devices: {e}")
        return []


def _resample(audio, src_rate, dst_rate):
    """Resample audio from src_rate to dst_rate using linear interpolation."""
    if src_rate == dst_rate:
        return audio
    duration = len(audio) / src_rate
    new_length = int(duration * dst_rate)
    if new_length == 0:
        return np.array([], dtype=audio.dtype)
    old_indices = np.linspace(0, len(audio) - 1, new_length)
    return np.interp(old_indices, np.arange(len(audio)), audio.astype(np.float64)).astype(audio.dtype)


def _mic_callback(indata, frames, time_info, status):
    """Callback for microphone audio."""
    if status:
        print(f"Mic status: {status}")
    with _recording_lock:
        if _recording:
            audio_int16 = (indata.flatten() * 32767).astype(np.int16)
            _mic_data.append(audio_int16.copy())


def _record_system_audio(device_index, sample_rate, channels):
    """Record system audio using PyAudioWPatch WASAPI loopback (runs in thread)."""
    global _system_data, _system_sample_rate
    
    if not HAS_PYAUDIO:
        return
    
    _system_sample_rate = sample_rate
    p = pyaudio.PyAudio()
    
    try:
        stream = p.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=sample_rate,
            frames_per_buffer=1024,
            input=True,
            input_device_index=device_index
        )
        
        print(f"System loopback stream opened: device={device_index}, {sample_rate}Hz, {channels}ch")
        
        while _recording:
            try:
                data = stream.read(1024, exception_on_overflow=False)
                audio = np.frombuffer(data, dtype=np.float32)
                
                # Downmix to mono if multi-channel
                if channels > 1:
                    audio = audio.reshape(-1, channels).mean(axis=1)
                
                audio_int16 = (audio * 32767).astype(np.int16)
                
                with _recording_lock:
                    _system_data.append(audio_int16.copy())
            except Exception as e:
                print(f"System audio read error: {e}")
                break
        
        stream.stop_stream()
        stream.close()
        print("System loopback stream closed")
    except Exception as e:
        print(f"System audio error: {e}")
    finally:
        p.terminate()


def start_recording(mic_index: int = None, system_index: int = None, session_id: str = None) -> str:
    """
    Start recording audio from mic and/or system.
    
    Args:
        mic_index: Microphone device index (None = default, for sounddevice)
        system_index: System audio device index (None = don't record system audio, for PyAudioWPatch)
        session_id: Optional pre-generated session ID
    
    Returns:
        session_id: The recording session ID
    """
    global _recording, _recording_session_id, _recording_start_time
    global _mic_data, _system_data, _mic_stream, _system_thread
    global _system_sample_rate
    
    if _recording:
        raise RuntimeError("Already recording")
    
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    # Clear previous audio
    _mic_data = []
    _system_data = []
    _system_sample_rate = None
    
    # Get default mic if not specified
    if mic_index is None:
        try:
            default_input = sd.query_devices(kind='input')
            mic_index = default_input.get('index', None)
            print(f"Using default mic: {default_input.get('name', 'Unknown')}")
        except Exception as e:
            print(f"Could not get default mic: {e}")
    
    _recording = True
    _recording_session_id = session_id
    _recording_start_time = time.time()
    
    streams = []
    
    # Start mic stream (sounddevice)
    if mic_index is not None:
        print(f"Starting mic recording: device={mic_index}")
        try:
            _mic_stream = sd.InputStream(
                device=mic_index,
                channels=CHANNELS,
                samplerate=SAMPLE_RATE,
                dtype=DTYPE,
                callback=_mic_callback,
                blocksize=1024
            )
            _mic_stream.start()
            streams.append('mic')
        except Exception as e:
            print(f"Failed to start mic stream: {e}")
            _mic_stream = None
    
    # Start system audio stream (PyAudioWPatch WASAPI loopback)
    if system_index is not None and HAS_PYAUDIO:
        print(f"Starting system recording (WASAPI loopback): device={system_index}")
        try:
            # Get device info from PyAudioWPatch
            p = pyaudio.PyAudio()
            dev_info = p.get_device_info_by_index(system_index)
            system_rate = int(dev_info['defaultSampleRate'])
            system_channels = dev_info['maxInputChannels']
            p.terminate()
            
            print(f"  System device: {dev_info['name']} @ {system_rate}Hz, {system_channels}ch")
            
            # Run system recording in its own thread
            _system_thread = threading.Thread(
                target=_record_system_audio,
                args=(system_index, system_rate, system_channels),
                daemon=True
            )
            _system_thread.start()
            streams.append(f'system@{system_rate}Hz')
        except Exception as e:
            print(f"Failed to start system stream: {e}")
            _system_thread = None
    
    print(f"Recording started: {session_id} (streams: {', '.join(streams) or 'none'})")
    
    # Keep recording until stopped
    while _recording:
        time.sleep(0.1)
    
    return session_id


def start_recording_threaded(mic_index: int = None, system_index: int = None) -> str:
    """Start recording in background thread."""
    global _recording_thread, _recording_session_id
    
    if _recording:
        raise RuntimeError("Already recording")
    
    # Generate session ID before starting thread to avoid race condition
    session_id = str(uuid.uuid4())[:8]
    _recording_session_id = session_id
    
    def run():
        try:
            start_recording(mic_index, system_index, session_id=session_id)
        except Exception as e:
            print(f"Recording error: {e}")
    
    _recording_thread = threading.Thread(target=run, daemon=True)
    _recording_thread.start()
    
    # Wait briefly for thread to initialize streams
    time.sleep(0.3)
    
    return session_id


def stop_recording() -> dict:
    """Stop recording and save to WAV file."""
    global _recording, _recording_session_id, _recording_start_time
    global _mic_stream, _system_thread
    
    if not _recording:
        raise RuntimeError("Not recording")
    
    _recording = False
    
    # Stop mic stream
    if _mic_stream:
        try:
            _mic_stream.stop()
            _mic_stream.close()
            print("Stopped mic stream")
        except Exception as e:
            print(f"Error stopping mic stream: {e}")
    _mic_stream = None
    
    # Wait for system thread to finish
    if _system_thread:
        _system_thread.join(timeout=3)
        _system_thread = None
    
    if _recording_thread:
        _recording_thread.join(timeout=2)
    
    session_id = _recording_session_id
    duration = time.time() - _recording_start_time
    
    # Process audio
    mic_audio = None
    system_audio = None
    
    with _recording_lock:
        if _mic_data:
            mic_audio = np.concatenate(_mic_data, axis=0)
            print(f"  Mic audio: {len(mic_audio)} samples @ {SAMPLE_RATE}Hz")
        
        if _system_data:
            system_audio = np.concatenate(_system_data, axis=0)
            src_rate = _system_sample_rate or SAMPLE_RATE
            print(f"  System audio: {len(system_audio)} samples @ {src_rate}Hz")
            
            # Resample system audio to match mic sample rate if needed
            if src_rate != SAMPLE_RATE:
                system_audio = _resample(system_audio, src_rate, SAMPLE_RATE)
                print(f"  System audio resampled to: {len(system_audio)} samples @ {SAMPLE_RATE}Hz")
    
    # Mix mic and system audio by overlaying (not appending)
    audio_path = TMP_DIR / f"meeting_{session_id}.wav"
    
    if mic_audio is not None and system_audio is not None:
        # Overlay: pad the shorter one with zeros, then add
        max_len = max(len(mic_audio), len(system_audio))
        mic_padded = np.zeros(max_len, dtype=np.float64)
        sys_padded = np.zeros(max_len, dtype=np.float64)
        mic_padded[:len(mic_audio)] = mic_audio.astype(np.float64)
        sys_padded[:len(system_audio)] = system_audio.astype(np.float64)
        
        # Mix and clip to int16 range
        mixed = mic_padded + sys_padded
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
        audio_array = mixed
        print(f"  Mixed mic + system: {len(audio_array)} samples")
    elif mic_audio is not None:
        audio_array = mic_audio
    elif system_audio is not None:
        audio_array = system_audio
    else:
        audio_array = None
    
    if audio_array is not None:
        with wave.open(str(audio_path), 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_array.tobytes())
        
        print(f"Saved: {audio_path} ({duration:.1f}s, {len(audio_array)} samples)")
    else:
        with wave.open(str(audio_path), 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b'')
        print(f"Saved empty: {audio_path}")
    
    return {
        "session_id": session_id,
        "audio_path": str(audio_path),
        "duration_seconds": duration,
        "sample_rate": SAMPLE_RATE
    }


def is_recording() -> bool:
    """Check if currently recording."""
    return _recording


def get_recording_status() -> dict:
    """Get current recording status."""
    global _recording_start_time
    
    if not _recording:
        return {"recording": False}
    
    elapsed = time.time() - _recording_start_time if _recording_start_time else 0
    
    return {
        "recording": True,
        "session_id": _recording_session_id,
        "elapsed_seconds": elapsed
    }


if __name__ == "__main__":
    print("=" * 50)
    print("Transcribe Audio - Audio Recorder Test")
    print("=" * 50)
    
    print(f"\nPyAudioWPatch available: {HAS_PYAUDIO}")
    
    print("\nInput devices (microphones):")
    for dev in list_input_devices():
        print(f"  [{dev['index']}] {dev['name']}")
    
    print("\nOutput devices (WASAPI loopback):")
    for dev in list_output_devices():
        print(f"  [{dev['index']}] {dev['name']} @ {dev['sample_rate']}Hz, {dev['channels']}ch")
    
    print("\nStarting 5-second test recording...")
    try:
        sid = start_recording(mic_index=None)  # Use default mic
        print(f"Session ID: {sid}")
        print("Recording... (will stop in 5 seconds)")
        time.sleep(5)
        result = stop_recording()
        print(f"\nSaved to: {result['audio_path']}")
        print(f"Duration: {result['duration_seconds']:.1f}s")
    except Exception as e:
        print(f"\nError: {e}")
