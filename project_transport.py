# tools/project_transport.py
# Shared project playback for the Menu screen.
from __future__ import annotations

import math
import threading
from typing import Dict, Iterable, Optional

import pygame

from settings.channels import SLOT_CHANNELS
from settings.drum_kits import DRUM_CHANNEL
from settings.project_state import PROJECT_SETTINGS, ensure_project_settings
from settings.selections import INSTRUMENT_DATA
from tools.audio_engine import all_notes_off, apply_slot_effects, play_note, set_preset, stop_note

GLOBAL_STEPS_PER_BAR = 192
GLOBAL_STEPS_PER_BEAT = GLOBAL_STEPS_PER_BAR // 4
DRUM_STEPS_PER_BEAT = 4
DRUM_STEP_SCALE = GLOBAL_STEPS_PER_BEAT // DRUM_STEPS_PER_BEAT
TEMPO_CORR = 0.9972376


def _build_notes_descending():
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    ascending = []
    for octv in range(1, 8):
        for name in names:
            ascending.append(f"{name}{octv}")
    ascending.append("C8")
    ascending.reverse()
    return ascending


NOTE_LABELS = _build_notes_descending()


def _note_label_to_midi(label: str) -> int:
    table = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    name = label[:-1]
    octv = int(label[-1])
    if name not in table:
        raise ValueError(f"Unsupported note label format: {label}")
    return (octv + 1) * 12 + table[name]


def _slot_is_drums(slot: Dict) -> bool:
    try:
        bank = int(slot.get("bank", -1))
    except (TypeError, ValueError):
        bank = -1
    return bank == 128 or slot.get("instrument") == "Drums" or "drum_rack" in slot


def slot_channel_for(index: int, slot: Optional[Dict] = None) -> int:
    slot = slot if slot is not None else (INSTRUMENT_DATA.get(int(index), {}) or {})
    if _slot_is_drums(slot):
        return DRUM_CHANNEL

    fallback = SLOT_CHANNELS.get(int(index), 0)
    try:
        return int(slot.get("channel", fallback))
    except (TypeError, ValueError):
        return fallback


def apply_slot_preset(index: int) -> None:
    slot = INSTRUMENT_DATA.get(int(index), {}) or {}
    if not slot:
        return
    if "bank" not in slot and "program" not in slot and "instrument" not in slot:
        return

    try:
        bank = int(slot.get("bank", 0) or 0)
    except (TypeError, ValueError):
        bank = 0
    try:
        program = int(slot.get("program", 0) or 0)
    except (TypeError, ValueError):
        program = 0

    channel = slot_channel_for(int(index), slot)
    slot["channel"] = int(channel)
    set_preset(bank, program, channel=channel)
    apply_slot_effects(int(index))


def apply_all_slot_presets_effects(indices: Optional[Iterable[int]] = None) -> None:
    if indices is None:
        indices = sorted(int(k) for k in INSTRUMENT_DATA.keys())
    for index in indices:
        apply_slot_preset(int(index))


def _tail_seconds(slot: Dict) -> float:
    fx = slot.get("effects", {}) or {}
    sustain = fx.get("sustain", {}) or {}
    if not bool(sustain.get("on", False)):
        return 0.0

    try:
        amount = int(sustain.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    amount = max(0, min(127, amount))
    return ((amount / 127.0) ** 1.6) * 2.5


class ProjectTransport:
    def __init__(self):
        self.is_playing = False
        self.current_step = 0
        self.display_step = 0
        self.last_step_time = 0.0

    def _step_ms(self) -> float:
        settings = ensure_project_settings()
        bpm = float(settings["global_tempo_bpm"]) * TEMPO_CORR
        return 60000.0 / (bpm * GLOBAL_STEPS_PER_BEAT)

    def _piano_content_len(self, piano_roll: Dict) -> int:
        notes = piano_roll.get("notes_v2", []) or []
        max_end = 0
        for note in notes:
            try:
                start = int(note.get("start", 0))
                length = int(note.get("length", 1))
            except (TypeError, ValueError):
                continue
            max_end = max(max_end, start + max(1, length))
        return max_end

    def _drum_content_len(self, drum_rack: Dict) -> int:
        pattern = drum_rack.get("pattern", []) or []
        max_col = -1
        for row in pattern:
            if not isinstance(row, list):
                continue
            for col, value in enumerate(row):
                if int(value or 0) == 1:
                    max_col = max(max_col, col)
        if max_col < 0:
            return 0
        return (max_col + 1) * DRUM_STEP_SCALE

    def content_len(self) -> int:
        max_len = 0
        for slot in INSTRUMENT_DATA.values():
            if not isinstance(slot, dict):
                continue
            piano_roll = slot.get("piano_roll", {}) or {}
            drum_rack = slot.get("drum_rack", {}) or {}
            if isinstance(piano_roll, dict):
                max_len = max(max_len, self._piano_content_len(piano_roll))
            if isinstance(drum_rack, dict):
                max_len = max(max_len, self._drum_content_len(drum_rack))
        return max_len

    def has_content(self) -> bool:
        return self.content_len() > 0

    def loop_len(self) -> int:
        content = self.content_len()
        if content <= 0:
            return GLOBAL_STEPS_PER_BAR
        if bool(ensure_project_settings().get("global_loop", False)):
            bars = int(math.ceil(content / float(GLOBAL_STEPS_PER_BAR)))
            return max(GLOBAL_STEPS_PER_BAR, bars * GLOBAL_STEPS_PER_BAR)
        return max(1, content)

    def play(self) -> bool:
        if not self.has_content():
            self.stop()
            return False

        apply_all_slot_presets_effects()
        max_step = max(0, self.loop_len() - 1)
        self.current_step = max(0, min(int(self.current_step), max_step))
        self.display_step = self.current_step
        self.is_playing = True
        self.last_step_time = float(pygame.time.get_ticks())
        return True

    def stop(self) -> None:
        self.is_playing = False
        self.current_step = 0
        self.display_step = 0
        all_notes_off()

    def toggle_loop(self) -> bool:
        settings = ensure_project_settings()
        settings["global_loop"] = not bool(settings.get("global_loop", False))
        ensure_project_settings()
        return bool(PROJECT_SETTINGS["global_loop"])

    def change_tempo(self, delta: int) -> int:
        settings = ensure_project_settings()
        settings["global_tempo_bpm"] = max(40, min(200, int(settings["global_tempo_bpm"]) + int(delta)))
        ensure_project_settings()
        if self.is_playing:
            self.last_step_time = float(pygame.time.get_ticks())
        return int(PROJECT_SETTINGS["global_tempo_bpm"])

    def progress_ratio(self) -> float:
        if not self.has_content():
            return 0.0
        length = max(1, self.loop_len() - 1)
        step = max(0, min(int(self.display_step), length))
        return step / float(length)

    def seek_ratio(self, ratio: float) -> bool:
        if not self.has_content():
            self.current_step = 0
            self.display_step = 0
            return False

        ratio = max(0.0, min(1.0, float(ratio)))
        length = max(1, self.loop_len() - 1)
        target = int(round(ratio * length))
        self.current_step = target
        self.display_step = target
        self.last_step_time = float(pygame.time.get_ticks())
        return True

    def _trigger_piano_slot(self, index: int, slot: Dict, step: int, step_ms: float) -> None:
        piano_roll = slot.get("piano_roll", {}) or {}
        notes = piano_roll.get("notes_v2", []) or []
        channel = slot_channel_for(index, slot)
        tail = _tail_seconds(slot)

        for note in notes:
            try:
                start = int(note.get("start", 0))
                length = max(1, int(note.get("length", 1)))
                row = int(note.get("row", -1))
            except (TypeError, ValueError):
                continue
            if start != step or not (0 <= row < len(NOTE_LABELS)):
                continue

            midi_note = _note_label_to_midi(NOTE_LABELS[row])
            play_note(midi_note, velocity=110, channel=channel)
            duration_sec = max(0.01, (length * step_ms) / 1000.0)
            threading.Timer(duration_sec + tail, lambda nn=midi_note, ch=channel: stop_note(nn, channel=ch)).start()

    def _trigger_drum_slot(self, slot: Dict, step: int) -> None:
        if step % DRUM_STEP_SCALE != 0:
            return

        drum_rack = slot.get("drum_rack", {}) or {}
        pattern = drum_rack.get("pattern", []) or []
        drum_rows = drum_rack.get("drum_rows", []) or []
        col = step // DRUM_STEP_SCALE

        for row_idx, row in enumerate(pattern):
            if not isinstance(row, list) or col >= len(row):
                continue
            if int(row[col] or 0) != 1:
                continue
            if row_idx >= len(drum_rows):
                continue

            try:
                midi_note = int(drum_rows[row_idx])
            except (TypeError, ValueError):
                continue
            if midi_note < 0:
                continue

            play_note(midi_note, velocity=110, channel=DRUM_CHANNEL)
            threading.Timer(0.05, lambda nn=midi_note: stop_note(nn, channel=DRUM_CHANNEL)).start()

    def _trigger_step(self, step: int, step_ms: float) -> None:
        for index in sorted(int(k) for k in INSTRUMENT_DATA.keys()):
            slot = INSTRUMENT_DATA.get(index, {}) or {}
            if not isinstance(slot, dict):
                continue
            if _slot_is_drums(slot):
                self._trigger_drum_slot(slot, step)
            else:
                self._trigger_piano_slot(index, slot, step, step_ms)

    def update(self) -> None:
        if not self.is_playing:
            return

        step_ms = self._step_ms()
        now = float(pygame.time.get_ticks())
        loop_len = self.loop_len()

        while self.is_playing and now - float(self.last_step_time) >= step_ms:
            self.last_step_time = float(self.last_step_time) + step_ms

            if not bool(ensure_project_settings().get("global_loop", False)) and self.current_step >= loop_len:
                self.display_step = max(0, loop_len - 1)
                self.stop()
                break

            self.display_step = self.current_step
            self._trigger_step(self.display_step, step_ms)

            if bool(PROJECT_SETTINGS.get("global_loop", False)):
                self.current_step = (self.current_step + 1) % max(1, loop_len)
            else:
                self.current_step += 1


PROJECT_TRANSPORT = ProjectTransport()
