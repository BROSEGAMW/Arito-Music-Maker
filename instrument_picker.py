import pygame
from settings.colors import (
    BG_COLOR, TEXT_LIGHT, TEXT_DARK, BUTTON_BG, BUTTON_BORDER,
    GRID_COLOR, BOX_COLOR, BOX_BORDER
)
from UI.layout import back_button_rect, outer_frame_rect
from UI.widgets import Button, draw_text_center
from settings.selections import INSTRUMENT_DATA

from settings.channels import SLOT_CHANNELS
from settings.drum_kits import DRUM_CHANNEL

from settings.soundfont_map import MAP
# ✅ προσθέσαμε apply_slot_effects
from tools.audio_engine import set_preset, play_note, stop_note, apply_slot_effects

import threading


class ListBox:
    def __init__(self, rect: pygame.Rect, items, item_h=45, scrollbar_w=10, font=None):
        self.rect = pygame.Rect(rect)
        self.items = list(items)
        self.selected = -1
        self.top = 0
        self.item_h = int(item_h)
        self.scrollbar_w = int(scrollbar_w)
        self.font = font or pygame.font.Font(None, 27)

    @property
    def visible_rows(self):
        return max(1, self.rect.height // self.item_h)

    def set_items(self, items):
        self.items = list(items)
        self.selected = -1
        self.top = 0

    def _clamp_top(self):
        max_top = max(0, len(self.items) - self.visible_rows)
        if self.top < 0:
            self.top = 0
        if self.top > max_top:
            self.top = max_top

    def _index_from_pos(self, pos):
        if not self.rect.collidepoint(pos):
            return -1
        row = (pos[1] - self.rect.y) // self.item_h
        idx = self.top + int(row)
        if 0 <= idx < len(self.items):
            return idx
        return -1

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            idx = self._index_from_pos(event.pos)
            if idx != -1:
                self.selected = idx

        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self.rect.collidepoint((mx, my)):
                self.top -= event.y
                self._clamp_top()

    def get_selected_item(self):
        if 0 <= self.selected < len(self.items):
            return self.items[self.selected]
        return None

    def draw(self, surf):
        pygame.draw.rect(surf, GRID_COLOR, self.rect, 1)
        prev_clip = surf.get_clip()
        surf.set_clip(self.rect)

        vis = self.visible_rows
        start = self.top
        end = min(len(self.items), start + vis)

        for row, idx in enumerate(range(start, end)):
            y = self.rect.y + row * self.item_h
            line_rect = pygame.Rect(self.rect.x, y, self.rect.width - self.scrollbar_w, self.item_h)

            if idx == self.selected:
                pygame.draw.rect(surf, BOX_COLOR, line_rect)

            text = self.font.render(self.items[idx], True, TEXT_LIGHT)
            surf.blit(text, (line_rect.x + 6, line_rect.y + (self.item_h - text.get_height()) // 2))

        surf.set_clip(prev_clip)

        # Scrollbar
        total = len(self.items)
        if total > vis:
            track = pygame.Rect(self.rect.right - self.scrollbar_w, self.rect.y, self.scrollbar_w, self.rect.height)
            pygame.draw.rect(surf, GRID_COLOR, track)
            thumb_h = max(16, int(track.height * (vis / total)))
            max_top = total - vis
            thumb_y = int(track.y + (track.height - thumb_h) * (self.top / max_top)) if max_top > 0 else track.y
            thumb = pygame.Rect(track.x, thumb_y, self.scrollbar_w, thumb_h)
            pygame.draw.rect(surf, BOX_BORDER, thumb)


class InstrumentPicker:
    """
    2 λίστες: Αριστερά όργανα (keys του MAP), Δεξιά presets (MAP[όργανο].keys()).
    'Επιλογή' -> set_preset + αποθήκευση bank/program στο INSTRUMENT_DATA[index].
    Αν bank==128 (Drums) -> route σε Drum Rack.
    """

    def __init__(self, index: int):
        self.index = index

        screen = pygame.display.get_surface()
        sw, sh = screen.get_width(), screen.get_height()

        # Κλιμάκωση
        base_w, base_h = 800, 600
        s = min(sw / base_w, sh / base_h)

        title_size     = max(40, int(50 * s))
        listname_size  = max(34, int(45 * s))
        item_size      = max(22, int(27 * s))
        item_h         = max(36, int(45 * s))
        scrollbar_w    = max(8,  int(10 * s))

        self.font_title = pygame.font.Font(None, title_size)
        self.font_small = pygame.font.Font(None, int(22 * s))
        self.font_item  = pygame.font.Font(None, item_size)
        self.font_label = pygame.font.Font(None, listname_size)

        # Buttons
        self.back_btn = Button(
            rect=back_button_rect(),
            bg_color=BUTTON_BG,
            border_color=BUTTON_BORDER,
            text="Πίσω",
            font=self.font_small,
            text_color=TEXT_DARK,
        )
        btn_w, btn_h = int(200 * s), int(44 * s)

        # Διάταξη λιστών
        list_w = int(min(sw * 0.35, 380 * s))
        list_h = int(min(sh * 0.55, 360 * s))
        gap    = int(max(30, 40 * s))
        top_y  = int(max(90, 120 * s))
        total_w = list_w * 2 + gap
        start_x = (sw - total_w) // 2

        self.left_rect  = pygame.Rect(start_x,               top_y, list_w, list_h)
        self.right_rect = pygame.Rect(start_x + list_w + gap, top_y, list_w, list_h)

        # Button: Επιλογή
        btn_margin_y = int(24 * s)
        btn_x = sw // 2 - btn_w // 2
        btn_y = self.right_rect.bottom + btn_margin_y
        btn_y = min(btn_y, sh - btn_h - int(20 * s))
        self.select_btn = Button(
            rect=pygame.Rect(btn_x, btn_y, btn_w, btn_h),
            bg_color=BUTTON_BG,
            border_color=BUTTON_BORDER,
            text="Επιλογή",
            font=self.font_small,
            text_color=TEXT_DARK
        )

        # Δεδομένα
        self.INSTRUMENTS = {name: list(MAP[name].keys()) for name in MAP.keys()}
        left_items = list(self.INSTRUMENTS.keys())
        self.left  = ListBox(self.left_rect, left_items, item_h=item_h, scrollbar_w=scrollbar_w, font=self.font_item)
        self.right = ListBox(self.right_rect, [],        item_h=item_h, scrollbar_w=scrollbar_w, font=self.font_item)

        if left_items:
            self.left.selected = 0
            self.right.set_items(self.INSTRUMENTS[left_items[0]])
            if self.right.items:
                self.right.selected = 0

        self._prev_left_value  = self.left.get_selected_item()
        self._prev_right_value = self.right.get_selected_item()

        # ✅ preview state (για να μη γίνονται κολλήματα/overlaps)
        self._preview_timer = None
        self._preview_note = None
        self._preview_ch = None

    def _stop_preview(self):
        """Σταμάτα τυχόν προηγούμενο preview note + ακύρωσε timer."""
        if self._preview_note is not None and self._preview_ch is not None:
            stop_note(self._preview_note, channel=self._preview_ch)

        if self._preview_timer is not None:
            try:
                self._preview_timer.cancel()
            except Exception:
                pass

        self._preview_timer = None
        self._preview_note = None
        self._preview_ch = None

    def handle_event(self, event):
        next_state = None

        def go_back():
            nonlocal next_state
            # ✅ cleanup
            self._stop_preview()
            next_state = f"instrument {self.index}"

        self.back_btn.handle_event(event, go_back)

        # Επιβεβαίωση
        def confirm():
            nonlocal next_state

            selected_instrument = self.left.get_selected_item()
            selected_preset = self.right.get_selected_item()
            if not (selected_instrument and selected_preset):
                return

            # Βρες bank/program
            try:
                bank, program = MAP[selected_instrument][selected_preset]
            except KeyError:
                bank, program = 0, 0

            # Channel (σωστό)
            ch = DRUM_CHANNEL if bank == 128 else SLOT_CHANNELS.get(self.index, 0)

            # Πάρε slot
            slot = INSTRUMENT_DATA.setdefault(self.index, {})

            # Αν αλλάζει mode (melodic <-> drums) -> σβήσε ΚΑΙ τα δύο patterns
            prev_is_drums = (int(slot.get("bank", 0) or 0) == 128)
            new_is_drums = (bank == 128)
            if prev_is_drums != new_is_drums:
                slot.pop("piano_roll", None)
                slot.pop("drum_rack", None)

            # Αποθήκευση επιλογής
            slot.update({
                "instrument": selected_instrument,
                "preset": selected_preset,
                "bank": int(bank),
                "program": int(program),
                "channel": int(ch),
            })

            if bank == 128:
                slot["kit_name"] = selected_preset

            # Εφάρμοσε preset
            set_preset(bank, program, channel=ch)

            # ✅ ΚΡΙΣΙΜΟ: ξαναπέρασε effects μετά από program change
            apply_slot_effects(self.index)

            # ✅ σταμάτα preview πριν φύγεις
            self._stop_preview()

            next_state = f"instrument {self.index}"

        self.select_btn.handle_event(event, confirm)

        # Ενέργειες στις λίστες
        clicked_in_right = (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.right.rect.collidepoint(event.pos)
        )
        self.left.handle_event(event)
        self.right.handle_event(event)

        # Αλλαγή αριστερής λίστας -> ανανέωση presets + default select
        cur_left_value = self.left.get_selected_item()
        if cur_left_value != self._prev_left_value and cur_left_value is not None:
            self.right.set_items(self.INSTRUMENTS.get(cur_left_value, []))
            if self.right.items:
                self.right.selected = 0

            # ✅ όταν αλλάζεις λίστα, σταμάτα προηγούμενο preview
            self._stop_preview()

            self._prev_left_value = cur_left_value
            self._prev_right_value = self.right.get_selected_item()

        # Preview όταν αλλάζει preset
        cur_right_value = self.right.get_selected_item()
        if (
            cur_left_value is not None
            and cur_right_value is not None
            and (clicked_in_right or cur_right_value != self._prev_right_value)
        ):
            try:
                bank, program = MAP[cur_left_value][cur_right_value]
            except KeyError:
                bank, program = 0, 0

            # ✅ σωστό channel για preview
            ch = DRUM_CHANNEL if bank == 128 else SLOT_CHANNELS.get(self.index, 0)

            # ✅ σταμάτα προηγούμενο preview (και timer)
            self._stop_preview()

            # preset για preview
            set_preset(bank, program, channel=ch)

            # ✅ ΚΡΙΣΙΜΟ: ξαναπέρασε effects μετά από program change
            apply_slot_effects(self.index)

            preview_note = 36 if bank == 128 else 60
            play_note(preview_note, velocity=110, channel=ch)

            # αποθήκευση state
            self._preview_note = preview_note
            self._preview_ch = ch

            self._preview_timer = threading.Timer(
                0.25,
                lambda: stop_note(preview_note, channel=ch)
            )
            self._preview_timer.start()

            self._prev_right_value = cur_right_value

        return next_state

    def draw(self, screen):
        screen.fill(BG_COLOR)
        pygame.draw.rect(screen, GRID_COLOR, outer_frame_rect(), 1)
        draw_text_center(screen, "Επιλογή Οργάνου", self.font_title, TEXT_LIGHT, (screen.get_width() // 2, 60))

        label_left  = self.font_label.render("Όργανα", True, TEXT_LIGHT)
        label_right = self.font_label.render("Presets", True, TEXT_LIGHT)
        screen.blit(label_left,  (self.left_rect.x,  self.left_rect.y  - label_left.get_height()  - 8))
        screen.blit(label_right, (self.right_rect.x, self.right_rect.y - label_right.get_height() - 8))

        self.left.draw(screen)
        self.right.draw(screen)
        self.back_btn.draw(screen)
        self.select_btn.draw(screen)