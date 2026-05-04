
import os
import sys
import pygame
import threading

_tick = None
_tock = None
_enabled = False
_tick_vol = 0.9
_tock_vol = 0.6
_latency_ms = 0.0


def set_latency_ms(ms: float) -> None:  # <-- ΝΕΟ API
    global _latency_ms
    _latency_ms = max(0.0, float(ms))



def _asset_dir() -> str:
    """
    Εντοπίζει το φάκελο assets για dev ή PyInstaller (frozen exe).
    .../src/tools -> project_src = .../src
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))  # .../src/tools
    project_src = os.path.dirname(base_dir)  # .../src

    # PyInstaller support
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        project_src = sys._MEIPASS  # type: ignore

    return os.path.join(project_src, "assets", "metronome")


def init() -> None:
    """Φόρτωση των samples (ο mixer έχει γίνει pre_init στο app.py)."""
    global _tick, _tock
    folder = _asset_dir()
    tick_path = os.path.join(folder, "tick1.wav")
    tock_path = os.path.join(folder, "tick2.wav")

    _tick = pygame.mixer.Sound(tick_path)
    _tock = pygame.mixer.Sound(tock_path)

    _tick.set_volume(_tick_vol)
    _tock.set_volume(_tock_vol)


def set_enabled(v: bool) -> None:
    global _enabled
    _enabled = bool(v)


def is_enabled() -> bool:
    return _enabled


def set_volume(tick: float, tock: float) -> None:
    """Τιμές 0.0..1.0. Αποθηκεύονται και εφαρμόζονται άμεσα στα loaded samples."""
    global _tick_vol, _tock_vol
    _tick_vol = max(0.0, min(1.0, float(tick)))
    _tock_vol = max(0.0, min(1.0, float(tock)))
    if _tick:
        _tick.set_volume(_tick_vol)
    if _tock:
        _tock.set_volume(_tock_vol)



def play_tick() -> None:
    if _enabled and _tick:
        if _latency_ms > 0:
            threading.Timer(_latency_ms / 1000.0, _tick.play).start()
        else:
            _tick.play()



def play_tock() -> None:
    if _enabled and _tock:
        if _latency_ms > 0:
            threading.Timer(_latency_ms / 1000.0, _tock.play).start()
        else:
            _tock.play()

