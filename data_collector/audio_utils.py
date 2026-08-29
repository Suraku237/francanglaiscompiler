"""
Audio recording, saving and playback helpers.
Recording needs sounddevice/soundfile (PortAudio backend); if those
aren't available, recording is disabled but playback/attach still work
via the OS's default player as a fallback.
"""

import os
import uuid
import shutil
import subprocess

try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    AUDIO_RECORDING_AVAILABLE = True
except Exception:
    AUDIO_RECORDING_AVAILABLE = False

SAMPLE_RATE = 44100


class Recorder:
    """Minimal start/stop mic recorder."""

    def __init__(self):
        self.frames = []
        self.stream = None
        self.recording = False

    def start(self):
        self.frames = []
        self.recording = True

        def callback(indata, frames, time_info, status):
            if self.recording:
                self.frames.append(indata.copy())

        self.stream = sd.InputStream(  # type: ignore
            samplerate=SAMPLE_RATE, channels=1, callback=callback
        )
        self.stream.start()

    def stop(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if not self.frames:
            return None
        return np.concatenate(self.frames, axis=0)  # type: ignore


def save_recording(audio, audio_dir: str) -> str:
    """Writes the recorded audio to a .wav file, returns its filename."""
    filename = f"{uuid.uuid4().hex}.wav"
    path = os.path.join(audio_dir, filename)
    sf.write(path, audio, SAMPLE_RATE)  # type: ignore
    return filename


def attach_file(source_path: str, audio_dir: str) -> str:
    """Copies an existing audio file into audio_dir, returns its filename."""
    filename = f"{uuid.uuid4().hex}{os.path.splitext(source_path)[1]}"
    dest = os.path.join(audio_dir, filename)
    shutil.copy2(source_path, dest)
    return filename


def play_audio(path: str) -> bool:
    """Best-effort playback: sounddevice if available, else OS default app."""
    if not os.path.exists(path):
        return False

    if AUDIO_RECORDING_AVAILABLE:
        try:
            data, sr = sf.read(path, dtype="float32")  # type: ignore
            sd.play(data, sr)  # type: ignore
            return True
        except Exception:
            pass  # fall through to OS-level fallback

    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False