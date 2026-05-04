# -*- coding: utf-8 -*-
import math
import threading
import pygame
from settings.colors import BG_COLOR, GRID_COLOR, TEXT_LIGHT, TEXT_DARK, BUTTON_BG, BUTTON_BORDER
from UI.widgets import Button
from tools.audio_engine import all_notes_off, play_note, stop_note, apply_slot_effects
from settings.channels import SLOT_CHANNELS
from settings.selections import INSTRUMENT_DATA
import tools.metronome as MET

# ==============================
# Tempo mapping (BPM ↔ program value)
# ==============================
def bpm_to_pvalue(bpm: float) -> float:
    return (bpm - 11.5) / 0.8625

def pvalue_to_bpm(pv: float) -> float:
    return pv * 0.8625 + 11.5


class PianoRollScreen:
    # Τελικό tuning μετά το fixed timestep
    TEMPO_CORR = 0.9972376
    DEBUG_TEMPO = False

    def __init__(self, index: int):
        self.index = index

        
        # --- Debug latency (UI -> trigger) ---
        self.dbg_latency = True
        self._dbg_t0_ms = None
        self._dbg_ui_to_trigger_ms = None

        # --- Layout ---
        self.header_h = 48
        self.left_w = 90
        self.row_h = 20
        self.scrollbar_w = 12
        self.step_w = 24
        self.hscroll_h = 12

        # --- Zoom limits ---
        self.step_w_min, self.step_w_max = 1, 96
        self.row_h_min, self.row_h_max = 12, 48

        # --- Fonts ---
        self.font = pygame.font.Font(None, 18)
        self.font_header = pygame.font.Font(None, 28)

        # --- Notes list (C8..C2 descending) ---
        self.notes = self._build_notes_descending()
        self.top_row = 0
        self._last_height = 1
        self.current_note = ""

        # --- Scrolling/UI flags ---
        self.dragging_scroll = False
        self.dragging_hscroll = False
        self.dragging_tempo = False
        self._drag_offset = 0
        self._tempo_drag_offset = 0
        self._scroll_track_rect = pygame.Rect(0, 0, 0, 0)
        self._h_scroll_track_rect = pygame.Rect(0, 0, 0, 0)
        self._grid_rect = pygame.Rect(0, 0, 0, 0)
        # Safe-click flags
        self._ui_click_in_progress = False
        self._mouse_down_in_grid = False

        # --- V2 data model: explicit notes list ---
        self.notes_v2 = []          # list of dicts: {'id': int, 'row': int, 'start': int, 'length': int}
        self._next_note_id = 1

        # Drag bookkeeping (single-note move)
        self._drag_started = False
        self._drag_note_id = None
        self._drag_note_pick_offset = 0
        self._drag_note_src_row = -1
        self._drag_note_src_start = 0
        self._mouse_down_cell = None
        self._drag_threshold_px = 3

        # --- Selection state ---
        self.sel_active = False
        self.sel_dragging = False
        self.sel_anchor = (0, 0)         # (row0, step0)
        self.sel_rect = None             # (r0, r1, s0, s1)
        self.sel_ids = set()
        self.sel_flash_ids = set()
        self.sel_flash_until = 0
        self.sel_bbox = None
        self.sel_bbox_last = None

        # Group-drag (με clamp αριστερά)
        self.group_dragging = False
        self.group_drag_ids = set()
        self._group_drag_start_cell = None
        self._group_drag_snapshot = {}
        self._group_drag_min_start = 0

        # --- Clipboard για Ctrl+C/X/V ---
        self.clipboard = {'notes': [], 'w': 0, 'h': 0}

        # --- Cells (legacy για συμβατότητα) ---
        self.active_cells = set()

        # --- Sequencer timing ---
        # ΝΕΑ βασική ανάλυση: 192 steps/bar -> 48 steps/beat (υποστηρίζει ακριβώς 1/2, 1/3, 1/4, 1/6, 1/8, 1/16)
        self.BAR_STEPS = 192
        self.STEPS_PER_BEAT = self.BAR_STEPS / 4.0  # 48.0

        self.tempo_bpm = 120
        self.tempo_pv = bpm_to_pvalue(self.tempo_bpm)
        self._recompute_step_ms()
        self.last_step_time = 0.0
        self.current_step = 0
        self.display_step = 0

        # --- Playback state ---
        self.is_playing = False
        self.is_looping = False
        self._flash_last_step = False
        self._centered_once = False
        self.note_preview_timeout_ms = 650
        self._note_reset_at = 0
        self.start_step = 0
        self.total_steps = int(self.BAR_STEPS)

        # Metronome de-dup per step
        self._last_met_step = -1

        # --- Buttons ---
        self.btn_play = Button(pygame.Rect(0, 0, 60, 30), bg_color=(0, 180, 0), border_color=(30, 30, 30), text="Play", font=self.font, text_color=TEXT_DARK)
        self.btn_stop = Button(pygame.Rect(0, 0, 60, 30), bg_color=(180, 0, 0), border_color=(30, 30, 30), text="Stop", font=self.font, text_color=TEXT_LIGHT)
        self.btn_loop = Button(pygame.Rect(0, 0, 60, 30), bg_color=(200, 140, 0), border_color=(30, 30, 30), text="Loop", font=self.font, text_color=TEXT_DARK)
        self.btn_clear= Button(pygame.Rect(0, 0, 60, 30), bg_color=(100,100,100), border_color=(30,30,30), text="Clear", font=self.font, text_color=TEXT_LIGHT)

        self.back_btn = Button(rect=pygame.Rect(12, 8, 100, self.header_h - 16), bg_color=BUTTON_BG, border_color=BUTTON_BORDER, text="Πίσω", font=self.font, text_color=TEXT_DARK)
        self.btn_met = Button(pygame.Rect(0, 0, 30, 30), bg_color=BUTTON_BG, border_color=(30,30,30), text="Met", font=self.font, text_color=TEXT_DARK)

        # Metronome state & volumes
        self.is_met_on = False
        self.met_tick_vol = 0.9
        self.met_tock_vol = 0.6

        # Tempo slider conf (real BPM on UI)
        self.tempo_min = 40
        self.tempo_max = 200
        self._tempo_slider_track = pygame.Rect(0, 0, 0, 0)
        self._tempo_thumb_rect = pygame.Rect(0, 0, 12, 12)
        self.btn_tempo_minus = Button(pygame.Rect(0, 0, 24, 24), bg_color=BUTTON_BG, border_color=(30,30,30), text="−", font=self.font, text_color=TEXT_DARK)
        self.btn_tempo_plus  = Button(pygame.Rect(0, 0, 24, 24), bg_color=BUTTON_BG, border_color=(30,30,30), text="+", font=self.font, text_color=TEXT_DARK)

        self._header_rect = pygame.Rect(0,0,0,0)
        self._minus_rect = pygame.Rect(0,0,0,0)
        self._plus_rect  = pygame.Rect(0,0,0,0)

        # --- Snap to Grid (όλα σε STEPS για 48 steps/beat) ---
        self.snap_options = [
            (24, "1/2 beat"),
            (16, "1/3 beat"),
            (12, "1/4 beat"),
            (8,  "1/6 beat"),
            (6,  "1/8 beat"),
            (3,  "1/16 beat"),
        ]
        self.snap_idx = 2  # default: 1/4 beat = 12 steps
        self.snap_steps, self.snap_label = self.snap_options[self.snap_idx]
        self.snap_enabled = True
        self.btn_snap = Button(
            pygame.Rect(0, 0, 110, 30),
            bg_color=BUTTON_BG, border_color=BUTTON_BORDER,
            text=f"Snap {self.snap_label}", font=self.font, text_color=TEXT_DARK
        )

        # --- Undo/Redo μικρά κουμπιά δίπλα στο Snap ---
        self.btn_undo = Button(
            pygame.Rect(0, 0, 26, 26),
            bg_color=BUTTON_BG, border_color=BUTTON_BORDER,
            text="<-", font=self.font, text_color=TEXT_DARK
        )
        self.btn_redo = Button(
            pygame.Rect(0, 0, 26, 26),
            bg_color=BUTTON_BG, border_color=BUTTON_BORDER,
            text="->", font=self.font, text_color=TEXT_DARK
        )

        # --- Undo/Redo history ---
        self.HIST_LIMIT = 10
        self._hist = []                 # στοίβα για Undo
        self._redo = []                 # στοίβα για Redo
        self._drag_hist_armed = False   # armado του history στην έναρξη drag


        apply_slot_effects(self.index)
        
        # Load from store (after constructing Snap button)
        self._load_from_store()

    def _slot_channel(self) -> int:
        slot = INSTRUMENT_DATA.get(self.index, {}) or {}
        fallback = SLOT_CHANNELS.get(self.index, 0)
        try:
            return int(slot.get("channel", fallback))
        except (TypeError, ValueError):
            return fallback

    def _stop_playback(self, save: bool = False) -> None:
        self.is_playing = False
        self.display_step = 0
        self.current_step = 0
        self._flash_last_step = False
        self._last_met_step = -1
        all_notes_off(channel=self._slot_channel())
        if save:
            self._save_to_store()
    
    # ---- μοναδική πηγή αλήθειας για step_ms ----
    def _recompute_step_ms(self):
        effective_bpm = float(self.tempo_bpm) * float(self.TEMPO_CORR)
        self.step_ms = 60000.0 / (effective_bpm * self.STEPS_PER_BEAT)

    # ---- Header layout helper ----
    def _layout_header(self, w: int, h: int):
        header_rect = pygame.Rect(0, 0, w, self.header_h)
        self._header_rect = header_rect

        gap = 16
        self.btn_met.rect.topleft = (self.back_btn.rect.right + gap, header_rect.centery - self.btn_met.rect.height // 2)

        pad = 10
        label_w, _ = self.font.size("BPM:")
        x_start = self.btn_met.rect.right + 20
        y_mid   = header_rect.centery
        minus_rect = pygame.Rect(x_start + label_w + pad, y_mid - 12, 24, 24)
        track_x    = minus_rect.right + pad
        track_w    = 220
        track_rect = pygame.Rect(track_x, y_mid - 3, track_w, 6)
        plus_rect  = pygame.Rect(track_rect.right + pad, y_mid - 12, 24, 24)
        self._minus_rect = minus_rect
        self._plus_rect  = plus_rect
        self._tempo_slider_track = track_rect
        thumb_x = self._tempo_to_thumb_x(track_rect)
        self._tempo_thumb_rect = pygame.Rect(thumb_x - 6, y_mid - 6, 12, 12)

        play_x, stop_x, loop_x = w - 200, w - 135, w - 70
        clear_x = w - 265
        y_btn = header_rect.centery - 15
        self.btn_clear.rect.topleft = (clear_x, y_btn)
        self.btn_play.rect.topleft  = (play_x,  y_btn)
        self.btn_stop.rect.topleft  = (stop_x,  y_btn)
        self.btn_loop.rect.topleft  = (loop_x,  y_btn)

        # Snap button
        self.btn_snap.rect.topleft = (self._plus_rect.right + 60, y_btn)

        # Undo/Redo δίπλα στο Snap
        undo_y = header_rect.centery - self.btn_undo.rect.height // 2
        self.btn_undo.rect.topleft = (self.btn_snap.rect.right + 8, undo_y)
        self.btn_redo.rect.topleft = (self.btn_undo.rect.right + 6, undo_y)

    # ---- Body layout helper ----
    def _layout_body(self, w: int, h: int):
        grid_h      = (h - self.header_h) - self.hscroll_h
        grid_rect   = pygame.Rect(self.left_w, self.header_h, w - self.left_w - self.scrollbar_w, grid_h)
        scroll_track= pygame.Rect(w - self.scrollbar_w, self.header_h, self.scrollbar_w, grid_h)
        self._h_scroll_track_rect = pygame.Rect(self.left_w, self.header_h + grid_h, grid_rect.width, self.hscroll_h)
        self._scroll_track_rect = scroll_track
        self._grid_rect = grid_rect

    # --------------------- helpers ---------------------
    def _build_notes_descending(self):
        names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        ascending = []
        for octv in range(1, 8):
            for n in names:
                ascending.append(f"{n}{octv}")
        ascending.append("C8")
        ascending.reverse()
        return ascending

    def _tail_seconds(self) -> float:
        slot = INSTRUMENT_DATA.get(self.index, {}) or {}
        fx = slot.get("effects", {}) or {}
        sus = fx.get("sustain", {}) or {}

        # toggle OFF => 0 tail
        if not bool(sus.get("on", False)):
            return 0.0

        amt = int(sus.get("amount", 0))
        amt = max(0, min(127, amt))

        # ✅ FULL RANGE: 0..127 -> 0..MAX seconds
        MAX_TAIL_SEC = 2.5   # διάλεξε 2.0, 2.5, 3.0 όπως σου αρέσει

        
        curve = 1.6
        return ((amt / 127.0) ** curve) * MAX_TAIL_SEC

    
    def _note_label_to_midi(self, label: str) -> int:
        table = {"C":0,"C#":1,"D":2,"D#":3,"E":4,"F":5,"F#":6,"G":7,"G#":8,"A":9,"A#":10,"B":11}
        name = label[:-1]
        octv = int(label[-1])
        if name not in table:
            raise ValueError(f"Unsupported note label format: {label}\n")
        return (octv + 1) * 12 + table[name]

    # --------------------- store ---------------------
    def _save_to_store(self) -> None:
        slot = INSTRUMENT_DATA.setdefault(self.index, {})
        pr = slot.setdefault('piano_roll', {})
        pr['cells'] = sorted(list(self.active_cells))
        pr['notes_v2'] = [ {'id': n['id'], 'row': n['row'], 'start': n['start'], 'length': n['length']} for n in self.notes_v2 ]
        pr['tempo_bpm'] = float(self.tempo_bpm)
        pr['tempo_pv']  = float(self.tempo_pv)
        pr['is_looping'] = bool(self.is_looping)
        pr['met_on'] = bool(self.is_met_on)
        pr['met_tick_vol'] = float(self.met_tick_vol)
        pr['met_tock_vol'] = float(self.met_tock_vol)
        # νέα πεδία
        pr['steps_per_beat'] = int(self.STEPS_PER_BEAT)
        pr['snap_enabled'] = bool(self.snap_enabled)
        pr['snap_steps'] = int(self.snap_steps)
        pr['snap_idx'] = int(self.snap_idx)

    def _load_from_store(self) -> None:
        slot = INSTRUMENT_DATA.get(self.index, {})
        pr = slot.get('piano_roll')
        if not pr:
            # baseline για undo/redo
            self._hist.clear(); self._redo.clear()
            self._push_history('init-baseline')
            return

        self.notes_v2 = []
        v2 = pr.get('notes_v2', [])
        if v2:
            for n in v2:
                nid = int(n.get('id', 0)) or self._next_note_id
                note = {'id': nid,'row': int(n['row']),'start': int(n['start']),'length': int(n['length'])}
                self.notes_v2.append(note)
                self._next_note_id = max(self._next_note_id, note['id'] + 1)

        self.active_cells = set((int(r), int(s)) for (r, s) in pr.get('cells', []))
        if not self.notes_v2 and self.active_cells:
            self._migrate_cells_to_notes_v2()

        # BPM restore
        if 'tempo_pv' in pr:
            try:
                pv = float(pr.get('tempo_pv', self.tempo_pv))
                bpm = float(pvalue_to_bpm(pv))
            except Exception:
                bpm = float(self.tempo_bpm)
        else:
            saved_t = pr.get('tempo_bpm', self.tempo_bpm)
            try:
                saved_val = float(saved_t)
            except (TypeError, ValueError):
                saved_val = float(self.tempo_bpm)
            bpm = int(round(saved_val)) if saved_val <= 200 else max(self.tempo_min, min(self.tempo_max, int(round(60000.0 / saved_val))))
        bpm = max(self.tempo_min, min(self.tempo_max, bpm))
        self.tempo_bpm = bpm
        self.tempo_pv = bpm_to_pvalue(self.tempo_bpm)
        self._recompute_step_ms()

        self.is_looping = bool(pr.get('is_looping', self.is_looping))
        self.is_met_on = bool(pr.get('met_on', False))
        self.met_tick_vol = float(pr.get('met_tick_vol', self.met_tick_vol))
        self.met_tock_vol = float(pr.get('met_tock_vol', self.met_tock_vol))

        # --- Load Snap state ---
        self.snap_enabled = bool(pr.get('snap_enabled', True))
        self.snap_idx = int(pr.get('snap_idx', self.snap_idx))
        self.snap_idx = max(0, min(self.snap_idx, len(self.snap_options)-1))
        self.snap_steps, self.snap_label = self.snap_options[self.snap_idx]
        self.btn_snap.text = f"Snap {self.snap_label}"

        # --- SPB migration ---
        saved_spb = int(pr.get('steps_per_beat', int(self.STEPS_PER_BEAT)))
        current_spb = int(self.STEPS_PER_BEAT)
        if saved_spb != current_spb and saved_spb > 0 and current_spb % saved_spb == 0:
            self._migrate_spb(saved_spb, current_spb)

        MET.set_enabled(self.is_met_on)
        MET.set_volume(self.met_tick_vol, self.met_tock_vol)
        self._recalc_total_steps()

        # baseline για undo/redo μετά το φόρτωμα
        self._hist.clear(); self._redo.clear()
        self._push_history('load-baseline')

    # ========== NOTES V2 helpers ==========
    def _recalc_total_steps(self):
        max_end = 0
        for n in self.notes_v2:
            max_end = max(max_end, n['start'] + n['length'])
        self.total_steps = max(self.total_steps, max_end + 10)

    def _add_note(self, row: int, start: int, length: int = 1):
        note = {'id': self._next_note_id, 'row': int(row), 'start': int(start), 'length': max(1, int(length))}
        self._next_note_id += 1
        self.notes_v2.append(note)
        self._recalc_total_steps()
        self._save_to_store()
        return note

    def _migrate_cells_to_notes_v2(self):
        if self.notes_v2:
            return
        per_row = {}
        for (r, s) in sorted(self.active_cells):
            per_row.setdefault(r, []).append(s)
        for r, steps in per_row.items():
            i = 0
            L = len(steps)
            while i < L:
                run_start = steps[i]
                run_end = run_start
                while i + 1 < L and steps[i + 1] == run_end + 1:
                    i += 1
                    run_end = steps[i]
                self._add_note(r, run_start, run_end - run_start + 1)
                i += 1
        self.active_cells.clear()

    def _note_at(self, row: int, step: int):
        for n in reversed(self.notes_v2):
            if n['row'] == row and n['start'] <= step < n['start'] + n['length']:
                return n
        return None

    def _delete_note(self, note_id: int):
        self.notes_v2 = [n for n in self.notes_v2 if n['id'] != note_id]
        self._recalc_total_steps()
        self._save_to_store()

    # -------- Selection helpers --------
    def _clear_selection(self):
        self.sel_active = False
        self.sel_dragging = False
        self.sel_rect = None
        self.sel_ids.clear()
        self.sel_flash_ids.clear()
        self.sel_flash_until = 0
        self.group_dragging = False
        self.group_drag_ids.clear()
        self._group_drag_start_cell = None
        self._group_drag_snapshot.clear()
        self._drag_started = False
        self.sel_bbox = None
        # self.sel_bbox_last μένει για paste fallback

    def _note_in_sel(self, n) -> bool:
        if not (self.sel_active and self.sel_rect):
            return False
        r0, r1, s0, s1 = self.sel_rect
        if not (r0 <= n['row'] <= r1):
            return False
        ns, ne = n['start'], n['start'] + n['length'] - 1
        return not (ne < s0 or ns > s1)

    def _cell_in_sel(self, row: int, step: int) -> bool:
        if not (self.sel_active and self.sel_rect):
            return False
        r0, r1, s0, s1 = self.sel_rect
        return (r0 <= row <= r1) and (s0 <= step <= s1)

    def _compute_bbox_for_ids(self, ids:set):
        if not ids:
            return None
        rows=[]; s_starts=[]; s_ends=[]
        for n in self.notes_v2:
            if n['id'] in ids:
                rows.append(n['row'])
                s_starts.append(n['start'])
                s_ends.append(n['start']+n['length']-1)
        if not rows:
            return None
        return (min(rows), max(rows), min(s_starts), max(s_ends))

    # -------- Clipboard ops --------
    def _clipboard_copy_from_selection(self):
        if not self.sel_ids:
            return False
        bbox = self._compute_bbox_for_ids(self.sel_ids)
        if not bbox:
            return False
        r0, r1, s0, s1 = bbox
        notes = []
        for n in self.notes_v2:
            if n['id'] in self.sel_ids:
                notes.append({'drow': n['row'] - r0, 'dstart': n['start'] - s0, 'length': n['length']})
        self.clipboard = {'notes': notes, 'w': (s1 - s0 + 1), 'h': (r1 - r0 + 1)}
        self.sel_bbox = bbox
        self.sel_bbox_last = bbox
        return True

    def _clipboard_paste_at(self, target_row0: int, target_step0: int):
        if not self.clipboard['notes']:
            return False
        new_ids = []
        for item in self.clipboard['notes']:
            r = target_row0 + item['drow']
            s = target_step0 + item['dstart']
            if r < 0 or r >= len(self.notes):
                continue
            if s < 0:
                continue
            note = self._add_note(r, s, item['length'])
            new_ids.append(note['id'])
        if not new_ids:
            return False
        self.sel_ids = set(new_ids)
        bbox = self._compute_bbox_for_ids(self.sel_ids)
        self.sel_bbox = bbox
        self.sel_bbox_last = bbox
        self.sel_flash_ids = set(new_ids)
        self.sel_flash_until = pygame.time.get_ticks() + 500
        return True

    # ---- Snap helpers ----
    def _snap_is_active(self) -> bool:
        """
        Επιστρέφει True όταν το Snap είναι ενεργό και έχει έγκυρο granularité.
        ALT κρατημένο => προσωρινό bypass.
        Με 48 steps/beat: απαιτούμε q>=1 (θετικά ακέραια βήματα).
        """
        try:
            mods = pygame.key.get_mods()
        except Exception:
            mods = 0
        alt_held = bool(mods & pygame.KMOD_ALT)
        q = int(getattr(self, 'snap_steps', 0) or 0)
        snap_on = bool(getattr(self, 'snap_enabled', True))
        return snap_on and not alt_held and q >= 1

    def _quantize_step(self, step: int, mode: str = 'floor') -> int:
        """Quantize ανά q steps (με 48 steps/beat όλα τα 1/2,1/3,1/4,1/6,1/8,1/16 είναι ακριβή)."""
        s = max(0, int(step))
        if not self._snap_is_active():
            return s
        q = max(1, int(self.snap_steps))
        if mode == 'round':
            return max(0, int(round(s / q)) * q)
        return max(0, (s // q) * q)

    # ---- SPB migration ----
    def _migrate_spb(self, old_spb: int, new_spb: int):
        """Μετατροπή συντεταγμένων/μηκών από old_spb -> new_spb όταν new_spb % old_spb == 0."""
        if old_spb <= 0 or new_spb <= 0:
            return
        if new_spb % old_spb != 0:
            return
        scale = new_spb // old_spb
        if scale == 1:
            return
        for n in self.notes_v2:
            n['start']  = int(n['start'] * scale)
            n['length'] = max(1, int(n['length'] * scale))
        self._recalc_total_steps()

    # ---------- UNDO / REDO ----------
    def _snapshot_state(self):
        """Πάρε ασφαλές στιγμιότυπο του μουσικού state για ιστορικό."""
        return {
            'notes_v2': [dict(n) for n in self.notes_v2],
            'sel_ids': set(self.sel_ids),
            'sel_bbox': (None if self.sel_bbox is None else tuple(self.sel_bbox)),
            'total_steps': int(self.total_steps),
        }

    def _apply_state(self, st: dict):
        """Εφάρμοσε στιγμιότυπο από ιστορικό."""
        self.notes_v2 = [dict(n) for n in st.get('notes_v2', [])]
        self.sel_ids = set(st.get('sel_ids', set()))
        self.sel_bbox = st.get('sel_bbox', None)
        self._recalc_total_steps()
        self._save_to_store()

    def _push_history(self, label: str = ''):
        """Αποθήκευσε τρέχουσα κατάσταση στο ιστορικό και καθάρισε το redo stack."""
        self._hist.append(self._snapshot_state())
        if len(self._hist) > self.HIST_LIMIT:
            self._hist.pop(0)
        self._redo.clear()

    def _undo(self) -> bool:
        """Γύρνα ένα βήμα πίσω. True αν έγινε undo."""
        if len(self._hist) <= 1:
            return False
        # Βάλε το current στο redo
        self._redo.append(self._snapshot_state())
        # Πάρε την τελευταία προηγούμενη
        prev = self._hist.pop()
        self._apply_state(prev)
        return True

    def _redo_do(self) -> bool:
        """Προχώρα ένα βήμα μπροστά (redo). True αν έγινε redo."""
        if not self._redo:
            return False
        # Βάλε το current στο history
        self._hist.append(self._snapshot_state())
        nxt = self._redo.pop()
        self._apply_state(nxt)
        return True

    # -------- Move/Transpose helpers --------
    def _get_hover_cell(self):
        try:
            mx, my = pygame.mouse.get_pos()
        except Exception:
            return None
        if not self._grid_rect.collidepoint(mx, my):
            return None
        row_in_view = (my - self.header_h) // self.row_h
        row_idx = self.top_row + int(row_in_view)
        if not (0 <= row_idx < len(self.notes)):
            return None
        rel_x = mx - self._grid_rect.x
        step_idx = self.start_step + int(rel_x // max(1, self.step_w))
        if step_idx < 0:
            step_idx = 0
        return (row_idx, step_idx)

    def _ids_or_hover(self):
        if self.sel_ids:
            return set(self.sel_ids)
        hover = self._get_hover_cell()
        if hover:
            r, s = hover
            hit = self._note_at(r, s)
            if hit:
                return {hit['id']}
        return set()

    def _move_ids(self, ids:set, drow:int, dstep:int, clamp_left:bool=True, clamp_rows:bool=True):
        if not ids or (drow == 0 and dstep == 0):
            return (0, 0, False)
        rows = [n['row'] for n in self.notes_v2 if n['id'] in ids]
        starts = [n['start'] for n in self.notes_v2 if n['id'] in ids]
        if not rows:
            return (0, 0, False)
        min_row, max_row = min(rows), max(rows)
        min_start = min(starts)
        applied_drow = drow
        applied_dstep = dstep
        if clamp_rows:
            if applied_drow < 0:
                applied_drow = max(applied_drow, -min_row)
            if applied_drow > 0:
                applied_drow = min(applied_drow, (len(self.notes) - 1) - max_row)
        if clamp_left and applied_dstep < 0:
            applied_dstep = max(applied_dstep, -min_start)
        moved = False
        if applied_drow != 0 or applied_dstep != 0:
            for n in self.notes_v2:
                if n['id'] in ids:
                    n['row'] = max(0, min(len(self.notes)-1, n['row'] + applied_drow))
                    n['start'] = max(0, n['start'] + applied_dstep)
            self._recalc_total_steps()
            self._save_to_store()
            moved = True
        if ids == self.sel_ids and moved:
            self.sel_bbox = self._compute_bbox_for_ids(self.sel_ids)
            self.sel_bbox_last = self.sel_bbox
        return (applied_drow, applied_dstep, moved)

    def _transpose_octave(self, ids:set, direction:int):
        drow = 12 * (1 if direction > 0 else -1)
        return self._move_ids(ids, drow=drow, dstep=0, clamp_left=False, clamp_rows=True)

    # --------------------- properties ---------------------
    @property
    def visible_rows(self):
        return max(1, (self._last_height - self.header_h) // self.row_h)

    def _clamp_top(self):
        max_top = max(0, len(self.notes) - self.visible_rows)
        if self.top_row < 0:
            self.top_row = 0
        if self.top_row > max_top:
            self.top_row = max_top

    def _clamp_start(self, vis_steps: int = None):
        """Κρατά το start_step πάντοτε στο έγκυρο εύρος (για να μη «φεύγει» το thumb)."""
        if vis_steps is None:
            vis_steps = max(1, self._grid_rect.width // max(1, self.step_w))
        max_start = max(0, self.total_steps - vis_steps)
        if self.start_step < 0:
            self.start_step = 0
        if self.start_step > max_start:
            self.start_step = max_start

    # vertical scrollbar
    def _scroll_thumb(self, track: pygame.Rect):
        total = len(self.notes)
        vis = self.visible_rows
        if total <= vis or track.height <= 0:
            return pygame.Rect(track.x, track.y, track.width, track.height)
        ratio = vis / total
        thumb_h = max(20, int(track.height * ratio))
        max_top = total - vis
        y = int(track.y + (track.height - thumb_h) * (self.top_row / max_top)) if max_top > 0 else track.y
        return pygame.Rect(track.x, y, track.width, thumb_h)

    def _set_top_from_thumb_y(self, thumb_y: int, track: pygame.Rect):
        total = len(self.notes)
        vis = self.visible_rows
        if total <= vis:
            self.top_row = 0
            return
        thumb_h = self._scroll_thumb(track).height
        travel = max(1, track.height - thumb_h)
        pos_ratio = max(0.0, min(1.0, (thumb_y - track.y) / travel))
        max_top = total - vis
        self.top_row = int(round(max_top * pos_ratio))
        self._clamp_top()

    # horizontal scrollbar
    def _h_scroll_thumb(self, track: pygame.Rect, vis_steps: int):
        total = max(1, self.total_steps)
        vis = max(1, vis_steps)
        if total <= vis or track.width <= 0:
            return pygame.Rect(track.x, track.y, track.width, track.height)
        ratio = vis / total
        thumb_w = max(20, int(track.width * ratio))
        max_start = max(0, total - vis)
        self._clamp_start(vis)
        x = int(track.x + (track.width - thumb_w) * (self.start_step / max_start)) if max_start > 0 else track.x
        return pygame.Rect(x, track.y, thumb_w, track.height)

    def _set_start_from_thumb_x(self, thumb_x: int, track: pygame.Rect, vis_steps: int):
        total = max(1, self.total_steps)
        vis = max(1, vis_steps)
        if total <= vis:
            self.start_step = 0
            return
        thumb_w = self._h_scroll_thumb(track, vis_steps).width
        travel = max(1, track.width - thumb_w)
        pos_ratio = max(0.0, min(1.0, (thumb_x - track.x) / travel))
        max_start = total - vis
        self.start_step = int(round(max_start * pos_ratio))
        self._clamp_start(vis)

    # ---- Zoom helpers ----
    def _zoom_horizontal_at(self, mx: int, factor: float) -> None:
        old_w = int(self.step_w)

        # Με round() μπορεί να 'κολλήσει' (π.χ. 2 * 0.909 -> 1.818 round -> 2).
        # Εδώ εξασφαλίζουμε πάντα αλλαγή ώστε να φτάνει πραγματικά στο step_w_min.
        if factor < 1.0:
            new_w = int(old_w * factor)  # floor
            if new_w >= old_w:
                new_w = old_w - 1
        else:
            # ceil-ish
            new_w = int(old_w * factor + 0.9999)
            if new_w <= old_w:
                new_w = old_w + 1

        new_w = int(max(self.step_w_min, min(self.step_w_max, new_w)))
        if new_w == old_w:
            return

        grid = self._grid_rect
        if grid.width <= 0:
            self.step_w = new_w
            return

        cursor_rel = max(0, mx - grid.x)
        col_at_cursor = self.start_step + int(cursor_rel // max(1, old_w))
        self.step_w = new_w
        new_col_under_mouse = int(cursor_rel // max(1, new_w))
        self.start_step = col_at_cursor - new_col_under_mouse

        vis_steps = max(1, grid.width // max(1, self.step_w))
        self._clamp_start(vis_steps)

    def _zoom_vertical_at(self, my: int, factor: float) -> None:
        old_h = int(self.row_h)
        new_h = int(round(max(self.row_h_min, min(self.row_h_max, old_h * factor))))
        if new_h == old_h:
            return
        cursor_rel = max(0, my - self.header_h)
        row_at_cursor = self.top_row + int(cursor_rel // max(1, old_h))
        self.row_h = new_h
        new_row_under_mouse = int(cursor_rel // max(1, new_h))
        self.top_row = max(0, row_at_cursor - new_row_under_mouse)
        self._clamp_top()

    # tempo slider helpers
    def _tempo_to_thumb_x(self, track_rect: pygame.Rect) -> int:
        t = max(self.tempo_min, min(self.tempo_max, float(self.tempo_bpm)))
        ratio = (t - self.tempo_min) / (self.tempo_max - self.tempo_min)
        return int(track_rect.x + ratio * track_rect.width)

    def _thumb_x_to_tempo(self, thumb_x: int, track_rect: pygame.Rect) -> int:
        thumb_x = max(track_rect.x, min(track_rect.right, thumb_x))
        ratio = (thumb_x - track_rect.x) / max(1, track_rect.width)
        t = int(round(self.tempo_min + ratio * (self.tempo_max - self.tempo_min)))
        return max(self.tempo_min, min(self.tempo_max, t))

    # --------------------- events ---------------------
    def handle_event(self, event):
        # Κάνε layout πριν τους handlers (header + body) για σωστό hit-testing
        try:
            screen = pygame.display.get_surface()
            if screen:
                w, h = screen.get_width(), screen.get_height()
                self._layout_body(w, h)
                self._layout_header(w, h)
        except Exception:
            pass

        next_state = None

        # ---------- Buttons / Header ----------
        def go_back():
            nonlocal next_state
            self._stop_playback(save=True)
            next_state = f"instrument {self.index}"

        self.back_btn.handle_event(event, go_back)

        def _apply_new_bpm(new_bpm: int):
            self.tempo_bpm = int(max(self.tempo_min, min(self.tempo_max, new_bpm)))
            self.tempo_pv = bpm_to_pvalue(self.tempo_bpm)
            self._recompute_step_ms()
            self.last_step_time = float(pygame.time.get_ticks())
            self._save_to_store()

        def do_play():
            self._mouse_down_cell = None
            self._mouse_down_in_grid = False
            self._drag_started = False
            apply_slot_effects(self.index)
            self.is_playing = True
            self.current_step = 0
            self.display_step = 0
            self.last_step_time = float(pygame.time.get_ticks())
            self._flash_last_step = False
            self._last_met_step = -1

        def do_stop():
            self._stop_playback(save=True)

        def do_loop():
            self.is_looping = not self.is_looping
            self._save_to_store()

        def do_clear():
            self._push_history('clear')
            self.active_cells.clear()
            self.notes_v2.clear()
            self._clear_selection()
            self._stop_playback(save=False)
            self.start_step = 0
            self.total_steps = int(self.BAR_STEPS)
            self._save_to_store()

        def do_met_toggle():
            self.is_met_on = not self.is_met_on
            MET.set_enabled(self.is_met_on)
            MET.set_volume(self.met_tick_vol, self.met_tock_vol)
            self._save_to_store()

        def do_tempo_minus():
            step = 5 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1
            _apply_new_bpm(self.tempo_bpm - step)

        def do_tempo_plus():
            step = 5 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1
            _apply_new_bpm(self.tempo_bpm + step)

        # Manual hit-test για Clear/Play/Stop/Loop (μοιράζει early-return)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.btn_clear.rect.collidepoint(mx, my):
                self._ui_click_in_progress = True
                self._mouse_down_cell = None
                self._drag_started = False
                do_clear(); return next_state
            if self.btn_play.rect.collidepoint(mx, my):
                self._ui_click_in_progress = True
                self._mouse_down_cell = None
                self._drag_started = False
                do_play();  return next_state
            if self.btn_stop.rect.collidepoint(mx, my):
                self._ui_click_in_progress = True
                self._mouse_down_cell = None
                self._drag_started = False
                do_stop();  return next_state
            if self.btn_loop.rect.collidepoint(mx, my):
                self._ui_click_in_progress = True
                self._mouse_down_cell = None
                self._drag_started = False
                do_loop();  return next_state

        # Widgets
        self.btn_met.handle_event(event, do_met_toggle)
        self.btn_tempo_minus.handle_event(event, do_tempo_minus)
        self.btn_tempo_plus.handle_event(event, do_tempo_plus)

        # Snap cycle
        def _snap_cycle():
            self.snap_idx = (self.snap_idx + 1) % len(self.snap_options)
            self.snap_steps, self.snap_label = self.snap_options[self.snap_idx]
            self.btn_snap.text = f"Snap {self.snap_label}"
            self._save_to_store()
        self.btn_snap.handle_event(event, _snap_cycle)

        # Undo/Redo buttons
        def do_undo():
            self._undo()
        def do_redo():
            self._redo_do()
        self.btn_undo.handle_event(event, do_undo)
        self.btn_redo.handle_event(event, do_redo)

        # --- Keyboard shortcuts ---
        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            ctrl_held = bool(mods & pygame.KMOD_CTRL)

            if event.key == pygame.K_SPACE and not ctrl_held:
                if self.is_playing:
                    do_stop()
                else:
                    do_play()
                return next_state

            # Undo / Redo
            if ctrl_held and event.key == pygame.K_z:
                if self._undo(): return next_state
            if ctrl_held and event.key == pygame.K_y:
                if self._redo_do(): return next_state
            if ctrl_held and (mods & pygame.KMOD_SHIFT) and event.key == pygame.K_z:
                if self._redo_do(): return next_state

            # Toggle Snap
            if event.key == pygame.K_s:
                self.snap_enabled = not self.snap_enabled
                self._save_to_store()
                return next_state

            # Prev/Next Snap
            if event.key == pygame.K_LEFTBRACKET:   # [
                self.snap_idx = (self.snap_idx - 1) % len(self.snap_options)
                self.snap_steps, self.snap_label = self.snap_options[self.snap_idx]
                self.btn_snap.text = f"Snap {self.snap_label}"
                self._save_to_store()
                return next_state
            if event.key == pygame.K_RIGHTBRACKET:  # ]
                self.snap_idx = (self.snap_idx + 1) % len(self.snap_options)
                self.snap_steps, self.snap_label = self.snap_options[self.snap_idx]
                self.btn_snap.text = f"Snap {self.snap_label}"
                self._save_to_store()
                return next_state

            # Delete (επιλογή ή νότα κάτω από κέρσορα)
            if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                if self.sel_ids:
                    self._push_history('delete-selection')
                    ids_to_del = set(self.sel_ids)
                    self.notes_v2 = [n for n in self.notes_v2 if n['id'] not in ids_to_del]
                    self._recalc_total_steps()
                    self._save_to_store()
                    self._clear_selection()
                    return next_state
                hover = self._get_hover_cell()
                if hover:
                    r, s = hover
                    note = self._note_at(r, s)
                    if note:
                        self._push_history('delete-hover')
                        self._delete_note(note['id'])
                        if note['id'] in self.sel_ids:
                            self.sel_ids.discard(note['id'])
                            if not self.sel_ids:
                                self._clear_selection()
                return next_state

            # Ctrl + Up / Ctrl + Down  -> οκτάβα
            if ctrl_held and event.key in (pygame.K_UP, pygame.K_DOWN):
                ids = self._ids_or_hover()
                if ids:
                    self._push_history('octave')
                    direction = +1 if event.key == pygame.K_DOWN else -1
                    self._transpose_octave(ids, direction)
                return next_state

            # Arrow keys χωρίς Ctrl -> nudge κατά snap unit
            if not ctrl_held and event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                ids = self._ids_or_hover()
                if ids:
                    self._push_history('nudge')
                    drow = 0
                    dstep = 0
                    q = int(self.snap_steps)
                    step_unit = q if self._snap_is_active() else 1
                    if event.key == pygame.K_LEFT:
                        dstep = -step_unit
                    elif event.key == pygame.K_RIGHT:
                        dstep = +step_unit
                    elif event.key == pygame.K_UP:
                        drow  = -1
                    elif event.key == pygame.K_DOWN:
                        drow  = +1
                    self._move_ids(ids, drow=drow, dstep=dstep, clamp_left=True, clamp_rows=True)
                return next_state

            # Ctrl + A : Select All
            if ctrl_held and event.key == pygame.K_a:
                ids = {n['id'] for n in self.notes_v2}
                self.sel_ids = ids
                self.sel_bbox = self._compute_bbox_for_ids(ids)
                self.sel_bbox_last = self.sel_bbox
                self.sel_flash_ids = set(ids)
                self.sel_flash_until = pygame.time.get_ticks() + 400
                return next_state

            # Ctrl + C : Copy
            if ctrl_held and event.key == pygame.K_c:
                self._clipboard_copy_from_selection()
                return next_state

            # Ctrl + X : Cut
            if ctrl_held and event.key == pygame.K_x:
                if self._clipboard_copy_from_selection():
                    self._push_history('cut')
                    ids_to_del = set(self.sel_ids)
                    self.notes_v2 = [n for n in self.notes_v2 if n['id'] not in ids_to_del]
                    self._recalc_total_steps()
                    self._save_to_store()
                    self.sel_ids.clear()
                    self.sel_flash_ids.clear()
                    self.sel_active = False
                    self.sel_rect = None
                return next_state

            # Ctrl + V : Paste
            if ctrl_held and event.key == pygame.K_v:
                mx, my = pygame.mouse.get_pos()
                target = None
                if self._grid_rect.collidepoint(mx, my):
                    row_in_view = (my - self.header_h) // self.row_h
                    row0 = self.top_row + int(row_in_view)
                    rel_x = mx - self._grid_rect.x
                    step0 = self.start_step + int(rel_x // max(1, self.step_w))
                    target = (max(0, min(len(self.notes)-1, row0)), max(0, step0))
                elif self.sel_bbox:
                    r0, r1, s0, s1 = self.sel_bbox
                    target = (r0, s0)
                elif self.sel_bbox_last:
                    r0, r1, s0, s1 = self.sel_bbox_last
                    target = (r0, s0)
                else:
                    target = (self.top_row, self.start_step)
                self._push_history('paste')
                self._clipboard_paste_at(*target)
                self._save_to_store()
                return next_state

            # Esc: clear selection
            if event.key == pygame.K_ESCAPE:
                self._clear_selection()
                return next_state

        # ---------- Wheel (Zoom / Resize) ----------
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            ctrl = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)
            # Ctrl + ροδέλα πάνω από grid -> resize νότας
            if ctrl and self._grid_rect.collidepoint(mx, my):
                row_in_view = (my - self.header_h) // self.row_h
                row_idx = self.top_row + int(row_in_view)
                if 0 <= row_idx < len(self.notes):
                    rel_x = mx - self._grid_rect.x
                    step_idx = self.start_step + int(rel_x // max(1, self.step_w))
                    note = self._note_at(row_idx, step_idx)
                    if note:
                        self._push_history('resize-wheel')
                        q = int(self.snap_steps)
                        delta_units = q if self._snap_is_active() else 1
                        delta = (1 if event.y > 0 else -1) * delta_units
                        note['length'] = max(1, note['length'] + delta)
                        self._recalc_total_steps()
                        self._save_to_store()
                        return next_state
            # Ctrl πάνω από οριζόντιο scrollbar -> οριζόντιο zoom (σταδιακό & ασφαλές)
            if self._h_scroll_track_rect.collidepoint(mx, my) and ctrl:
                factor = 1.1 if event.y > 0 else (1 / 1.1)
                self._zoom_horizontal_at(mx, factor)
                return next_state
            # Κάθετος scrollbar -> κάθετο zoom
            if self._scroll_track_rect.collidepoint(mx, my):
                factor = 1.1 if event.y > 0 else (1 / 1.1)
                self._zoom_vertical_at(my, factor)
                return next_state
            # Κανονικό κάθετο scroll
            self.top_row -= event.y
            self._clamp_top()
            return next_state

        # ---------- Mouse Down ----------
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            self._mouse_down_in_grid = False

            if event.button == 1:
                # Vertical scrollbar
                track = self._scroll_track_rect
                if track.collidepoint(mx, my):
                    self._ui_click_in_progress = True
                    thumb = self._scroll_thumb(track)
                    if thumb.collidepoint(mx, my):
                        self.dragging_scroll = True
                        self._drag_offset = my - thumb.y
                    else:
                        target_y = my - thumb.height // 2
                        self._set_top_from_thumb_y(target_y, track)
                    return next_state

                # Horizontal scrollbar
                htrack = self._h_scroll_track_rect
                if htrack.collidepoint(mx, my):
                    self._ui_click_in_progress = True
                    self.dragging_hscroll = True
                    ht = self._h_scroll_thumb(htrack, max(1, (self._grid_rect.width // max(1, self.step_w))))
                    self._drag_offset = mx - ht.x
                    return next_state

                # Tempo slider
                track_t = self._tempo_slider_track
                thumb_t = self._tempo_thumb_rect
                if track_t.width > 0 and (track_t.collidepoint(mx, my) or thumb_t.collidepoint(mx, my)):
                    self._ui_click_in_progress = True
                    self.dragging_tempo = True
                    if not thumb_t.collidepoint(mx, my):
                        new_bpm = self._thumb_x_to_tempo(mx, track_t)
                        self.tempo_bpm = new_bpm
                        self.tempo_pv = bpm_to_pvalue(self.tempo_bpm)
                        self._recompute_step_ms()
                        self.last_step_time = float(pygame.time.get_ticks())
                        self._save_to_store()
                    else:
                        self._tempo_drag_offset = mx - thumb_t.x
                    return next_state

            # Ctrl + LeftDown στο grid: START selection drag
            if event.button == 1 and self._grid_rect.collidepoint(mx, my) and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                if self.sel_ids:
                    self._clear_selection()
                row_in_view = (my - self.header_h) // self.row_h
                row0 = self.top_row + int(row_in_view)
                rel_x = mx - self._grid_rect.x
                step0 = self.start_step + int(rel_x // max(1, self.step_w))
                row0  = max(0, min(len(self.notes) - 1, row0))
                step0 = max(0, step0)
                self.sel_anchor   = (row0, step0)
                self.sel_active   = True
                self.sel_dragging = True
                self.sel_rect     = (row0, row0, step0, step0)
                self._mouse_down_cell = None
                self._mouse_down_in_grid = False
                return next_state

            # Right click delete (κρατάμε selection εκτός των διαγραμμένων ids)
            if event.button == 3 and self._grid_rect.collidepoint(mx, my):
                self._ui_click_in_progress = False
                row_in_view = (my - self.header_h) // self.row_h
                row_idx = self.top_row + int(row_in_view)
                if 0 <= row_idx < len(self.notes):
                    rel_x = mx - self._grid_rect.x
                    step_idx = self.start_step + int(rel_x // max(1, self.step_w))
                    note = self._note_at(row_idx, step_idx)
                    if note:
                        self._push_history('delete-rclick')
                        self._delete_note(note['id'])
                        if note['id'] in self.sel_ids:
                            self.sel_ids.discard(note['id'])
                            self.sel_flash_ids.discard(note['id'])
                            if not self.sel_ids:
                                self._clear_selection()
                return next_state

            # LeftDown χωρίς Ctrl: group‑drag αν σε επιλεγμένη, αλλιώς single‑drag/placement
            if event.button == 1 and self._grid_rect.collidepoint(mx, my) and not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self._ui_click_in_progress = False
                
                if self.dbg_latency:
                    self._dbg_t0_ms = pygame.time.get_ticks()

                row_in_view = (my - self.header_h) // self.row_h
                row_idx = self.top_row + int(row_in_view)
                if 0 <= row_idx < len(self.notes):
                    rel_x = mx - self._grid_rect.x
                    step_idx = self.start_step + int(rel_x // max(1, self.step_w))
                    self._mouse_down_cell = (row_idx, step_idx)
                    self._mouse_down_in_grid = True
                    hit = self._note_at(row_idx, step_idx)
                    if hit and (hit['id'] in self.sel_ids):
                        self.group_dragging = True
                        self._group_drag_start_cell = (row_idx, step_idx)
                        self.group_drag_ids = set(self.sel_ids)
                        self._group_drag_snapshot = { n['id']: (n['row'], n['start']) for n in self.notes_v2 if n['id'] in self.group_drag_ids }
                        self._group_drag_min_start = min(start for (_row, start) in self._group_drag_snapshot.values()) if self._group_drag_snapshot else 0
                        self._drag_started = False
                        return next_state
                    if self.sel_ids:
                        self._clear_selection()
                    if hit:
                        self._drag_note_id = hit['id']
                        self._drag_note_pick_offset = step_idx - hit['start']
                        self._drag_note_src_row = hit['row']
                        self._drag_note_src_start = hit['start']
                        self._drag_started = False
                    else:
                        self._drag_note_id = None
                        self._drag_started = False
                return next_state

        # ---------- Mouse Up ----------
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # σταμάτα τυχόν drags
            self.dragging_scroll = False
            self.dragging_hscroll = False
            self.dragging_tempo = False
            self._drag_offset = 0
            self._tempo_drag_offset = 0

            if self._ui_click_in_progress:
                self._ui_click_in_progress = False
                self._mouse_down_cell = None
                self._mouse_down_in_grid = False
                self._drag_started = False
                self._drag_hist_armed = False
                return next_state

            # SELECTION DRAG finalize
            if self.sel_dragging:
                self.sel_dragging = False
                ids = set()
                if self.sel_rect:
                    r0, r1, s0, s1 = self.sel_rect
                    for n in self.notes_v2:
                        if r0 <= n['row'] <= r1:
                            ns, ne = n['start'], n['start'] + n['length'] - 1
                            if not (ne < s0 or ns > s1):
                                ids.add(n['id'])
                self.sel_ids = ids
                self.sel_active = False
                self.sel_bbox = self._compute_bbox_for_ids(self.sel_ids)
                self.sel_bbox_last = self.sel_bbox
                self.sel_rect = None
                self.sel_flash_ids = set(ids)
                self.sel_flash_until = pygame.time.get_ticks() + 700
                self._drag_hist_armed = False
                return next_state

            # GROUP DRAG finalize
            if self.group_dragging:
                self.group_dragging = False
                self._group_drag_start_cell = None
                self._group_drag_snapshot.clear()
                self._drag_started = False
                self._drag_hist_armed = False
                self._save_to_store()
                return next_state

            # Placement ΜΟΝΟ αν το down είχε ξεκινήσει στο grid & δεν έγινε drag
            if self._mouse_down_cell and not self._drag_started:
                if self._mouse_down_in_grid and self._grid_rect.collidepoint(event.pos):
                    r, s = self._mouse_down_cell
                    if self._note_at(r, s) is None:
                        self._push_history('place')
                        s = self._quantize_step(s, mode='floor')
                        q = int(self.snap_steps)
                        default_len = max(1, q if self._snap_is_active() else 1)
                        self._add_note(r, s, default_len)
                        note_label = self.notes[r]
                        midi_note = self._note_label_to_midi(note_label)
                        
                        ch = self._slot_channel()
                        play_note(midi_note, velocity=110, channel=ch)

                        
                        # --- measure UI->trigger latency ---
                        if self.dbg_latency and self._dbg_t0_ms is not None:
                            self._dbg_ui_to_trigger_ms = pygame.time.get_ticks() - self._dbg_t0_ms
                            self._dbg_t0_ms = None

                        tail = self._tail_seconds()
                        threading.Timer(0.25 + tail, lambda nn=midi_note, cc=ch: stop_note(nn, channel=cc)).start()

            # καθάρισμα state single-drag
            self._mouse_down_cell = None
            self._mouse_down_in_grid = False
            self._drag_note_id = None
            self._drag_started = False
            self._drag_hist_armed = False
            self._save_to_store()
            return next_state

        if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            return next_state

        # ---------- Mouse Move ----------
        if event.type == pygame.MOUSEMOTION and self.dragging_scroll:
            track = self._scroll_track_rect
            new_thumb_y = event.pos[1] - self._drag_offset
            self._set_top_from_thumb_y(new_thumb_y, track)
            return next_state

        if event.type == pygame.MOUSEMOTION and self.dragging_hscroll:
            htrack = self._h_scroll_track_rect
            mx = event.pos[0]
            vis_steps_guess = max(1, (self._grid_rect.width // self.step_w))
            new_thumb_x = mx - self._drag_offset
            self._set_start_from_thumb_x(new_thumb_x, htrack, vis_steps_guess)
            return next_state

        if event.type == pygame.MOUSEMOTION and self.dragging_tempo:
            mx = event.pos[0]
            track_t = self._tempo_slider_track
            target_x = mx - (self._tempo_drag_offset if self._tempo_drag_offset else 0)
            new_bpm = self._thumb_x_to_tempo(target_x, track_t)
            if new_bpm != self.tempo_bpm:
                self.tempo_bpm = new_bpm
                self.tempo_pv = bpm_to_pvalue(self.tempo_bpm)
                self._recompute_step_ms()
                self.last_step_time = float(pygame.time.get_ticks())
                self._save_to_store()
            return next_state

        # Selection rectangle live update
        if event.type == pygame.MOUSEMOTION and self.sel_dragging:
            mx, my = event.pos
            if not self._grid_rect.collidepoint(mx, my):
                return next_state
            row_in_view = (my - self.header_h) // self.row_h
            row1 = self.top_row + int(row_in_view)
            rel_x = mx - self._grid_rect.x
            step1 = self.start_step + int(rel_x // max(1, self.step_w))
            r0, s0 = self.sel_anchor
            r1 = max(0, min(len(self.notes) - 1, row1))
            s1 = max(0, step1)
            self.sel_rect = (min(r0, r1), max(r0, r1), min(s0, s1), max(s0, s1))
            self.sel_active = True
            return next_state

        # Left-drag move (single note)
        if event.type == pygame.MOUSEMOTION and self._drag_note_id is not None and self._mouse_down_cell is not None:
            mx, my = event.pos
            if not self._grid_rect.collidepoint(mx, my):
                return next_state
            row_in_view = (my - self.header_h) // self.row_h
            target_row = self.top_row + int(row_in_view)
            rel_x = mx - self._grid_rect.x
            step_idx = self.start_step + int(rel_x // max(1, self.step_w))
            row0, step0 = self._mouse_down_cell
            if not self._drag_started and (target_row != row0 or step_idx != step0):
                self._drag_started = True
                if not self._drag_hist_armed:
                    self._push_history('drag-start-single')
                    self._drag_hist_armed = True
            if self._drag_started:
                note = next((n for n in self.notes_v2 if n['id'] == self._drag_note_id), None)
                if note:
                    new_start = max(0, step_idx - self._drag_note_pick_offset)
                    new_start = self._quantize_step(new_start, mode='floor')
                    note['row'] = max(0, min(len(self.notes) - 1, target_row))
                    note['start'] = new_start
                    self._recalc_total_steps()
            return next_state

        # GROUP DRAG (selection by ids)
        if event.type == pygame.MOUSEMOTION and self.group_dragging and self._group_drag_start_cell is not None:
            mx, my = event.pos
            if not self._grid_rect.collidepoint(mx, my):
                return next_state
            row_in_view = (my - self.header_h) // self.row_h
            target_row = self.top_row + int(row_in_view)
            rel_x = mx - self._grid_rect.x
            step_idx = self.start_step + int(rel_x // max(1, self.step_w))
            row0, step0 = self._group_drag_start_cell
            if not self._drag_started and (target_row != row0 or step_idx != step0):
                self._drag_started = True
                if not self._drag_hist_armed:
                    self._push_history('drag-start-group')
                    self._drag_hist_armed = True
            if self._drag_started:
                drow = target_row - row0
                snapped_target = self._quantize_step(step_idx, mode='round')
                dstep = snapped_target - step0
                # clamp προς τα αριστερά
                min_dstep = -int(self._group_drag_min_start)
                if dstep < min_dstep:
                    dstep = min_dstep
                for n in self.notes_v2:
                    if n['id'] in self.group_drag_ids:
                        src_row, src_start = self._group_drag_snapshot[n['id']]
                        n['row'] = max(0, min(len(self.notes) - 1, src_row + drow))
                        n['start'] = max(0, src_start + dstep)
                self._recalc_total_steps()
            return next_state

        return next_state

    # --------------------- draw ---------------------
    def draw(self, screen: pygame.Surface):
        w, h = screen.get_width(), screen.get_height()
        self._last_height = h
        self._layout_body(w, h)
        self._layout_header(w, h)
        if not self._centered_once:
            vis_tmp = self.visible_rows
            max_top = max(0, len(self.notes) - vis_tmp)
            mid_idx = len(self.notes) // 2
            self.top_row = max(0, min(max_top, mid_idx - vis_tmp // 2))
            self._centered_once = True

        screen.fill(BG_COLOR)

        # Header
        header_rect = self._header_rect
        pygame.draw.rect(screen, (32, 32, 32), header_rect)
        pygame.draw.line(screen, GRID_COLOR, (0, header_rect.bottom - 1), (w, header_rect.bottom - 1))
        self.back_btn.draw(screen)
        self.btn_met.draw(screen)
        if self.is_met_on:
            pygame.draw.rect(screen, (0, 150, 255), self.btn_met.rect, 3)
        label_surf = self.font.render("BPM:", True, TEXT_LIGHT)
        y_mid = header_rect.centery
        label_pos = (self.btn_met.rect.right + 20, y_mid - label_surf.get_height() // 2)
        screen.blit(label_surf, label_pos)
        pygame.draw.rect(screen, (70, 70, 70), self._tempo_slider_track)
        pygame.draw.rect(screen, (150, 150, 150), self._tempo_thumb_rect, border_radius=2)
        self.btn_tempo_minus.rect = self._minus_rect
        self.btn_tempo_plus.rect  = self._plus_rect
        self.btn_tempo_minus.draw(screen)
        self.btn_tempo_plus.draw(screen)

        
        # if self.dbg_latency and self._dbg_ui_to_trigger_ms is not None:
        #     txt = f"UI→Trig: {self._dbg_ui_to_trigger_ms} ms"
        #     surf = self.font.render(txt, True, (200, 200, 200))
        #     screen.blit(surf, (w - surf.get_width() - 12, 12))

        val_text = f"{int(self.tempo_bpm)}"
        val_surf = self.font.render(val_text, True, TEXT_LIGHT)
        val_pos = (self._plus_rect.right + 10, y_mid - val_surf.get_height() // 2)
        screen.blit(val_surf, val_pos)

        # Snap & Undo/Redo buttons
        self.btn_snap.text = f"Snap {self.snap_label}"
        self.btn_snap.draw(screen)
        self.btn_undo.draw(screen)
        self.btn_redo.draw(screen)

        # Προαιρετικό disabled look (όταν δεν έχει ιστορικό)
        can_undo = len(self._hist) > 1
        can_redo = len(self._redo) > 0
        if not can_undo:
            overlay = pygame.Surface(self.btn_undo.rect.size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 90))
            screen.blit(overlay, self.btn_undo.rect.topleft)
        if not can_redo:
            overlay = pygame.Surface(self.btn_redo.rect.size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 90))
            screen.blit(overlay, self.btn_redo.rect.topleft)

        # Utility buttons
        self.btn_clear.draw(screen)
        self.btn_play.draw(screen)
        self.btn_stop.draw(screen)
        self.btn_loop.draw(screen)
        if self.is_looping:
            pygame.draw.rect(screen, (255, 60, 60), self.btn_loop.rect, 3)
            dark = pygame.Surface(self.btn_loop.rect.size)
            dark.set_alpha(90)
            dark.fill((0, 0, 0))
            screen.blit(dark, self.btn_loop.rect.topleft)

        # Body
        grid_rect = self._grid_rect
        left_rect = pygame.Rect(0, self.header_h, self.left_w, h - self.header_h)
        screen.set_clip(pygame.Rect(0, self.header_h, w, h - self.header_h))

        vis = self.visible_rows
        start = self.top_row
        end = min(len(self.notes), start + vis)
        grid_rect_local = grid_rect

        for row, idx in enumerate(range(start, end)):
            y = self.header_h + row * self.row_h
            note = self.notes[idx]
            is_black = '#' in note
            if is_black:
                pygame.draw.rect(screen, (22, 22, 22), pygame.Rect(grid_rect_local.x, y, grid_rect_local.width, self.row_h))
                pygame.draw.rect(screen, (28, 28, 28), pygame.Rect(left_rect.x, y, left_rect.width, self.row_h))
            pygame.draw.line(screen, GRID_COLOR, (grid_rect_local.x, y), (grid_rect_local.right, y))
            note_label = self.font.render(note, True, TEXT_LIGHT)
            screen.blit(note_label, (left_rect.x + 6, y + (self.row_h - note_label.get_height()) // 2))
        bottom_y = grid_rect_local.bottom
        pygame.draw.line(screen, GRID_COLOR, (grid_rect_local.x, bottom_y), (grid_rect_local.right, bottom_y))

        cols = max(1, grid_rect_local.width // self.step_w)
        vis_steps = cols
        self._clamp_start(vis_steps)

        # Χρώματα για τις κάθετες γραμμές
        bar_color = (230, 205, 90)            # bar (λίγο πιο σκούρο κίτρινο)
        beat_color = (180, 180, 180)          # beat (γκρι)
        snap_color_rgba = (200, 200, 200, 80) # snap (ανοιχτό γκρι με alpha)

        # Overlay για snap lines
        overlay_h = bottom_y - self.header_h
        grid_overlay = pygame.Surface((grid_rect_local.width, overlay_h), pygame.SRCALPHA)

        # Bar/Beat lines (dominant)
        for c in range(vis_steps + 1):
            x_screen = grid_rect_local.x + c * self.step_w
            abs_step = self.start_step + c
            if (abs_step % int(self.BAR_STEPS)) == 0:
                pygame.draw.line(screen, bar_color, (x_screen, self.header_h), (x_screen, bottom_y), 3)
                # Bar number (1,2,3...) στην αρχή κάθε μέτρου
                bar_idx = (abs_step // int(self.BAR_STEPS)) + 1
                num_surf = self.font.render(str(bar_idx), True, (200, 200, 200))
                screen.blit(num_surf, (x_screen + 3, self.header_h + 3))
                continue
            if (abs_step % int(self.STEPS_PER_BEAT)) == 0:
                pygame.draw.line(screen, beat_color, (x_screen, self.header_h), (x_screen, bottom_y), 2)
                continue

        # Snap sub-lines: κάθε q steps (ακριβώς οι στήλες του quantize)
        if self._snap_is_active():
            q = int(self.snap_steps)
            for c in range(vis_steps + 1):
                abs_step = self.start_step + c
                if (abs_step % q) == 0:
                    x_local = (c * self.step_w)
                    pygame.draw.line(grid_overlay, snap_color_rgba, (x_local, 0), (x_local, overlay_h), 1)

        # Blend snap overlay
        screen.blit(grid_overlay, (grid_rect_local.x, self.header_h))

        # Νότες
        active_color       = (180, 0, 0)
        active_color_sel   = (220, 60, 60)
        active_color_flash = (255, 100, 100)
        border_color       = (120, 0, 0)
        now_ms = pygame.time.get_ticks()
        flashing = now_ms < self.sel_flash_until

        def _draw_note_block(n):
            row_idx = n['row']
            if not (start <= row_idx < end):
                return
            row = row_idx - start
            y = self.header_h + row * self.row_h
            run_start = n['start']
            run_end   = n['start'] + n['length'] - 1
            vis_start = self.start_step
            vis_end   = self.start_step + vis_steps - 1
            if run_end < vis_start or run_start > vis_end:
                return
            draw_start = max(run_start, vis_start)
            draw_end   = min(run_end, vis_end)
            x = grid_rect_local.x + (draw_start - self.start_step) * self.step_w
            w_block = (draw_end - draw_start + 1) * self.step_w
            rect_w = max(1, w_block - 2)
            rect = pygame.Rect(x + 1, y + 1, rect_w, self.row_h - 2)
            if rect.left < grid_rect_local.right and rect.right > grid_rect_local.left:
                rect.width = min(rect.width, grid_rect_local.right - rect.x - 1)
                if flashing and (n['id'] in self.sel_flash_ids):
                    col = active_color_flash
                elif n['id'] in self.sel_ids:
                    col = active_color_sel
                else:
                    col = active_color
                pygame.draw.rect(screen, col, rect)
                pygame.draw.rect(screen, border_color, rect, 1)

        # Προτεραιότητα σε νότα που γίνεται resize με Ctrl
        resizing_note_id = None
        mods = pygame.key.get_mods()
        if (mods & pygame.KMOD_CTRL):
            mx, my = pygame.mouse.get_pos()
            if self._grid_rect.collidepoint(mx, my):
                row_in_view = (my - self.header_h) // self.row_h
                row_idx = self.top_row + int(row_in_view)
                if 0 <= row_idx < len(self.notes):
                    rel_x = mx - self._grid_rect.x
                    step_idx = self.start_step + int(rel_x // max(1, self.step_w))
                    hit_note = self._note_at(row_idx, step_idx)
                    if hit_note:
                        resizing_note_id = hit_note['id']

        if resizing_note_id is not None:
            n = next((nn for nn in self.notes_v2 if nn['id'] == resizing_note_id), None)
            if n:
                _draw_note_block(n)
        for n in reversed(self.notes_v2):
            if resizing_note_id is not None and n['id'] == resizing_note_id:
                continue
            _draw_note_block(n)

        # Selection rectangle ONLY while dragging
        if self.sel_dragging and self.sel_active and self.sel_rect:
            r0, r1, s0, s1 = self.sel_rect
            vis_r0, vis_r1 = self.top_row, self.top_row + vis - 1
            vis_s0, vis_s1 = self.start_step, self.start_step + vis_steps - 1
            dr0, dr1 = max(r0, vis_r0), min(r1, vis_r1)
            ds0, ds1 = max(s0, vis_s0), min(s1, vis_s1)
            if dr0 <= dr1 and ds0 <= ds1:
                x = grid_rect_local.x + (ds0 - self.start_step) * self.step_w
                y = self.header_h + (dr0 - self.top_row) * self.row_h
                w_sel = (ds1 - ds0 + 1) * self.step_w
                h_sel = (dr1 - dr0 + 1) * self.row_h
                sel_surf = pygame.Surface((w_sel, h_sel), pygame.SRCALPHA)
                sel_surf.fill((0, 180, 255, 40))
                pygame.draw.rect(sel_surf, (0, 180, 255), sel_surf.get_rect(), 2)
                screen.blit(sel_surf, (x, y))

        # Scrollbars
        scroll_track = self._scroll_track_rect
        pygame.draw.rect(screen, (40, 40, 40), scroll_track)
        thumb = self._scroll_thumb(scroll_track)
        pygame.draw.rect(screen, (120, 120, 120), thumb)
        pygame.draw.rect(screen, (40, 40, 40), self._h_scroll_track_rect)
        ht = self._h_scroll_thumb(self._h_scroll_track_rect, vis_steps)
        pygame.draw.rect(screen, (120, 120, 120), ht)
        self._h_scroll_thumb_rect = ht

        # Sequencer
        if self.is_playing:
            now = float(pygame.time.get_ticks())
            while now - float(self.last_step_time) >= float(self.step_ms):
                self.last_step_time = float(self.last_step_time) + float(self.step_ms)
                max_end = max((n['start'] + n['length'] for n in self.notes_v2), default=0)
                content_len = max_end
                if self.is_looping:
                    loop_len = self.BAR_STEPS if content_len <= 0 else ((content_len + self.BAR_STEPS - 1) // self.BAR_STEPS) * self.BAR_STEPS
                else:
                    loop_len = max(1, content_len)
                if not self.is_looping and self.current_step >= loop_len:
                    self.display_step = max(0, loop_len - 1)
                    self._flash_last_step = True
                    self.is_playing = False
                    break
                else:
                    self.display_step = self.current_step
                    if self.is_met_on and self._last_met_step != self.display_step:
                        pos_in_bar = self.display_step % self.BAR_STEPS
                        beat_step = int(self.STEPS_PER_BEAT)
                        if pos_in_bar == 0:
                            MET.play_tick()
                        elif pos_in_bar in (beat_step, beat_step*2, beat_step*3):
                            MET.play_tock()
                        self._last_met_step = self.display_step
                    starts = [n for n in self.notes_v2 if n['start'] == self.display_step]
                    for n in starts:
                        note_label = self.notes[n['row']]
                        midi_note = self._note_label_to_midi(note_label)
                        ch = self._slot_channel()
                        play_note(midi_note, velocity=110, channel=ch)
                        duration_sec = max(0.01, (n['length'] * float(self.step_ms)) / 1000.0)
                        tail = self._tail_seconds()
                        threading.Timer(duration_sec + tail, lambda nn=midi_note, cc=ch: stop_note(nn, channel=cc)).start()
                    if self.is_looping:
                        self.current_step = (self.current_step + 1) % max(1, loop_len)
                    else:
                        self.current_step += 1

        # Step highlight
        if self.is_playing or self._flash_last_step:
            if self.start_step <= self.display_step < self.start_step + vis_steps:
                step_x = self._grid_rect.x + (self.display_step - self.start_step) * self.step_w
            else:
                step_x = None
            if step_x is not None and step_x < self._grid_rect.right:
                highlight = pygame.Surface((self.step_w, (self._last_height - self.header_h) - self.hscroll_h))
                highlight.set_alpha(60)
                highlight.fill((0, 120, 255))
                screen.blit(highlight, (step_x, self.header_h))
            if self._flash_last_step and not self.is_playing:
                self._flash_last_step = False

        if self.current_note != "" and pygame.time.get_ticks() >= self._note_reset_at:
            self.current_note = ""
        note_lbl_surf = self.font_header.render(str(self.current_note), True, TEXT_LIGHT)
        screen.blit(note_lbl_surf, note_lbl_surf.get_rect(center=(w // 2, self._header_rect.centery)))
        screen.set_clip(pygame.Rect(0, 0, w, h))
