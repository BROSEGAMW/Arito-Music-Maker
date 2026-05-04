# -*- coding: utf-8 -*-
"""
tools/audio_engine.py

Σταθερό wrapper για FluidSynth (pyfluidsynth).

Per-slot FX (INSTRUMENT_DATA[index]['effects']):
- Volume:   CC7  + volume_on (mute)
- Pan:      CC10
- Balance:  CC8
- Reverb:   CC91 + reverb.on   (send amount)  (Reverb Send Level) [5](https://www.youtube.com/watch?v=4SI5GMb1RgM)[6](https://mail.gnu.org/archive/html/fluid-dev/2020-07/msg00001.html)
- Chorus:   CC93 + chorus.on   (send amount)  (Chorus Send Level) [5](https://www.youtube.com/watch?v=4SI5GMb1RgM)[6](https://mail.gnu.org/archive/html/fluid-dev/2020-07/msg00001.html)

Extra (ίδια μορφή on/off + amount=80):
- Sustain:    CC64 (>=64 ON) [2](https://openmusic-project.github.io/openmusic/doc/fluid.html)[1](https://discourse.nixos.org/t/how-to-configure-fluidsynth-to-use-soundfont-fluid/42830)
- Modulation: CC1            [1](https://discourse.nixos.org/t/how-to-configure-fluidsynth-to-use-soundfont-fluid/42830)[2](https://openmusic-project.github.io/openmusic/doc/fluid.html)

Expression / Tremolo / Glide / Filter αφαιρέθηκαν.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Optional, Tuple, Dict

import fluidsynth
from settings.selections import INSTRUMENT_DATA

CC_MOD = 1
CC_VOLUME = 7
CC_BALANCE = 8
CC_PAN = 10
CC_REVERB = 91
CC_CHORUS = 93
CC_ALL_NOTES_OFF = 123

DEFAULT_EFFECTS = {
    "volume": 100,
    "volume_on": True,
    "pan": 64,

    "reverb": {"on": False, "amount": 80},
    "chorus": {"on": False, "amount": 80},

    # ίδια μορφή: on + amount (preset 80)
    "sustain": {"on": False, "amount": 80},
    "mod": {"on": False, "amount": 80},
}

_init_lock = threading.Lock()
_api_lock = threading.RLock()

_fs: Optional[fluidsynth.Synth] = None
_sfid: Optional[int] = None
_current: Tuple[int, int] = (0, 0)
_initialized = False

_last_cc_by_ch: Dict[int, Dict[str, int]] = {}


def _default_sf2_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_src = os.path.dirname(base_dir)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        project_src = sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.join(project_src, "tools", "soundfonts", "GeneralUser-GS.sf2")


def _add_dll_dir_if_needed() -> None:
    if os.name != "nt":
        return
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_src = os.path.dirname(base_dir)
        dll_dir = os.path.join(project_src, "tools", "fluidsynth", "bin")
        if os.path.isdir(dll_dir):
            os.add_dll_directory(dll_dir)
    except Exception:
        pass


def init(sf2_path: Optional[str] = None) -> None:
    global _fs, _sfid, _initialized
    with _init_lock:
        if _initialized:
            return

        _add_dll_dir_if_needed()

        with _api_lock:
            _fs = fluidsynth.Synth()
            _fs.start()

            path = sf2_path or _default_sf2_path()
            sfid = _fs.sfload(path)
            if sfid is None or int(sfid) < 0:
                raise RuntimeError(f"Αποτυχία φόρτωσης soundfont: {path}")

            _sfid = int(sfid)

        _initialized = True


def _ensure() -> None:
    if not _initialized:
        init()


def cc(control: int, value: int, channel: int = 0) -> None:
    _ensure()
    if _fs is None:
        return
    v = max(0, min(127, int(value)))
    with _api_lock:
        _fs.cc(int(channel), int(control), v)


def _hard_reset_channel(ch: int) -> None:
    """
    Ασφαλές reset ώστε να μην μένει κανάλι "βουβό" από παλιά CC.
    """
    cc(CC_VOLUME, 100, channel=ch)
    cc(CC_PAN, 64, channel=ch)
    cc(CC_BALANCE, 64, channel=ch)
    cc(CC_MOD, 0, channel=ch)
    cc(CC_REVERB, 0, channel=ch)
    cc(CC_CHORUS, 0, channel=ch)

    _last_cc_by_ch[ch] = {"pan": 64, "vol": 100, "rev": 0, "cho": 0, "mod": 0}


def set_preset(bank: int, program: int, channel: int = 0) -> None:
    global _current
    _ensure()
    if _fs is None or _sfid is None:
        return

    ch = int(channel)
    with _api_lock:
        _fs.program_select(ch, int(_sfid), int(bank), int(program))

    # κρίσιμο: reset CC μετά από program change
    _hard_reset_channel(ch)
    _current = (int(bank), int(program))


def play_note(midi_note: int, velocity: int = 127, channel: int = 0) -> None:
    _ensure()
    if _fs is None:
        return

    ch = int(channel)
    if ch not in _last_cc_by_ch:
        _hard_reset_channel(ch)

    vel = max(0, min(127, int(velocity)))
    with _api_lock:
        _fs.noteon(ch, int(midi_note), vel)


def stop_note(midi_note: int, channel: int = 0) -> None:
    _ensure()
    if _fs is None:
        return
    with _api_lock:
        _fs.noteoff(int(channel), int(midi_note))


def all_notes_off(channel: Optional[int] = None) -> None:
    _ensure()
    if _fs is None:
        return

    channels = range(16) if channel is None else (int(channel),)
    with _api_lock:
        for ch in channels:
            _fs.cc(int(ch), CC_ALL_NOTES_OFF, 0)


def current_preset() -> Tuple[int, int]:
    return _current


def ensure_slot_effects(index: int):
    slot = INSTRUMENT_DATA.setdefault(int(index), {})
    fx = slot.setdefault("effects", {})

    fx.setdefault("volume", DEFAULT_EFFECTS["volume"])
    fx.setdefault("volume_on", DEFAULT_EFFECTS["volume_on"])
    fx.setdefault("pan", DEFAULT_EFFECTS["pan"])

    fx.setdefault("reverb", dict(DEFAULT_EFFECTS["reverb"]))
    fx.setdefault("chorus", dict(DEFAULT_EFFECTS["chorus"]))

    fx.setdefault("sustain", dict(DEFAULT_EFFECTS["sustain"]))
    fx.setdefault("mod", dict(DEFAULT_EFFECTS["mod"]))

    return fx


def apply_slot_effects(index: int) -> None:
    slot = INSTRUMENT_DATA.get(int(index), {}) or {}
    ch = int(slot.get("channel", 0))

    fx = ensure_slot_effects(int(index))

    vol_on = bool(fx.get("volume_on", True))
    vol = int(fx.get("volume", 100))
    vol = 0 if not vol_on else vol

    pan = int(fx.get("pan", 64))

    rev = fx.get("reverb", {}) or {}
    cho = fx.get("chorus", {}) or {}
    rev_amt = int(rev.get("amount", 80)) if bool(rev.get("on", False)) else 0
    cho_amt = int(cho.get("amount", 80)) if bool(cho.get("on", False)) else 0

    # # Sustain: amount >=64 => ON
    # sus = fx.get("sustain", {}) or {}
    # sus_amt = int(sus.get("amount", 80)) if bool(sus.get("on", False)) else 0
    # sus_val = 127 if sus_amt >= 64 else 0  # [2](https://openmusic-project.github.io/openmusic/doc/fluid.html)[1](https://discourse.nixos.org/t/how-to-configure-fluidsynth-to-use-soundfont-fluid/42830)

    # Mod
    mod = fx.get("mod", {}) or {}
    mod_val = int(mod.get("amount", 80)) if bool(mod.get("on", False)) else 0

    cc(CC_VOLUME, vol, channel=ch)
    cc(CC_PAN, pan, channel=ch)
    cc(CC_BALANCE, pan, channel=ch)

    cc(CC_REVERB, rev_amt, channel=ch)  # [5](https://www.youtube.com/watch?v=4SI5GMb1RgM)[6](https://mail.gnu.org/archive/html/fluid-dev/2020-07/msg00001.html)
    cc(CC_CHORUS, cho_amt, channel=ch)  # [5](https://www.youtube.com/watch?v=4SI5GMb1RgM)[6](https://mail.gnu.org/archive/html/fluid-dev/2020-07/msg00001.html)

    cc(CC_MOD, mod_val, channel=ch)      # [1](https://discourse.nixos.org/t/how-to-configure-fluidsynth-to-use-soundfont-fluid/42830)[2](https://openmusic-project.github.io/openmusic/doc/fluid.html)

    _last_cc_by_ch[ch] = {"pan": pan, "vol": vol, "rev": rev_amt, "cho": cho_amt, "mod": mod_val}
