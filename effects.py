# -*- coding: utf-8 -*-
"""
screens/effects.py

UI:
- Κεντρικό panel πάνω από PAN με sliders:
  ΕΝΤΑΣΗ / ΒΑΘΟΣ / ΧΟΡΩΔΙΑ / ΟΥΡΑ / ΒΙΜΠΡΑΤΟ
- Πράσινα toggles: VOL, REV, CHO, SUS, MOD
- PAN κάτω και κεντρικά

ΝΕΟ:
- "Default": επαναφέρει ΑΚΡΙΒΩΣ τις αρχικές ρυθμίσεις όπως ήταν όταν άνοιξε το Effects screen.
- Ctrl+Click σε toggle:
    * πάντα SOLO: μόνο αυτό ON, όλα τα άλλα OFF
    * Ctrl+Click ξανά στο ίδιο: ALL ON
"""

import copy
import pygame

from settings.colors import BG_COLOR, GRID_COLOR, TEXT_LIGHT, TEXT_DARK, BUTTON_BG, BUTTON_BORDER
from UI.layout import back_button_rect, outer_frame_rect
from UI.widgets import Button, draw_text_center
from tools.audio_engine import apply_slot_effects, ensure_slot_effects


class VSlider:
    """Απλός κάθετος slider 0..127."""
    def __init__(self, x: int, y: int, h: int, label: str, value: int = 0, w: int = 22):
        self.label = label
        self.track = pygame.Rect(x, y, w, h)
        self.value = int(max(0, min(127, value)))
        self.dragging = False

    def _y_to_value(self, my: int) -> int:
        my = max(self.track.top, min(self.track.bottom, my))
        ratio = (self.track.bottom - my) / max(1, self.track.height)
        return int(round(ratio * 127))

    def _value_to_y(self) -> int:
        ratio = max(0.0, min(1.0, self.value / 127.0))
        return int(self.track.bottom - ratio * self.track.height)

    def handle_event(self, event) -> bool:
        changed = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.track.collidepoint(event.pos):
            self.dragging = True
            self.value = self._y_to_value(event.pos[1])
            changed = True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self.value = self._y_to_value(event.pos[1])
            changed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False

        if changed:
            self.value = int(max(0, min(127, self.value)))
        return changed

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        pygame.draw.rect(screen, (70, 70, 70), self.track)
        ty = self._value_to_y()
        pygame.draw.circle(screen, (210, 210, 210), (self.track.centerx, ty), 7)

        lbl = font.render(self.label, True, TEXT_LIGHT)
        screen.blit(lbl, (self.track.centerx - lbl.get_width() // 2, self.track.top - 28))

        val = font.render(str(int(self.value)), True, TEXT_LIGHT)
        screen.blit(val, (self.track.centerx - val.get_width() // 2, self.track.bottom + 8))


class HSlider:
    """Οριζόντιος slider 0..127 (PAN)."""
    def __init__(self, x: int, y: int, w: int, label: str, value: int = 64, h: int = 10):
        self.label = label
        self.track = pygame.Rect(x, y, w, h)
        self.value = int(max(0, min(127, value)))
        self.dragging = False

    def _x_to_value(self, mx: int) -> int:
        mx = max(self.track.left, min(self.track.right, mx))
        ratio = (mx - self.track.left) / max(1, self.track.width)
        return int(round(ratio * 127))

    def _value_to_x(self) -> int:
        ratio = max(0.0, min(1.0, self.value / 127.0))
        return int(self.track.left + ratio * self.track.width)

    def handle_event(self, event) -> bool:
        changed = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.track.collidepoint(event.pos):
            self.dragging = True
            self.value = self._x_to_value(event.pos[0])
            changed = True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self.value = self._x_to_value(event.pos[0])
            changed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False

        if changed:
            self.value = int(max(0, min(127, self.value)))
        return changed

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, center_x: int):
        pygame.draw.rect(screen, (70, 70, 70), self.track)
        tx = self._value_to_x()
        pygame.draw.circle(screen, (210, 210, 210), (tx, self.track.centery), 7)

        lbl = font.render(self.label, True, TEXT_LIGHT)
        screen.blit(lbl, (center_x - lbl.get_width() // 2, self.track.top - 24))

        ltxt = font.render("L", True, TEXT_LIGHT)
        rtxt = font.render("R", True, TEXT_LIGHT)
        screen.blit(ltxt, (self.track.left - ltxt.get_width() - 8, self.track.centery - ltxt.get_height() // 2))
        screen.blit(rtxt, (self.track.right + 8, self.track.centery - rtxt.get_height() // 2))


class EffectsScreen:
    def __init__(self, index: int):
        self.index = int(index)
        self.font_title = pygame.font.Font(None, 50)
        self.font = pygame.font.Font(None, 22)

        self.back_btn = Button(back_button_rect(), BUTTON_BG, BUTTON_BORDER, "Πίσω", self.font, TEXT_DARK)
        self.btn_default = Button(pygame.Rect(0, 0, 120, 34), BUTTON_BG, BUTTON_BORDER, "Επαναφορά", self.font, TEXT_DARK)

        self.fx = ensure_slot_effects(self.index)
        self._entry_snapshot = copy.deepcopy(self.fx)

        # ✅ Ελληνικά labels
        self.sld_vol = VSlider(0, 0, 250, "ΕΝΤΑΣΗ", int(self.fx.get("volume", 100)))
        self.sld_rev = VSlider(0, 0, 250, "ΒΑΘΟΣ", int(self.fx["reverb"]["amount"]))
        self.sld_cho = VSlider(0, 0, 250, "ΧΟΡΩΔΙΑ", int(self.fx["chorus"]["amount"]))
        self.sld_sus = VSlider(0, 0, 250, "ΟΥΡΑ", int(self.fx["sustain"]["amount"]))
        self.sld_mod = VSlider(0, 0, 250, "ΒΙΜΠΡΑΤΟ", int(self.fx["mod"]["amount"]))

        self.pan = HSlider(0, 0, 420, "PAN", int(self.fx.get("pan", 64)))

        self._toggle_r = 13
        self._toggle_centers = {"VOL": (0, 0), "REV": (0, 0), "CHO": (0, 0), "SUS": (0, 0), "MOD": (0, 0)}
        self.faders_frame = pygame.Rect(0, 0, 0, 0)
        self.pan_frame = pygame.Rect(0, 0, 0, 0)

        self._solo_mode = False
        self._solo_key = None

        apply_slot_effects(self.index)

    def _hit_circle(self, pos, center) -> bool:
        dx = pos[0] - center[0]
        dy = pos[1] - center[1]
        return (dx * dx + dy * dy) <= (self._toggle_r * self._toggle_r)

    def _layout(self, w: int, h: int):
        top = 130
        slider_top = top + 70

        slider_h = min(300, h - slider_top - 260)
        slider_h = max(210, slider_h)

        bar_w = 22
        n = 5

        # ✅ ΠΙΟ ΜΕΓΑΛΕΣ ΑΠΟΣΤΑΣΕΙΣ
        gap = 150

        total_w = (n - 1) * gap + bar_w
        left = (w - total_w) // 2
        xs = [left + i * gap for i in range(n)]

        self.sld_vol.track = pygame.Rect(xs[0], slider_top, bar_w, slider_h)
        self.sld_rev.track = pygame.Rect(xs[1], slider_top, bar_w, slider_h)
        self.sld_cho.track = pygame.Rect(xs[2], slider_top, bar_w, slider_h)
        self.sld_sus.track = pygame.Rect(xs[3], slider_top, bar_w, slider_h)
        self.sld_mod.track = pygame.Rect(xs[4], slider_top, bar_w, slider_h)

        toggle_y = slider_top + slider_h + 55
        self._toggle_centers["VOL"] = (self.sld_vol.track.centerx, toggle_y)
        self._toggle_centers["REV"] = (self.sld_rev.track.centerx, toggle_y)
        self._toggle_centers["CHO"] = (self.sld_cho.track.centerx, toggle_y)
        self._toggle_centers["SUS"] = (self.sld_sus.track.centerx, toggle_y)
        self._toggle_centers["MOD"] = (self.sld_mod.track.centerx, toggle_y)

        pan_y = toggle_y + 130
        pan_w = min(520, w - 160)
        pan_x = (w - pan_w) // 2
        self.pan.track = pygame.Rect(pan_x, pan_y, pan_w, 10)

        # ✅ λίγο μεγαλύτερο padding για να “ανασαίνει”
        pads = 70
        left_edge = self.sld_vol.track.left
        right_edge = self.sld_mod.track.right
        top_edge = self.sld_vol.track.top - 36
        bottom_edge = toggle_y + 24

        self.faders_frame = pygame.Rect(
            left_edge - pads,
            top_edge - pads,
            (right_edge - left_edge) + 2 * pads,
            (bottom_edge - top_edge) + 2 * pads
        )

        pan_pad = 35
        self.pan_frame = pygame.Rect(
            self.pan.track.left - pan_pad,
            self.pan.track.top - 32,
            self.pan.track.width + 2 * pan_pad,
            self.pan.track.height + 60
        )

        self.btn_default.rect.topleft = (
            self.faders_frame.right - self.btn_default.rect.width - 14,
            self.faders_frame.top + 12
        )

    def _set_all_toggles(self, on: bool):
        self.fx["volume_on"] = bool(on)
        self.fx["reverb"]["on"] = bool(on)
        self.fx["chorus"]["on"] = bool(on)
        self.fx["sustain"]["on"] = bool(on)
        self.fx["mod"]["on"] = bool(on)

    def _set_only_toggle(self, key: str):
        self._set_all_toggles(False)
        if key == "VOL":
            self.fx["volume_on"] = True
        elif key == "REV":
            self.fx["reverb"]["on"] = True
        elif key == "CHO":
            self.fx["chorus"]["on"] = True
        elif key == "SUS":
            self.fx["sustain"]["on"] = True
        elif key == "MOD":
            self.fx["mod"]["on"] = True

    def _restore_entry_defaults(self):
        self.fx = copy.deepcopy(self._entry_snapshot)

        self.sld_vol.value = int(self.fx.get("volume", 100))
        self.sld_rev.value = int(self.fx["reverb"]["amount"])
        self.sld_cho.value = int(self.fx["chorus"]["amount"])
        self.sld_sus.value = int(self.fx["sustain"]["amount"])
        self.sld_mod.value = int(self.fx["mod"]["amount"])
        self.pan.value = int(self.fx.get("pan", 64))

        self._solo_mode = False
        self._solo_key = None

        apply_slot_effects(self.index)

    def _ctrl_solo_logic(self, key: str):
        if (not self._solo_mode) or (self._solo_key != key):
            self._solo_mode = True
            self._solo_key = key
            self._set_only_toggle(key)
            apply_slot_effects(self.index)
            return

        self._solo_mode = False
        self._solo_key = None
        self._set_all_toggles(True)
        apply_slot_effects(self.index)

    def handle_event(self, event):
        next_state = None

        def go_back():
            nonlocal next_state
            next_state = f"instrument {self.index}"

        self.back_btn.handle_event(event, go_back)

        screen = pygame.display.get_surface()
        if screen:
            self._layout(screen.get_width(), screen.get_height())

        self.btn_default.handle_event(event, self._restore_entry_defaults)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mods = pygame.key.get_mods()
            ctrl = bool(mods & pygame.KMOD_CTRL)

            for key in ["VOL", "REV", "CHO", "SUS", "MOD"]:
                if self._hit_circle(event.pos, self._toggle_centers[key]):
                    if ctrl:
                        self._ctrl_solo_logic(key)
                    else:
                        if key == "VOL":
                            self.fx["volume_on"] = not bool(self.fx.get("volume_on", True))
                        elif key == "REV":
                            self.fx["reverb"]["on"] = not bool(self.fx["reverb"].get("on", False))
                        elif key == "CHO":
                            self.fx["chorus"]["on"] = not bool(self.fx["chorus"].get("on", False))
                        elif key == "SUS":
                            self.fx["sustain"]["on"] = not bool(self.fx["sustain"].get("on", False))
                        elif key == "MOD":
                            self.fx["mod"]["on"] = not bool(self.fx["mod"].get("on", False))

                        self._solo_mode = False
                        self._solo_key = None
                        apply_slot_effects(self.index)
                    break

        changed = False
        changed |= self.sld_vol.handle_event(event)
        changed |= self.sld_rev.handle_event(event)
        changed |= self.sld_cho.handle_event(event)
        changed |= self.sld_sus.handle_event(event)
        changed |= self.sld_mod.handle_event(event)
        changed |= self.pan.handle_event(event)

        if changed:
            self.fx["volume"] = int(self.sld_vol.value)
            self.fx["reverb"]["amount"] = int(self.sld_rev.value)
            self.fx["chorus"]["amount"] = int(self.sld_cho.value)
            self.fx["sustain"]["amount"] = int(self.sld_sus.value)
            self.fx["mod"]["amount"] = int(self.sld_mod.value)
            self.fx["pan"] = int(self.pan.value)

            self._solo_mode = False
            self._solo_key = None

            apply_slot_effects(self.index)

        return next_state

    def draw(self, screen: pygame.Surface):
        w, h = screen.get_width(), screen.get_height()
        self._layout(w, h)

        screen.fill(BG_COLOR)
        pygame.draw.rect(screen, GRID_COLOR, outer_frame_rect(), 1)

        draw_text_center(screen, "Εφέ", self.font_title, TEXT_LIGHT, (w // 2, 70))
        self.back_btn.draw(screen)
        self.btn_default.draw(screen)

        grey = (120, 120, 120)
        pygame.draw.rect(screen, grey, self.faders_frame, 2, border_radius=18)
        pygame.draw.rect(screen, grey, self.pan_frame, 2, border_radius=18)

        self.sld_vol.draw(screen, self.font)
        self.sld_rev.draw(screen, self.font)
        self.sld_cho.draw(screen, self.font)
        self.sld_sus.draw(screen, self.font)
        self.sld_mod.draw(screen, self.font)

        green = (0, 200, 0)
        for k in ["VOL", "REV", "CHO", "SUS", "MOD"]:
            pygame.draw.circle(screen, green, self._toggle_centers[k], self._toggle_r, 2)

        if bool(self.fx.get("volume_on", True)):
            pygame.draw.circle(screen, green, self._toggle_centers["VOL"], self._toggle_r - 2, 0)
        if bool(self.fx["reverb"].get("on", False)):
            pygame.draw.circle(screen, green, self._toggle_centers["REV"], self._toggle_r - 2, 0)
        if bool(self.fx["chorus"].get("on", False)):
            pygame.draw.circle(screen, green, self._toggle_centers["CHO"], self._toggle_r - 2, 0)
        if bool(self.fx["sustain"].get("on", False)):
            pygame.draw.circle(screen, green, self._toggle_centers["SUS"], self._toggle_r - 2, 0)
        if bool(self.fx["mod"].get("on", False)):
            pygame.draw.circle(screen, green, self._toggle_centers["MOD"], self._toggle_r - 2, 0)

        self.pan.draw(screen, self.font, w // 2)