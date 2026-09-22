"""Offline speech-to-text via Vosk."""

import json
import os
import queue
import sys
import threading
from typing import Callable, Optional


class SpeechService:
    def __init__(self, model_path: str = ""):
        self._model_path = model_path or os.environ.get("VOSK_MODEL_PATH", "")
        self._model = None
        self._rec = None
        self._audio_q: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def is_available(self) -> bool:
        try:
            import vosk

            return True
        except ImportError:
            return False

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if not self.is_available():
            return False
        if not self._model_path or not os.path.isdir(self._model_path):
            return False
        try:
            import vosk

            self._model = vosk.Model(self._model_path)
            return True
        except Exception:
            return False

    def transcribe_file(self, audio_path: str) -> str:
        if not self._ensure_model():
            return ""
        try:
            import vosk

            rec = vosk.KaldiRecognizer(self._model, 16000)
            with open(audio_path, "rb") as f:
                while True:
                    data = f.read(4000)
                    if not data:
                        break
                    rec.AcceptWaveform(data)
            result = json.loads(rec.FinalResult())
            return result.get("text", "")
        except Exception:
            return ""

    def start_listening(self, callback: Callable[[str], None]) -> None:
        if self._running:
            return
        if not self._ensure_model():
            return
        try:
            import vosk
            import pyaudio

            self._rec = vosk.KaldiRecognizer(self._model, 16000)
            self._audio_q = queue.Queue()
            self._running = True

            def _audio_thread():
                p = pyaudio.PyAudio()
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=4000,
                )
                stream.start_stream()
                try:
                    while self._running:
                        data = stream.read(4000, exception_on_overflow=False)
                        if self._rec.AcceptWaveform(data):
                            result = json.loads(self._rec.Result())
                            text = result.get("text", "")
                            if text:
                                callback(text)
                finally:
                    stream.stop_stream()
                    stream.close()
                    p.terminate()
                    self._running = False

            self._thread = threading.Thread(target=_audio_thread, daemon=True)
            self._thread.start()
        except ImportError:
            pass

    def stop_listening(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
