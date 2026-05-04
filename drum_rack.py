# screens/drum_rack.py
# Drum Rack (1/16 grid)
# ------------------------------------------------------------
# Περιλαμβάνει:
# - Οριζόντιο scrollbar & zoom με Ctrl+ροδέλα (grid/μπάρα)
# - Box-selection (Ctrl+Drag) με μπλε ορθογώνιο, highlight ΜΟΝΟ ενεργών pads (live)
# - Left click: σε κενό -> place+preview+select, σε υπάρχον -> select / group-drag αν είναι ήδη selected
# - Right click: σε υπάρχον -> delete (undoable), σε κενό -> preview
# - Ctrl+C / Ctrl+X / Ctrl+V
# - Nudge επιλογής με βελάκια
# - Group-drag selection (collision-safe)
# - Undo/Redo (κουμπιά & Ctrl+Z / Ctrl+Y / Shift+Ctrl+Z)
# - Playback: σταματά/λουπάρει στο ΠΡΩΤΟ bar boundary ΜΕΤΑ το τέλος περιεχομένου
# - Auto-extend: μεγαλώνει το grid όταν χρειάζεται
# - Playhead στήλη μόνο όταν παίζει
# - Header buttons: ARM on MouseDown, FIRE on MouseUp (ακυρώνεται αν αφήσεις εκτός)
# - Click-through guard για Πίσω
# - BPM slider λειτουργικό (click + drag)
# - Layout: Rack κεντραρισμένο οριζόντια ΚΑΙ κάθετα (κενό background πάνω/κάτω)
# - Οπτικά: rounded rack, διακριτική σκιά, zebra rows, beat shading, bar ruler

import math
import threading
import pygame

from settings.colors import (
    BG_COLOR, GRID_COLOR, TEXT_LIGHT, TEXT_DARK,
    BUTTON_BG, BUTTON_BORDER
)
from UI.widgets import Button
from UI.layout import back_button_rect
from settings.selections import INSTRUMENT_DATA
from settings.drum_kits import DRUM_KITS, DRUM_CHANNEL

from tools.audio_engine import all_notes_off, apply_slot_effects, set_preset, play_note, stop_note
import tools.metronome as MET


class DrumRackScreen:
    BEATS_PER_BAR = 4
    STEPS_PER_BEAT = 4
    STEPS_PER_BAR = BEATS_PER_BAR * STEPS_PER_BEAT

    TEMPO_CORR = 0.9972376

    def __init__(self, index: int):
        self.index = index

        # --- Debug latency (UI -> play_note) ---
        self.dbg_latency = True
        self._dbg_t0_ms = None
        self._dbg_ui_to_trigger_ms = None

        # --- Layout ---
        self.header_h = 48
        self.left_w = 220
        self.row_h = 28
        self.hscroll_h = 18

        # column width (zoom)
        self.step_w = 24
        self.step_w_min, self.step_w_max = 8, 72

        # κεντραρισμένο rack
        self.content_max_w = 1200
        self.content_min_grid_w = 320
        self._content_rect = pygame.Rect(0, 0, 0, 0)
        self._left_panel_rect = pygame.Rect(0, 0, 0, 0)

        # cosmetics
        self.ui_corner = 8
        self.ui_shadow_alpha = 70
        self.ui_beat_band_alpha = 18
        self.ui_zebra_alpha = 12
        self.ui_ruler = True

        # fonts
        self.font = pygame.font.Font(None, 18)
        self.font_small = pygame.font.Font(None, 18)
        self.font_header = pygame.font.Font(None, 28)

        # rects
        self._grid_rect = pygame.Rect(0, 0, 0, 0)
        self._h_scroll_track_rect = pygame.Rect(0, 0, 0, 0)
        self._header_rect = pygame.Rect(0, 0, 0, 0)

        # tempo UI rects
        self._tempo_slider_track = pygame.Rect(0, 0, 0, 0)
        self._tempo_thumb_rect = pygame.Rect(0, 0, 12, 12)
        self._minus_rect = pygame.Rect(0, 0, 0, 0)
        self._plus_rect = pygame.Rect(0, 0, 0, 0)
        self._bpm_val_pos = (0, 0)

        # hscroll drag
        self._h_scroll_dragging = False
        self._h_scroll_drag_dx = 0

        # tempo drag
        self._dragging_tempo = False
        self._tempo_drag_offset = 0

        # header button arming (fire on mouse up)
        self._armed_btn = None
        self._armed_cb = None

        # --- Header Buttons ---
        self.back_btn = Button(back_button_rect(), BUTTON_BG, BUTTON_BORDER, "Πίσω", self.font_small, TEXT_DARK)
        self.btn_met = Button(pygame.Rect(0, 0, 36, 30), BUTTON_BG, (30, 30, 30), "Met", self.font_small, TEXT_DARK)
        self.btn_tempo_minus = Button(pygame.Rect(0, 0, 24, 24), BUTTON_BG, (30, 30, 30), "−", self.font_small, TEXT_DARK)
        self.btn_tempo_plus = Button(pygame.Rect(0, 0, 24, 24), BUTTON_BG, (30, 30, 30), "+", self.font_small, TEXT_DARK)

        self.btn_kit_prev = Button(pygame.Rect(0, 0, 30, 30), BUTTON_BG, BUTTON_BORDER, "<", self.font_small, TEXT_DARK)
        self.btn_kit_next = Button(pygame.Rect(0, 0, 30, 30), BUTTON_BG, BUTTON_BORDER, ">", self.font_small, TEXT_DARK)

        self.btn_clear = Button(pygame.Rect(0, 0, 70, 30), (100, 100, 100), (30, 30, 30), "Clear", self.font_small, TEXT_LIGHT)
        self.btn_play = Button(pygame.Rect(0, 0, 70, 30), (0, 180, 0), (30, 30, 30), "Play", self.font_small, TEXT_DARK)
        self.btn_stop = Button(pygame.Rect(0, 0, 70, 30), (180, 0, 0), (30, 30, 30), "Stop", self.font_small, TEXT_LIGHT)
        self.btn_loop = Button(pygame.Rect(0, 0, 70, 30), (200, 140, 0), (30, 30, 30), "Loop", self.font_small, TEXT_DARK)

        self.btn_undo = Button(pygame.Rect(0, 0, 26, 26), BUTTON_BG, BUTTON_BORDER, "<-", self.font_small, TEXT_DARK)
        self.btn_redo = Button(pygame.Rect(0, 0, 26, 26), BUTTON_BG, BUTTON_BORDER, "->", self.font_small, TEXT_DARK)

        # --- Undo/Redo stacks ---
        self.HIST_LIMIT = 20
        self._hist = []
        self._redo = []

        # --- Tempo / Metronome ---
        self.tempo_min, self.tempo_max = 40, 200
        self.tempo_bpm = 120

        self.is_met_on = False
        self._last_met_step = -1
        self.met_tick_vol = 0.9
        self.met_tock_vol = 0.6
        MET.set_enabled(self.is_met_on)
        MET.set_volume(self.met_tick_vol, self.met_tock_vol)
        self.met_delay_ms = 30

        self.is_playing = False
        self.is_looping = False
        self.last_step_time = 0.0
        self.current_step = 0
        self.display_step = 0

        # --- Master rows (σταθερό grid ανεξάρτητα από kit) ---
        try:
            self._master_row_count = max(len(v.get("rows", [])) for v in DRUM_KITS.values()) if DRUM_KITS else 0
        except Exception:
            self._master_row_count = 0
        if self._master_row_count <= 0:
            self._master_row_count = 8  # fallback

# --- Kit / Pattern ---
        self._init_kit_and_pattern_from_store()
        self.total_steps = max(16, int(INSTRUMENT_DATA.get(self.index, {}).get("drum_rack", {}).get("total_steps", 64)))
        self.start_col = 0

        # --- Selection ---
        self.sel_active = False
        self.sel_dragging = False
        self.sel_anchor = (0, 0)
        self.sel_rect = None
        self.sel_cells = set()

        # Clipboard
        self.clipboard = {'cells': [], 'w': 0, 'h': 0}
        self._last_copy_anchor = None

        # Group drag (collision-safe)
        self.group_dragging = False
        self._group_drag_start_cell = None
        self._group_drag_snapshot = set()
        self._group_drag_last_applied = set()
        self._group_drag_painted = {}

        self._recompute_step_ms()

        # baseline history
        self._hist.clear(); self._redo.clear()
        self._push_history('init-baseline')

    # ==================== Utilities ====================
    @staticmethod
    def _ellipsis(text: str, font: pygame.font.Font, max_w: int) -> str:
        if font.size(text)[0] <= max_w:
            return text
        dots = "..."
        w_dots = font.size(dots)[0]
        if w_dots >= max_w:
            return dots
        s = text
        while s and font.size(s)[0] + w_dots > max_w:
            s = s[:-1]
        return s + dots

    # ==================== Load / Save ====================
    def _slot(self):
        return INSTRUMENT_DATA.setdefault(self.index, {})

    def _init_kit_and_pattern_from_store(self):
        slot = self._slot()
        kit_names = list(DRUM_KITS.keys()) if DRUM_KITS else ["Default"]
        kit_name = slot.get("kit_name", kit_names[0])
        if kit_name not in DRUM_KITS and kit_names:
            kit_name = kit_names[0]
        self.kit_names = kit_names
        self.kit_idx = self.kit_names.index(kit_name) if kit_name in self.kit_names else 0
        kit = DRUM_KITS[self.kit_names[self.kit_idx]]
        kit_rows = list(kit["rows"])
        # pad σε σταθερό πλήθος γραμμών ώστε το pattern να μένει οπτικά ίδιο
        self.rows = list(kit_rows)
        if hasattr(self, '_master_row_count') and self._master_row_count > 0:
            if len(self.rows) < self._master_row_count:
                self.rows += [(None, '')] * (self._master_row_count - len(self.rows))
            else:
                # ΔΕΝ κόβουμε (κρατάμε max count ως master)
                pass
        self.rows_midi = [n for (n, _l) in self.rows]
        self.rows_labels = [_l for (_n, _l) in self.rows]


        dr = slot.get("drum_rack", {})
        saved_rows = dr.get("drum_rows")
        saved_pat = dr.get("pattern")

        if saved_pat and saved_rows and len(saved_pat) == len(saved_rows):
            note2idx = {n: i for i, (n, _l) in enumerate(self.rows)}
            total_steps = max(16, max((len(r) for r in saved_pat), default=64))
            new_pat = [[0] * total_steps for _ in range(len(self.rows))]
            for i, midi in enumerate(saved_rows):
                midi = None if midi == -1 else midi
                if midi in note2idx:
                    r = note2idx[midi]
                    row_vals = list(saved_pat[i])
                    row_vals += [0] * max(0, total_steps - len(row_vals))
                    new_pat[r] = row_vals[:total_steps]
            self.pattern = new_pat
        else:
            self.pattern = [[0] * int(getattr(self, 'total_steps', 64)) for _ in range(len(self.rows))]

        self.tempo_bpm = int(dr.get("tempo_bpm", self.tempo_bpm))
        self.is_looping = bool(dr.get("is_looping", False))
        self.is_met_on = bool(dr.get("met_on", False))
        MET.set_enabled(self.is_met_on)
        self.met_delay_ms = int(dr.get("met_delay_ms", getattr(self, "met_delay_ms", 30)))

        slot["instrument"] = "Drums"
        slot["preset"] = self.kit_names[self.kit_idx]
        slot["kit_name"] = self.kit_names[self.kit_idx]
        slot["bank"] = int(kit["bank"])
        slot["program"] = int(kit["program"])
        slot["channel"] = int(DRUM_CHANNEL)

        try:
            set_preset(int(kit["bank"]), int(kit["program"]), channel=DRUM_CHANNEL)
            apply_slot_effects(self.index)
        except Exception:
            pass

    def _save_to_store(self):
        slot = self._slot()
        kit = DRUM_KITS[self.kit_names[self.kit_idx]]
        dr = slot.setdefault("drum_rack", {})
        dr.update({
            "kit_name": self.kit_names[self.kit_idx],
            "bank": int(kit["bank"]),
            "program": int(kit["program"]),
            "drum_rows": [(-1 if n is None else int(n)) for (n, _l) in self.rows],
            "pattern": [list(r) for r in self.pattern],
            "tempo_bpm": int(self.tempo_bpm),
            "is_looping": bool(self.is_looping),
            "met_on": bool(self.is_met_on),
            "total_steps": int(self.total_steps),
            "met_delay_ms": int(self.met_delay_ms),
        })
        slot["instrument"] = "Drums"
        slot["preset"] = self.kit_names[self.kit_idx]
        slot["kit_name"] = self.kit_names[self.kit_idx]
        slot["bank"] = int(kit["bank"])
        slot["program"] = int(kit["program"])
        slot["channel"] = int(DRUM_CHANNEL)

    def _stop_playback(self, save: bool = False):
        self.is_playing = False
        self.current_step = 0
        self.display_step = 0
        self._last_met_step = -1
        all_notes_off(channel=DRUM_CHANNEL)
        if save:
            self._save_to_store()

    # ==================== Tempo helpers ====================
    def _recompute_step_ms(self):
        eff_bpm = float(self.tempo_bpm) * float(self.TEMPO_CORR)
        self.step_ms = 60000.0 / (eff_bpm * self.STEPS_PER_BEAT)

    def _tempo_to_thumb_x(self, track_rect: pygame.Rect) -> int:
        t = max(self.tempo_min, min(self.tempo_max, float(self.tempo_bpm)))
        ratio = (t - self.tempo_min) / (self.tempo_max - self.tempo_min)
        return int(track_rect.x + ratio * track_rect.width)

    def _thumb_x_to_tempo(self, thumb_x: int, track_rect: pygame.Rect) -> int:
        thumb_x = max(track_rect.x, min(track_rect.right, thumb_x))
        ratio = (thumb_x - track_rect.x) / max(1, track_rect.width)
        t = int(round(self.tempo_min + ratio * (self.tempo_max - self.tempo_min)))
        return max(self.tempo_min, min(self.tempo_max, t))

    def _met_after(self, fn):
        delay = max(0, int(getattr(self, "met_delay_ms", 0))) / 1000.0
        if delay <= 0:
            fn()
        else:
            threading.Timer(delay, fn).start()

    # ==================== Undo / Redo ====================
    def _snapshot_state(self):
        return {
            'pattern': [list(row) for row in self.pattern],
            'sel_cells': set(self.sel_cells),
            'total_steps': int(self.total_steps),
            'start_col': int(self.start_col),
        }

    def _apply_state(self, st: dict):
        self.total_steps = int(st.get('total_steps', self.total_steps))
        self.start_col = int(st.get('start_col', self.start_col))
        patt = st.get('pattern')
        if patt is not None:
            rows = min(len(self.rows), len(patt))
            new_pat = [[0] * self.total_steps for _ in range(len(self.rows))]
            for r in range(rows):
                row_vals = list(patt[r])
                if len(row_vals) < self.total_steps:
                    row_vals += [0] * (self.total_steps - len(row_vals))
                new_pat[r] = row_vals[:self.total_steps]
            self.pattern = new_pat
        self.sel_cells = set(st.get('sel_cells', set()))
        self._clamp_start_col()
        self._save_to_store()

    def _push_history(self, label: str = ''):
        self._hist.append(self._snapshot_state())
        if len(self._hist) > self.HIST_LIMIT:
            self._hist.pop(0)
        self._redo.clear()

    def _undo(self) -> bool:
        if len(self._hist) <= 1:
            return False
        self._redo.append(self._snapshot_state())
        prev = self._hist.pop()
        self._apply_state(prev)
        return True

    def _redo_do(self) -> bool:
        if not self._redo:
            return False
        self._hist.append(self._snapshot_state())
        nxt = self._redo.pop()
        self._apply_state(nxt)
        return True

    # ==================== Scroll & Zoom helpers ====================
    def _visible_cols(self) -> int:
        return max(1, self._grid_rect.width // max(1, self.step_w))

    def _clamp_start_col(self):
        vis = self._visible_cols()
        max_start = max(0, self.total_steps - vis)
        if self.start_col < 0:
            self.start_col = 0
        if self.start_col > max_start:
            self.start_col = max_start

    def _h_scroll_thumb(self, track: pygame.Rect) -> pygame.Rect:
        vis = self._visible_cols()
        total = max(1, self.total_steps)
        if total <= vis or track.width <= 0:
            return pygame.Rect(track.x, track.y, track.width, track.height)
        ratio = vis / total
        thumb_w = max(24, int(track.width * ratio))
        max_start = max(0, total - vis)
        self._clamp_start_col()
        x = int(track.x + (track.width - thumb_w) * (self.start_col / max_start)) if max_start > 0 else track.x
        return pygame.Rect(x, track.y, thumb_w, track.height)

    def _set_start_from_thumb_x(self, thumb_x: int, track: pygame.Rect):
        vis = self._visible_cols()
        total = max(1, self.total_steps)
        if total <= vis:
            self.start_col = 0
            return
        thumb = self._h_scroll_thumb(track)
        travel = max(1, track.width - thumb.width)
        pos_ratio = max(0.0, min(1.0, (thumb_x - track.x) / travel))
        max_start = max(0, total - vis)
        self.start_col = int(round(max_start * pos_ratio))
        self._clamp_start_col()

    def _zoom_horizontal_at(self, mx: int, factor: float) -> None:
        old_w = int(self.step_w)
        new_w = int(round(max(self.step_w_min, min(self.step_w_max, old_w * factor))))
        if new_w == old_w:
            return
        grid = self._grid_rect
        if grid.width <= 0:
            self.step_w = new_w
            return
        cursor_rel = max(0, mx - grid.x)
        col_at_cursor = self.start_col + int(cursor_rel // max(1, old_w))
        self.step_w = new_w
        new_col_under_mouse = int(cursor_rel // max(1, new_w))
        self.start_col = col_at_cursor - new_col_under_mouse
        self._clamp_start_col()

    def _row_at(self, my: int) -> int:
        return int((my - self._grid_rect.y) // self.row_h)

    # ==================== Content & Auto-extend ====================
    def _content_length(self) -> int:
        max_c = -1
        if len(self.pattern) > 0:
            limit = max(0, min(len(self.pattern[0]), self.total_steps))
            for r in range(len(self.pattern)):
                row = self.pattern[r]
                for c in range(limit):
                    if row[c] == 1 and c > max_c:
                        max_c = c
        return 0 if max_c < 0 else (max_c + 1)

    def _compute_loop_len(self) -> int:
        content_len = self._content_length()
        if content_len <= 0:
            return self.STEPS_PER_BAR
        bars = int(math.ceil(content_len / float(self.STEPS_PER_BAR)))
        return max(1, bars * self.STEPS_PER_BAR)

    def _ensure_total_steps(self, needed: int):
        if needed <= self.total_steps:
            return
        for r in range(len(self.pattern)):
            row = self.pattern[r]
            if len(row) < needed:
                row.extend([0] * (needed - len(row)))
        self.total_steps = needed
        self._clamp_start_col()
        self._save_to_store()

    # ==================== Clipboard ====================
    def _sel_bbox(self):
        if not self.sel_cells:
            return None
        rs = [r for (r, _c) in self.sel_cells]
        cs = [c for (_r, c) in self.sel_cells]
        return (min(rs), max(rs), min(cs), max(cs))

    def _clipboard_copy_from_selection(self) -> bool:
        if not self.sel_cells:
            return False
        r0, r1, c0, c1 = self._sel_bbox()
        cells = []
        for (r, c) in sorted(self.sel_cells):
            cells.append({'drow': r - r0, 'dcol': c - c0})
        self.clipboard = {'cells': cells, 'w': (c1 - c0 + 1), 'h': (r1 - r0 + 1)}
        self._last_copy_anchor = (r0, c0)
        return True

    def _clipboard_paste_at(self, target_row0: int, target_col0: int) -> bool:
        if not self.clipboard.get('cells'):
            return False
        max_needed = target_col0
        for item in self.clipboard['cells']:
            c = target_col0 + item['dcol']
            if c > max_needed:
                max_needed = c
        self._ensure_total_steps(max_needed + 1)

        new_sel = set()
        for item in self.clipboard['cells']:
            r = target_row0 + item['drow']
            c = target_col0 + item['dcol']
            if 0 <= r < len(self.rows) and 0 <= c < self.total_steps:
                self.pattern[r][c] = 1
                new_sel.add((r, c))
        if not new_sel:
            return False
        self.sel_cells = new_sel
        self._save_to_store()
        return True

    # ==================== Group Drag (collision-safe) ====================
    def _start_group_drag(self, start_cell):
        self._push_history('drag-start-group')
        self.group_dragging = True
        self._group_drag_start_cell = start_cell
        self._group_drag_snapshot = set(self.sel_cells)
        self._group_drag_last_applied = set(self.sel_cells)
        self._group_drag_painted = {}

    def _apply_group_drag(self, target_cell):
        if not self.group_dragging or not self._group_drag_start_cell:
            return
        (r0, c0) = self._group_drag_start_cell
        (rt, ct) = target_cell
        drow = rt - r0
        dcol = ct - c0
        if not self._group_drag_snapshot:
            return

        rows = [r for (r, _c) in self._group_drag_snapshot]
        cols = [c for (_r, c) in self._group_drag_snapshot]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)

        drow = max(drow, -min_r)
        drow = min(drow, (len(self.rows) - 1) - max_r)
        dcol = max(dcol, -min_c)

        new_max_c = max_c + dcol
        if new_max_c >= self.total_steps:
            self._ensure_total_steps(new_max_c + 1)

        for (r, c) in self._group_drag_last_applied:
            if (r, c) in self._group_drag_snapshot:
                self.pattern[r][c] = 0
            else:
                prev_val = self._group_drag_painted.get((r, c))
                if prev_val == 0:
                    self.pattern[r][c] = 0

        new_sel = set()
        painted_now = {}
        for (r, c) in self._group_drag_snapshot:
            nr, nc = r + drow, c + dcol
            if 0 <= nr < len(self.rows) and 0 <= nc < self.total_steps:
                prev_val = self.pattern[nr][nc]
                painted_now[(nr, nc)] = prev_val
                self.pattern[nr][nc] = 1
                new_sel.add((nr, nc))

        self.sel_cells = new_sel
        self._group_drag_last_applied = new_sel
        self._group_drag_painted = painted_now

    def _end_group_drag(self):
        self.group_dragging = False
        self._group_drag_start_cell = None
        self._group_drag_snapshot.clear()
        self._group_drag_last_applied = set()
        self._group_drag_painted = {}
        self._save_to_store()

    # ==================== Events ====================
    def handle_event(self, event):
        next_state = None
        # (disabled) old click-through guard removed: buttons now fire on MouseUp

        # ensure layout is current for hit tests
        try:
            screen = pygame.display.get_surface()
            if screen:
                w, h = screen.get_width(), screen.get_height()
                self._layout_header(w, h)
                self._layout_body(w, h)
        except Exception:
            pass

        # --- callbacks ---
        def go_back():
            nonlocal next_state
            self._stop_playback(save=True)
            next_state = f"instrument {self.index}"

        
        # --- Back button (use standard Button logic, fire on release) ---
        self.back_btn.handle_event(event, go_back)
        if next_state and isinstance(next_state, str) and next_state.startswith('instrument'):
            # αποφυγή click-through στο επόμενο screen
            pygame.event.clear([pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP])
            return next_state

        def do_met():
            self.is_met_on = not self.is_met_on
            MET.set_enabled(self.is_met_on)
            self._save_to_store()

        def apply_new_bpm(new_bpm: int):
            self.tempo_bpm = int(max(self.tempo_min, min(self.tempo_max, new_bpm)))
            self._recompute_step_ms()
            self.last_step_time = float(pygame.time.get_ticks())
            self._save_to_store()

        def cycle_kit(direction: int):
            # Αλλαγή kit: ΔΕΝ πειράζουμε το pattern (μένει σταθερό). Απλά αλλάζουμε τα visible όργανα/labels.
            self.kit_idx = (self.kit_idx + direction) % len(self.kit_names)
            kit = DRUM_KITS[self.kit_names[self.kit_idx]]
            kit_rows = list(kit["rows"])
            self.rows = list(kit_rows)
            if hasattr(self, '_master_row_count') and self._master_row_count > 0:
                if len(self.rows) < self._master_row_count:
                    self.rows += [(None, '')] * (self._master_row_count - len(self.rows))
            self.rows_midi = [n for (n, _l) in self.rows]
            self.rows_labels = [_l for (_n, _l) in self.rows]
            # εξασφάλισε ότι το pattern έχει τόσες γραμμές όσες το master
            if len(self.pattern) < len(self.rows):
                self.pattern += [[0] * self.total_steps for _ in range(len(self.rows) - len(self.pattern))]
            elif len(self.pattern) > len(self.rows):
                # δεν κόβουμε· κρατάμε το pattern ως έχει (οι έξτρα γραμμές παραμένουν αποθηκευμένες)
                pass
            self.sel_cells.clear()


            try:
                set_preset(int(kit["bank"]), int(kit["program"]), channel=DRUM_CHANNEL)
            except Exception:
                pass

            # ---- SYNC kit selection to global slot data (hub + picker) ----
            slot = INSTRUMENT_DATA.setdefault(self.index, {})
            kit_name = self.kit_names[self.kit_idx]
            kit = DRUM_KITS[kit_name]

            slot["instrument"] = "Drums"
            slot["preset"] = kit_name        # αυτό θα δείχνει το hub (Drums + kit)
            slot["kit_name"] = kit_name      # αυτό θα χρησιμοποιεί ο instrument_picker
            slot["bank"] = int(kit["bank"])  # συνήθως 128
            slot["program"] = int(kit["program"])
            slot["channel"] = int(DRUM_CHANNEL)
            apply_slot_effects(self.index)
            
            self._save_to_store()

        def do_clear():
            self._push_history('clear')
            for r in range(len(self.pattern)):
                for c in range(self.total_steps):
                    self.pattern[r][c] = 0
            self.sel_cells.clear()
            self._stop_playback(save=False)
            self._save_to_store()

        def do_play():
            kit = DRUM_KITS[self.kit_names[self.kit_idx]]
            set_preset(int(kit["bank"]), int(kit["program"]), channel=DRUM_CHANNEL)
            apply_slot_effects(self.index)
            self.is_playing = True
            self.current_step = 0
            self.display_step = 0
            self.last_step_time = float(pygame.time.get_ticks())

        def do_stop():
            self._stop_playback(save=True)

        def do_loop():
            self.is_looping = not self.is_looping
            self._save_to_store()

        def header_map():
            return [
                                (self.btn_met, do_met),
                (self.btn_tempo_minus, lambda: apply_new_bpm(self.tempo_bpm - (5 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1))),
                (self.btn_tempo_plus,  lambda: apply_new_bpm(self.tempo_bpm + (5 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1))),
                (self.btn_kit_prev,    lambda: cycle_kit(-1)),
                (self.btn_kit_next,    lambda: cycle_kit(+1)),
                (self.btn_clear, do_clear),
                (self.btn_play,  do_play),
                (self.btn_stop,  do_stop),
                (self.btn_loop,  do_loop),
                (self.btn_undo,  self._undo),
                (self.btn_redo,  self._redo_do),
            ]

        # -------- Header buttons: ARM on MouseDown --------
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # Αν είναι στο tempo slider, μην οπλίζεις κουμπιά
            if self._tempo_thumb_rect.collidepoint(mx, my) or self._tempo_slider_track.collidepoint(mx, my):
                pass
            else:
                for btn, cb in header_map():
                    if btn.rect.collidepoint(mx, my):
                        self._armed_btn = btn
                        self._armed_cb = cb
                        return next_state

        # -------- Header buttons: FIRE on MouseUp --------
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            mx, my = event.pos
            if self._armed_btn is not None:
                btn = self._armed_btn
                cb = self._armed_cb
                self._armed_btn = None
                self._armed_cb = None

                if btn.rect.collidepoint(mx, my):
                    cb()
                    return next_state

        # ---------------- Tempo slider (click + drag) ----------------
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self._tempo_thumb_rect.collidepoint(mx, my):
                self._dragging_tempo = True
                self._tempo_drag_offset = mx - self._tempo_thumb_rect.centerx
                return next_state
            if self._tempo_slider_track.collidepoint(mx, my):
                self._dragging_tempo = True
                self._tempo_drag_offset = 0
                apply_new_bpm(self._thumb_x_to_tempo(mx, self._tempo_slider_track))
                return next_state

        if event.type == pygame.MOUSEMOTION and self._dragging_tempo:
            mx, my = event.pos
            apply_new_bpm(self._thumb_x_to_tempo(mx - self._tempo_drag_offset, self._tempo_slider_track))
            return next_state

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._dragging_tempo:
            self._dragging_tempo = False
            self._tempo_drag_offset = 0
            return next_state

        # ---- BOX SELECTION (Ctrl + Drag) ----
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self._grid_rect.collidepoint(mx, my) and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self.sel_cells.clear()
                row0 = self._row_at(my)
                if 0 <= row0 < len(self.rows):
                    rel_x = mx - self._grid_rect.x
                    col0 = self.start_col + int(rel_x // max(1, self.step_w))
                    if col0 < 0:
                        col0 = 0
                    self.sel_anchor = (row0, col0)
                    self.sel_dragging = True
                    self.sel_active = True
                    self.sel_rect = (row0, row0, col0, col0)

                return next_state

        if event.type == pygame.MOUSEMOTION and self.sel_dragging:
            mx, my = event.pos
            if self._grid_rect.collidepoint(mx, my):
                row1 = self._row_at(my)
                rel_x = mx - self._grid_rect.x
                col1 = self.start_col + int(rel_x // max(1, self.step_w))
                row1 = max(0, min(len(self.rows) - 1, row1))
                col1 = max(0, col1)
                r0, c0 = self.sel_anchor
                self.sel_rect = (min(r0, row1), max(r0, row1), min(c0, col1), max(c0, col1))
                self.sel_active = True

                rr0, rr1, cc0, cc1 = self.sel_rect
                new_sel = set()
                for r in range(rr0, rr1 + 1):
                    for c in range(max(0, cc0), min(cc1, self.total_steps - 1) + 1):
                        if 0 <= r < len(self.rows) and self.pattern[r][c] == 1:
                            new_sel.add((r, c))
                self.sel_cells = new_sel
            return next_state

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.sel_dragging:
            self.sel_dragging = False
            self.sel_active = False
            self.sel_rect = None
            return next_state

        # ---- Grid clicks: place/select/delete & group-drag ----
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3) and self._grid_rect.collidepoint(*event.pos):
            mx, my = event.pos

            # Debug: UI->trigger starts at the beginning of grid click handling
            if self.dbg_latency:
                self._dbg_t0_ms = pygame.time.get_ticks()
            row_idx = self._row_at(my)
            if 0 <= row_idx < len(self.rows):
                rel_x = mx - self._grid_rect.x
                desired = self.start_col + int(rel_x // max(1, self.step_w))
                if desired < 0:
                    desired = 0

                if event.button == 3:
                    if desired < self.total_steps and self.pattern[row_idx][desired] == 1:
                        self._push_history('delete-rclick')
                        self.pattern[row_idx][desired] = 0
                        self.sel_cells.discard((row_idx, desired))
                        self._save_to_store()
                    else:
                        midi = self.rows_midi[row_idx]
                        if midi is not None:
                            play_note(midi, velocity=110, channel=DRUM_CHANNEL)

                        if midi is not None:
                            threading.Timer(0.2, lambda: stop_note(midi, channel=DRUM_CHANNEL)).start()
                    return next_state

                if event.button == 1 and not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    if desired >= self.total_steps:
                        self._ensure_total_steps(desired + 1)

                    if self.pattern[row_idx][desired] == 0:
                        self._push_history('place')
                        self.pattern[row_idx][desired] = 1
                        self._save_to_store()
                        midi = self.rows_midi[row_idx]
                        if midi is not None:
                            play_note(midi, velocity=110, channel=DRUM_CHANNEL)

                        if midi is not None:
                            threading.Timer(0.2, lambda: stop_note(midi, channel=DRUM_CHANNEL)).start()
                        self.sel_cells = {(row_idx, desired)}
                    else:
                        if (row_idx, desired) in self.sel_cells:
                            self._start_group_drag((row_idx, desired))
                        else:
                            self.sel_cells = {(row_idx, desired)}
                    return next_state

        # Group-drag live
        if event.type == pygame.MOUSEMOTION and self.group_dragging and self._group_drag_start_cell is not None:
            mx, my = event.pos
            if self._grid_rect.collidepoint(mx, my):
                row_idx = self._row_at(my)
                rel_x = mx - self._grid_rect.x
                desired = self.start_col + int(rel_x // max(1, self.step_w))
                row_idx = max(0, min(len(self.rows) - 1, row_idx))
                if desired < 0:
                    desired = 0
                self._apply_group_drag((row_idx, desired))
            return next_state

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.group_dragging:
            self._end_group_drag()
            return next_state

        # ---- Horizontal scrollbar ----
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self._h_scroll_track_rect.collidepoint(*event.pos):
            mx, my = event.pos
            thumb = self._h_scroll_thumb(self._h_scroll_track_rect)
            if thumb.collidepoint(mx, my):
                self._h_scroll_dragging = True
                self._h_scroll_drag_dx = mx - thumb.x
            else:
                self._set_start_from_thumb_x(mx - thumb.width // 2, self._h_scroll_track_rect)
            return next_state

        if event.type == pygame.MOUSEMOTION and self._h_scroll_dragging:
            mx, _ = event.pos
            self._set_start_from_thumb_x(mx - (self._h_scroll_drag_dx if self._h_scroll_drag_dx else 0), self._h_scroll_track_rect)
            return next_state

        if event.type == pygame.MOUSEBUTTONUP and self._h_scroll_dragging and event.button == 1:
            self._h_scroll_dragging = False
            self._h_scroll_drag_dx = 0
            return next_state

        # ---- Wheel: Ctrl + Wheel για zoom ----
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            ctrl = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)
            if ctrl and (self._h_scroll_track_rect.collidepoint(mx, my) or self._grid_rect.collidepoint(mx, my)):
                factor = 1.1 if event.y > 0 else (1 / 1.1)
                self._zoom_horizontal_at(mx, factor)
                return next_state

        # ---- Keyboard shortcuts ----
        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            ctrl_held = bool(mods & pygame.KMOD_CTRL)

            if ctrl_held and event.key == pygame.K_z:
                self._undo(); return next_state
            if ctrl_held and event.key == pygame.K_y:
                self._redo_do(); return next_state
            if ctrl_held and (mods & pygame.KMOD_SHIFT) and event.key == pygame.K_z:
                self._redo_do(); return next_state

            if ctrl_held and event.key == pygame.K_a:
                sel = set()
                for r in range(len(self.rows)):
                    row = self.pattern[r]
                    for c in range(min(self.total_steps, len(row))):
                        if row[c] == 1:
                            sel.add((r, c))
                self.sel_cells = sel
                return next_state

            if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                if self.sel_cells:
                    self._push_history('delete-selection')
                    for (r, c) in list(self.sel_cells):
                        if 0 <= r < len(self.rows) and 0 <= c < self.total_steps:
                            self.pattern[r][c] = 0
                    self.sel_cells.clear()
                    self._save_to_store()
                    return next_state

                mx, my = pygame.mouse.get_pos()
                if self._grid_rect.collidepoint(mx, my):
                    row_idx = self._row_at(my)
                    if 0 <= row_idx < len(self.rows):
                        rel_x = mx - self._grid_rect.x
                        desired = self.start_col + int(rel_x // max(1, self.step_w))
                        if 0 <= desired < self.total_steps and self.pattern[row_idx][desired] == 1:
                            self._push_history('delete-hover')
                            self.pattern[row_idx][desired] = 0
                            self.sel_cells.discard((row_idx, desired))
                            self._save_to_store()
                return next_state

            if ctrl_held and event.key == pygame.K_c:
                self._clipboard_copy_from_selection(); return next_state

            if ctrl_held and event.key == pygame.K_x:
                if self._clipboard_copy_from_selection():
                    self._push_history('cut')
                    for (r, c) in list(self.sel_cells):
                        if 0 <= r < len(self.rows) and 0 <= c < self.total_steps:
                            self.pattern[r][c] = 0
                    self.sel_cells.clear()
                    self._save_to_store()
                return next_state

            if ctrl_held and event.key == pygame.K_v:
                mx, my = pygame.mouse.get_pos()
                if self._grid_rect.collidepoint(mx, my):
                    row0 = self._row_at(my)
                    col0 = self.start_col + int((mx - self._grid_rect.x) // max(1, self.step_w))
                    target = (max(0, min(len(self.rows) - 1, row0)), max(0, col0))
                elif self._last_copy_anchor:
                    target = self._last_copy_anchor
                else:
                    target = (0, 0)
                self._push_history('paste')
                self._clipboard_paste_at(*target)
                return next_state

            if self.sel_cells and event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                drow = (event.key == pygame.K_DOWN) - (event.key == pygame.K_UP)
                dcol = (event.key == pygame.K_RIGHT) - (event.key == pygame.K_LEFT)
                rows = [r for (r, _c) in self.sel_cells]
                cols = [c for (_r, c) in self.sel_cells]
                min_r, max_r = min(rows), max(rows)
                min_c, max_c = min(cols), max(cols)

                drow = max(drow, -min_r)
                drow = min(drow, (len(self.rows) - 1) - max_r)
                dcol = max(dcol, -min_c)

                new_max = max_c + dcol
                if new_max >= self.total_steps:
                    self._ensure_total_steps(new_max + 1)

                self._push_history('nudge')
                old = set(self.sel_cells)
                for (r, c) in old:
                    self.pattern[r][c] = 0
                new_sel = set()
                for (r, c) in old:
                    nr, nc = r + drow, c + dcol
                    if 0 <= nr < len(self.rows) and 0 <= nc < self.total_steps:
                        self.pattern[nr][nc] = 1
                        new_sel.add((nr, nc))
                self.sel_cells = new_sel
                self._save_to_store()
                return next_state

            if event.key == pygame.K_SPACE:
                if self.is_playing:
                    self._stop_playback(save=True)
                else:
                    do_play()
                return next_state

        return next_state

    # ==================== Draw ====================
    def draw(self, screen: pygame.Surface):
        w, h = screen.get_width(), screen.get_height()
        self._layout_header(w, h)
        self._layout_body(w, h)

        screen.fill(BG_COLOR)

        # Header
        pygame.draw.rect(screen, (32, 32, 32), self._header_rect)
        pygame.draw.line(screen, GRID_COLOR, (0, self._header_rect.bottom - 1), (w, self._header_rect.bottom - 1))

        self.back_btn.draw(screen)
        self.btn_met.draw(screen)
        if self.is_met_on:
            pygame.draw.rect(screen, (0, 150, 255), self.btn_met.rect, 3)

        # BPM slider
        pygame.draw.rect(screen, (70, 70, 70), self._tempo_slider_track)
        pygame.draw.rect(screen, (150, 150, 150), self._tempo_thumb_rect)


        # if self.dbg_latency and self._dbg_ui_to_trigger_ms is not None:
        #     txt = f"UI→Trig: {self._dbg_ui_to_trigger_ms} ms"
        #     surf = self.font.render(txt, True, (200, 200, 200))
        #     screen.blit(surf, (w - surf.get_width() - 12, 12))
            
        self.btn_tempo_minus.rect = self._minus_rect
        self.btn_tempo_plus.rect = self._plus_rect
        self.btn_tempo_minus.draw(screen)
        self.btn_tempo_plus.draw(screen)

        label_bpm = self.font.render("BPM:", True, TEXT_LIGHT)
        screen.blit(label_bpm, (self.btn_met.rect.right + 20, self._header_rect.centery - label_bpm.get_height() // 2))

        val_surf = self.font.render(f"{int(self.tempo_bpm)}", True, TEXT_LIGHT)
        screen.blit(val_surf, self._bpm_val_pos)

        # Undo/Redo
        self.btn_undo.draw(screen)
        self.btn_redo.draw(screen)
        if len(self._hist) <= 1:
            overlay = pygame.Surface(self.btn_undo.rect.size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 90))
            screen.blit(overlay, self.btn_undo.rect.topleft)
        if not self._redo:
            overlay = pygame.Surface(self.btn_redo.rect.size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 90))
            screen.blit(overlay, self.btn_redo.rect.topleft)

        # Kit arrows + label
        self.btn_kit_prev.draw(screen)
        self.btn_kit_next.draw(screen)

        kit_label = f"Kit: {self.kit_names[self.kit_idx]}"
        left_x = self.btn_kit_next.rect.right + 10
        right_x = self.btn_clear.rect.left - 10
        max_w = max(60, right_x - left_x)
        kit_label = self._ellipsis(kit_label, self.font, max_w)
        kit_surf = self.font.render(kit_label, True, TEXT_LIGHT)
        screen.blit(kit_surf, (left_x, self._header_rect.centery - kit_surf.get_height() // 2))

        # Transport
        self.btn_clear.draw(screen)
        self.btn_play.draw(screen)
        self.btn_stop.draw(screen)
        self.btn_loop.draw(screen)
        if self.is_looping:
            pygame.draw.rect(screen, (255, 60, 60), self.btn_loop.rect, 3)
            dim = pygame.Surface(self.btn_loop.rect.size, pygame.SRCALPHA)
            dim.fill((0, 0, 0, 90))
            screen.blit(dim, self.btn_loop.rect.topleft)

        # Rack shadow + bg
        if self.ui_shadow_alpha > 0:
            shadow_surf = pygame.Surface((self._content_rect.width, self._content_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(shadow_surf, (0, 0, 0, self.ui_shadow_alpha), shadow_surf.get_rect())
            screen.blit(shadow_surf, (self._content_rect.x + 3, self._content_rect.y + 3))

        pygame.draw.rect(screen, (26, 26, 26), self._content_rect)
        pygame.draw.rect(screen, (55, 55, 55), self._content_rect, 1)

        grid = self._grid_rect
        grid_y = grid.y
        vis_cols = self._visible_cols()
        step_w = max(1, self.step_w)

        # labels + grid bg
        for r, (_midi, lbl) in enumerate(self.rows):
            y = grid_y + r * self.row_h
            pygame.draw.rect(screen, (28, 28, 28), pygame.Rect(self._left_panel_rect.x, y, self.left_w, self.row_h))
            pygame.draw.rect(screen, (22, 22, 22), pygame.Rect(grid.x, y, grid.width, self.row_h))
            pygame.draw.line(screen, GRID_COLOR, (grid.x, y), (grid.right, y))
            text = self.font.render(lbl, True, TEXT_LIGHT)
            screen.blit(text, (self._left_panel_rect.x + 6, y + (self.row_h - text.get_height()) // 2))

        # zebra
        if self.ui_zebra_alpha > 0:
            for r in range(len(self.rows)):
                if r % 2 == 1:
                    y = grid_y + r * self.row_h
                    zebra = pygame.Surface((grid.width, self.row_h), pygame.SRCALPHA)
                    zebra.fill((255, 255, 255, self.ui_zebra_alpha))
                    screen.blit(zebra, (grid.x, y))

        # beat bands
        if self.ui_beat_band_alpha > 0 and step_w >= 6:
            band_h = len(self.rows) * self.row_h
            for c in range(vis_cols):
                abs_c = self.start_col + c
                if abs_c % self.STEPS_PER_BEAT == 0:
                    band = pygame.Surface((step_w, band_h), pygame.SRCALPHA)
                    band.fill((255, 255, 255, self.ui_beat_band_alpha))
                    screen.blit(band, (grid.x + c * step_w, grid_y))

        # vertical lines
        for c in range(vis_cols + 1):
            abs_c = self.start_col + c
            x = grid.x + c * step_w
            if abs_c % self.STEPS_PER_BAR == 0:
                pygame.draw.line(screen, (230, 205, 90), (x, grid_y), (x, grid.bottom), 3)
            elif abs_c % self.STEPS_PER_BEAT == 0:
                pygame.draw.line(screen, (180, 180, 180), (x, grid_y), (x, grid.bottom), 2)
            else:
                pygame.draw.line(screen, (70, 70, 70), (x, grid_y), (x, grid.bottom), 1)

        # ruler
        if self.ui_ruler:
            for c in range(vis_cols + 1):
                abs_c = self.start_col + c
                if abs_c % self.STEPS_PER_BAR == 0:
                    bar_idx = (abs_c // self.STEPS_PER_BAR) + 1
                    num = self.font_small.render(str(bar_idx), True, (200, 200, 200))
                    screen.blit(num, (grid.x + c * step_w + 3, grid_y + 3))

        pygame.draw.line(screen, GRID_COLOR, (grid.x, grid.bottom), (grid.right, grid.bottom))

        # selection live highlight
        live_rect_highlight = set()
        if self.sel_dragging and self.sel_active and self.sel_rect:
            r0, r1, c0, c1 = self.sel_rect
            for rr in range(r0, r1 + 1):
                for cc in range(c0, c1 + 1):
                    if 0 <= rr < len(self.rows) and 0 <= cc < self.total_steps and self.pattern[rr][cc] == 1:
                        live_rect_highlight.add((rr, cc))

        # pads
        pad_on = (180, 0, 0)
        pad_br = (120, 0, 0)
        sel_overlay_col = (255, 255, 255, 70)

        for r in range(len(self.rows)):
            y = grid_y + r * self.row_h + 2
            for c in range(vis_cols):
                abs_c = self.start_col + c
                if 0 <= abs_c < self.total_steps and self.pattern[r][abs_c] == 1:
                    rect = pygame.Rect(grid.x + c * step_w + 2, y, step_w - 4, self.row_h - 4)
                    pygame.draw.rect(screen, pad_on, rect)
                    pygame.draw.rect(screen, pad_br, rect, 1)
                    if (r, abs_c) in self.sel_cells or (r, abs_c) in live_rect_highlight:
                        sel_surf = pygame.Surface((step_w - 4, self.row_h - 4), pygame.SRCALPHA)
                        sel_surf.fill(sel_overlay_col)
                        screen.blit(sel_surf, (grid.x + c * step_w + 2, y))

        # selection rectangle
        if self.sel_dragging and self.sel_active and self.sel_rect:
            r0, r1, c0, c1 = self.sel_rect
            vis_r0, vis_r1 = 0, len(self.rows) - 1
            vis_c0, vis_c1 = self.start_col, self.start_col + vis_cols - 1
            dr0, dr1 = max(r0, vis_r0), min(r1, vis_r1)
            dc0, dc1 = max(c0, vis_c0), min(c1, vis_c1)
            if dr0 <= dr1 and dc0 <= dc1:
                x = grid.x + (dc0 - self.start_col) * step_w
                y = grid_y + dr0 * self.row_h
                w_sel = (dc1 - dc0 + 1) * step_w
                h_sel = (dr1 - dr0 + 1) * self.row_h
                sel_surf = pygame.Surface((w_sel, h_sel), pygame.SRCALPHA)
                sel_surf.fill((0, 180, 255, 40))
                pygame.draw.rect(sel_surf, (0, 180, 255), sel_surf.get_rect(), 2)
                screen.blit(sel_surf, (x, y))

        # advance sequencer
        self._advance_sequencer()

        # playhead only when playing
        if self.is_playing and self.start_col <= self.display_step < self.start_col + vis_cols:
            step_x = grid.x + (self.display_step - self.start_col) * step_w
            highlight = pygame.Surface((step_w, (len(self.rows) * self.row_h)), pygame.SRCALPHA)
            highlight.fill((0, 120, 255, 60))
            screen.blit(highlight, (step_x, grid_y))

        # scrollbar
        pygame.draw.rect(screen, (48, 48, 48), self._h_scroll_track_rect)
        ht = self._h_scroll_thumb(self._h_scroll_track_rect)
        pygame.draw.rect(screen, (175, 175, 175), ht)
        pygame.draw.rect(screen, (60, 60, 60), ht, 1)

    # ==================== Sequencer ====================
    def _advance_sequencer(self):
        if not self.is_playing:
            return

        loop_len = self._compute_loop_len()
        now = float(pygame.time.get_ticks())
        while now - float(self.last_step_time) >= float(self.step_ms):
            self.last_step_time = float(self.last_step_time) + float(self.step_ms)
            self.display_step = self.current_step

            if self.is_met_on and self._last_met_step != self.display_step:
                pos = self.display_step % self.STEPS_PER_BAR
                if pos == 0:
                    self._met_after(MET.play_tick)
                elif pos in (self.STEPS_PER_BEAT, 2 * self.STEPS_PER_BEAT, 3 * self.STEPS_PER_BEAT):
                    self._met_after(MET.play_tock)
                self._last_met_step = self.display_step

            col = self.display_step
            if 0 <= col < self.total_steps:
                for r, midi in enumerate(self.rows_midi):
                    if midi is None:
                        continue
                    if self.pattern[r][col] == 1:
                        play_note(midi, velocity=110, channel=DRUM_CHANNEL)

                        threading.Timer(0.05, lambda nn=midi: stop_note(nn, channel=DRUM_CHANNEL)).start()

            if self.is_looping:
                self.current_step = (self.current_step + 1) % loop_len
            else:
                self.current_step += 1
                if self.current_step >= loop_len:
                    self.is_playing = False
                    self.display_step = loop_len - 1
                    break

    # ==================== Layout ====================
    def _layout_header(self, w: int, h: int):
        self._header_rect = pygame.Rect(0, 0, w, self.header_h)
        cy = self._header_rect.centery

        # back + met
        self.back_btn.rect.topleft = (12, 8)
        self.btn_met.rect.topleft = (self.back_btn.rect.right + 10, cy - self.btn_met.rect.height // 2)

        # right transport
        clear_x = w - (4 * 75) - 35
        play_x = clear_x + 75
        stop_x = play_x + 75
        loop_x = stop_x + 75
        y_btn = cy - 15
        self.btn_clear.rect.topleft = (clear_x, y_btn)
        self.btn_play.rect.topleft = (play_x, y_btn)
        self.btn_stop.rect.topleft = (stop_x, y_btn)
        self.btn_loop.rect.topleft = (loop_x, y_btn)

        # BPM group
        pad = 10
        label_w, _ = self.font.size("BPM:")
        x_start = self.btn_met.rect.right + 20

        minus_r = pygame.Rect(x_start + label_w + pad, cy - 12, 24, 24)
        track_x = minus_r.right + pad

        reserve_right = 24 + 50 + 12 + (26 + 6 + 26) + 24 + (30 + 8 + 30) + 20
        max_track_w = max(110, (clear_x - reserve_right) - (minus_r.right + pad))
        track_w = min(170, max_track_w)

        track_r = pygame.Rect(track_x, cy - 3, track_w, 6)
        plus_r = pygame.Rect(track_r.right + pad, cy - 12, 24, 24)

        self._minus_rect = minus_r
        self._plus_rect = plus_r
        self._tempo_slider_track = track_r

        thumb_x = self._tempo_to_thumb_x(self._tempo_slider_track)
        self._tempo_thumb_rect = pygame.Rect(thumb_x - 6, cy - 6, 12, 12)

        bpm_str = str(int(self.tempo_bpm))
        val_w, val_h = self.font.size(bpm_str)
        val_x = plus_r.right + 10
        self._bpm_val_pos = (val_x, cy - val_h // 2)

        undo_x = val_x + val_w + 16
        undo_y = cy - self.btn_undo.rect.height // 2
        self.btn_undo.rect.topleft = (undo_x, undo_y)
        self.btn_redo.rect.topleft = (self.btn_undo.rect.right + 6, undo_y)

        y_kit = cy - 15
        self.btn_kit_prev.rect.topleft = (self.btn_redo.rect.right + 24, y_kit)
        self.btn_kit_next.rect.topleft = (self.btn_kit_prev.rect.right + 8, y_kit)

    def _layout_body(self, w: int, h: int):
        body_h = h - self.header_h

        # horizontal center
        min_content_w = self.left_w + self.content_min_grid_w
        target_w = min(self.content_max_w, max(min_content_w, w - 40))
        cx = (w - target_w) // 2

        # vertical center
        ideal_grid_h = len(self.rows) * self.row_h
        ideal_content_h = ideal_grid_h + self.hscroll_h

        if ideal_content_h <= body_h:
            top_y = self.header_h + (body_h - ideal_content_h) // 2
            grid_h = ideal_grid_h
        else:
            top_y = self.header_h
            grid_h = max(self.row_h, body_h - self.hscroll_h)

        self._content_rect = pygame.Rect(cx, top_y, target_w, grid_h + self.hscroll_h)
        self._left_panel_rect = pygame.Rect(cx, top_y, self.left_w, grid_h)
        self._grid_rect = pygame.Rect(cx + self.left_w, top_y, target_w - self.left_w, grid_h)
        self._h_scroll_track_rect = pygame.Rect(cx + self.left_w, top_y + grid_h, self._grid_rect.width, self.hscroll_h)
