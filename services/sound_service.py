"""Sound effects for UI events."""

import os
import threading
from typing import Optional

_EVENT_FILES: dict = {}


def _sounds_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources",
        "sounds",
    )


def register_sound(event: str, wav_path: str) -> None:
    _EVENT_FILES[event] = wav_path


def _default_sounds() -> None:
    sd = _sounds_dir()
    _EVENT_FILES.update(
        {
            "notification": os.path.join(sd, "notification.wav"),
            "error": os.path.join(sd, "error.wav"),
            "success": os.path.join(sd, "success.wav"),
            "warning": os.path.join(sd, "warning.wav"),
            "click": os.path.join(sd, "click.wav"),
            "scan": os.path.join(sd, "scan.wav"),
            "complete": os.path.join(sd, "complete.wav"),
        }
    )


_default_sounds()


def play_sound(event: str) -> None:
    path = _EVENT_FILES.get(event, "")
    if not path or not os.path.exists(path):
        return
    threading.Thread(target=_play_wav, args=(path,), daemon=True).start()


def _play_wav(path: str) -> None:
    try:
        import winsound

        winsound.PlaySound(path, winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except ImportError:
        try:
            from PyQt5.QtMultimedia import QSound

            QSound.play(path)
        except ImportError:
            pass


_beep_map = {
    "notification": (800, 150),
    "error": (200, 400),
    "success": (1200, 200),
    "warning": (600, 300),
}


def beep(event: str) -> None:
    freq_dur = _beep_map.get(event)
    if freq_dur:
        try:
            import winsound

            winsound.Beep(*freq_dur)
        except ImportError:
            pass
