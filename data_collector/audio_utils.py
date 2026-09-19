"""
Audio recording, saving and playback helpers.
Recording needs sounddevice/soundfile (PortAudio backend); if those
aren't available, recording is disabled but playback/attach still work
via the OS's default player as a fallback.
"""

import os
import math
import uuid
import shutil
import subprocess
import sys
from collections.abc import Callable

try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    AUDIO_RECORDING_AVAILABLE = True
except (ImportError, OSError):
    sd = sf = np = None
    AUDIO_RECORDING_AVAILABLE = False

SAMPLE_RATE = 44100

_BACKEND_ERRORS = (OSError, ValueError)
if sd is not None:
    _BACKEND_ERRORS += (sd.PortAudioError,)
if sf is not None:
    _BACKEND_ERRORS += (sf.SoundFileError,)


class AudioError(RuntimeError):
    """An expected device, codec, or audio-file failure the user can retry."""


class Recorder:
    """Retryable mic recorder; stop retains samples until start or close."""

    def __init__(self):
        self.frames = []
        self.stream = None
        self.recording = False
        self.sample_rate = SAMPLE_RATE
        self.warning = ""

    def start(self):
        """Start once; a failed start resets state and closes any opened stream."""
        if not AUDIO_RECORDING_AVAILABLE or sd is None:
            raise AudioError("Live recording is unavailable. Attach an audio file instead.")
        if self.recording or self.stream is not None:
            raise AudioError("Finish stopping the previous recording before starting another.")

        def callback(indata, _frames, _time_info, status):
            if self.recording:
                if status:
                    self.warning = f"Audio device reported {status}. The recording may be incomplete; listen before saving."
                self.frames.append(indata.copy())

        def finished():
            if self.recording:
                self.recording = False
                self.warning = "The microphone stopped unexpectedly. Review the captured audio for missing speech."

        previous_frames = self.frames
        previous_rate = self.sample_rate
        previous_warning = self.warning
        started = False
        try:
            self.stream = sd.InputStream(
                channels=1, callback=callback, finished_callback=finished,
            )
            rate = float(self.stream.samplerate)
            if not math.isfinite(rate) or rate <= 0:
                raise AudioError("The microphone returned an invalid sample rate.")
            self.sample_rate = int(round(rate))
            self.frames = []
            self.warning = ""
            self.recording = True
            self.stream.start()
            started = True
        except _BACKEND_ERRORS as error:
            raise AudioError(f"Could not start the microphone: {error}") from error
        finally:
            if not started:
                self.recording = False
                self.frames = previous_frames
                self.sample_rate = previous_rate
                self.warning = previous_warning
                self._close_stream()

    def stop(self):
        """Stop and return samples (or None); failures keep samples for a retry."""
        self.recording = False
        try:
            if self.stream is not None:
                self.stream.stop()
        except _BACKEND_ERRORS as error:
            raise AudioError(f"Could not stop the microphone: {error}") from error
        finally:
            self._close_stream()
        if not self.frames:
            return None
        if np is None:
            raise AudioError("The recording dependencies are unavailable.")
        try:
            return np.concatenate(self.frames, axis=0)
        except ValueError as error:
            raise AudioError(f"Could not assemble the recording: {error}") from error

    def _close_stream(self) -> None:
        self.recording = False
        if self.stream is not None:
            try:
                self.stream.close()
            except _BACKEND_ERRORS as error:
                # Retain the handle so stop/close can retry releasing the device.
                raise AudioError(f"Could not close the microphone: {error}") from error
            self.stream = None

    def close(self) -> None:
        """Release the mic and discard samples; safe to repeat after success."""
        self._close_stream()
        self.frames = []


def _store_audio(audio_dir: str, suffix: str, write: Callable[[str], object]) -> str:
    os.makedirs(audio_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    staging_path = os.path.join(audio_dir, f".{filename}")
    try:
        write(staging_path)
        os.replace(staging_path, os.path.join(audio_dir, filename))
    finally:
        try:
            os.remove(staging_path)
        except FileNotFoundError:
            pass
    return filename


def save_recording(audio, audio_dir: str, sample_rate: int = SAMPLE_RATE) -> str:
    """Atomically write a WAV; return its filename or raise AudioError."""
    if not AUDIO_RECORDING_AVAILABLE or sf is None:
        raise AudioError("The recording dependencies are unavailable.")
    if type(sample_rate) is not int or sample_rate <= 0:
        raise AudioError("A positive recording sample rate is required.")
    write = sf.write
    try:
        return _store_audio(audio_dir, ".wav", lambda path: write(path, audio, sample_rate))
    except _BACKEND_ERRORS as error:
        raise AudioError(f"Could not save the recording: {error}") from error


def attach_file(source_path: str, audio_dir: str) -> str:
    """Atomically copy an attachment, leaving its source untouched on failure."""
    try:
        return _store_audio(
            audio_dir, os.path.splitext(source_path)[1],
            lambda path: shutil.copy2(source_path, path),
        )
    except (OSError, ValueError) as error:
        raise AudioError(f"Could not attach this audio file: {error}") from error


def play_audio(path: str) -> bool:
    """Return whether playback started; expected backend errors try the OS player."""
    if not os.path.isfile(path):
        return False

    if AUDIO_RECORDING_AVAILABLE and sf is not None and sd is not None:
        try:
            data, sr = sf.read(path, dtype="float32")
            sd.play(data, sr)
            return True
        except _BACKEND_ERRORS:
            pass  # fall through to OS-level fallback

    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def stop_playback() -> None:
    """Release in-process playback; an external OS player owns its own lifetime."""
    if AUDIO_RECORDING_AVAILABLE and sd is not None:
        try:
            sd.stop()
        except _BACKEND_ERRORS as error:
            raise AudioError(f"Could not stop audio playback: {error}") from error