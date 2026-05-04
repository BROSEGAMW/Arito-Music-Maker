import pygame
from settings.colors import (
    GRID_COLOR, BOX_COLOR, BOX_BORDER, PLUS_COLOR,
    TEXT_LIGHT, TEXT_DARK, BUTTON_BG, BUTTON_BORDER
)
from UI.layout import compute_grid_rects, outer_frame_rect
from UI.widgets import Button, draw_rect_with_border, draw_text_center
from settings.project_state import PROJECT_SETTINGS, ensure_project_settings
from settings.selections import INSTRUMENT_DATA
from tools.project_transport import PROJECT_TRANSPORT

class MenuScreen:
    def __init__(self):
        self.font_plus = pygame.font.Font(None, 72)
        self.font_bar = pygame.font.Font(None, 24)
        self.font_status = pygame.font.Font(None, 22)
        self.font_slot = pygame.font.Font(None, 24)
        self.font_preset = pygame.font.Font(None, 20)
        self.font_index = pygame.font.Font(None, 18)
        self.rects = compute_grid_rects()
        self.is_playing = False
        self.status_message = ""
        self.status_until = 0
        self.dragging_transport_slider = False

        self.btn_play = Button(pygame.Rect(0, 0, 70, 34), (0, 180, 0), BUTTON_BORDER, "Play", self.font_bar, TEXT_DARK)
        self.btn_stop = Button(pygame.Rect(0, 0, 70, 34), (180, 0, 0), BUTTON_BORDER, "Stop", self.font_bar, TEXT_LIGHT)
        self.btn_loop = Button(pygame.Rect(0, 0, 70, 34), (200, 140, 0), BUTTON_BORDER, "Loop", self.font_bar, TEXT_DARK)
        self.btn_bpm_minus = Button(pygame.Rect(0, 0, 34, 34), BUTTON_BG, BUTTON_BORDER, "-", self.font_bar, TEXT_DARK)
        self.btn_bpm_plus = Button(pygame.Rect(0, 0, 34, 34), BUTTON_BG, BUTTON_BORDER, "+", self.font_bar, TEXT_DARK)
        self.btn_save = Button(pygame.Rect(0, 0, 74, 34), BUTTON_BG, BUTTON_BORDER, "Save", self.font_bar, TEXT_DARK)
        self.btn_load = Button(pygame.Rect(0, 0, 74, 34), BUTTON_BG, BUTTON_BORDER, "Load", self.font_bar, TEXT_DARK)
        self.bpm_rect = pygame.Rect(0, 0, 86, 34)
        self.transport_slider_rect = pygame.Rect(0, 0, 720, 8)
        self.transport_thumb_rect = pygame.Rect(0, 0, 14, 20)

    def _layout_transport(self, screen_w: int):
        gap = 10
        controls_w = (
            self.btn_play.rect.width + self.btn_stop.rect.width + self.btn_loop.rect.width
            + self.btn_bpm_minus.rect.width + self.bpm_rect.width + self.btn_bpm_plus.rect.width
            + self.btn_save.rect.width + self.btn_load.rect.width
            + gap * 7
        )
        x = (screen_w - controls_w) // 2
        y = 56

        for rect_owner in (
            self.btn_play, self.btn_stop, self.btn_loop,
            self.btn_bpm_minus, self.btn_bpm_plus,
            self.btn_save, self.btn_load,
        ):
            rect_owner.rect.y = y

        self.btn_play.rect.x = x
        self.btn_stop.rect.x = self.btn_play.rect.right + gap
        self.btn_loop.rect.x = self.btn_stop.rect.right + gap
        self.btn_bpm_minus.rect.x = self.btn_loop.rect.right + gap
        self.bpm_rect = pygame.Rect(self.btn_bpm_minus.rect.right + gap, y, self.bpm_rect.width, self.bpm_rect.height)
        self.btn_bpm_plus.rect.x = self.bpm_rect.right + gap
        self.btn_save.rect.x = self.btn_bpm_plus.rect.right + gap
        self.btn_load.rect.x = self.btn_save.rect.right + gap

        slider_w = min(760, screen_w - 140)
        slider_x = (screen_w - slider_w) // 2
        slider_y = y + 56
        self.transport_slider_rect = pygame.Rect(slider_x, slider_y, slider_w, 8)
        ratio = PROJECT_TRANSPORT.progress_ratio()
        thumb_x = int(self.transport_slider_rect.left + ratio * self.transport_slider_rect.width)
        self.transport_thumb_rect = pygame.Rect(thumb_x - 7, self.transport_slider_rect.centery - 10, 14, 20)

    def _change_bpm(self, delta: int):
        PROJECT_TRANSPORT.change_tempo(delta)

    def _seek_transport_from_x(self, mx: int):
        rect = self.transport_slider_rect
        ratio = (mx - rect.left) / max(1, rect.width)
        if PROJECT_TRANSPORT.seek_ratio(ratio):
            self.set_status("Playhead moved", duration_ms=900)

    def set_status(self, message: str, duration_ms: int = 2200):
        self.status_message = str(message)
        self.status_until = pygame.time.get_ticks() + int(duration_ms)

    def on_project_loaded(self):
        ensure_project_settings()
        PROJECT_TRANSPORT.stop()
        self.is_playing = False

    @staticmethod
    def _ellipsis(text: str, font: pygame.font.Font, max_w: int) -> str:
        if font.size(text)[0] <= max_w:
            return text
        dots = "..."
        s = text
        while s and font.size(s + dots)[0] > max_w:
            s = s[:-1]
        return (s + dots) if s else dots

    def handle_event(self, event):
        screen = pygame.display.get_surface()
        if screen:
            self._layout_transport(screen.get_width())

        next_state = None

        def do_play():
            if PROJECT_TRANSPORT.play():
                self.is_playing = True
                self.set_status("Playing project")
            else:
                self.is_playing = False
                self.set_status("Nothing to play")

        def do_stop():
            PROJECT_TRANSPORT.stop()
            self.is_playing = False

        def do_loop():
            PROJECT_TRANSPORT.toggle_loop()

        def do_save():
            nonlocal next_state
            next_state = "save_project"

        def do_load():
            nonlocal next_state
            next_state = "load_project"

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            slider_hit = self.transport_slider_rect.inflate(0, 18).collidepoint(mx, my)
            thumb_hit = self.transport_thumb_rect.inflate(6, 6).collidepoint(mx, my)
            if slider_hit or thumb_hit:
                self.dragging_transport_slider = True
                self._seek_transport_from_x(mx)
                return None

        if event.type == pygame.MOUSEMOTION and self.dragging_transport_slider:
            self._seek_transport_from_x(event.pos[0])
            return None

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging_transport_slider:
            self.dragging_transport_slider = False
            self._seek_transport_from_x(event.pos[0])
            return None

        self.btn_play.handle_event(event, do_play)
        self.btn_stop.handle_event(event, do_stop)
        self.btn_loop.handle_event(event, do_loop)
        self.btn_bpm_minus.handle_event(event, lambda: self._change_bpm(-1))
        self.btn_bpm_plus.handle_event(event, lambda: self._change_bpm(+1))
        self.btn_save.handle_event(event, do_save)
        self.btn_load.handle_event(event, do_load)

        if next_state:
            return next_state

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for i, r in enumerate(self.rects):
                if r.collidepoint(mx, my):
                    return f"instrument {i+1}"
        return None

    def draw(self, screen):
        ensure_project_settings()
        self._layout_transport(screen.get_width())

        pygame.draw.rect(screen, GRID_COLOR, outer_frame_rect(), 2)
        self.btn_play.draw(screen)
        self.btn_stop.draw(screen)
        self.btn_loop.draw(screen)
        self.btn_bpm_minus.draw(screen)
        pygame.draw.rect(screen, BUTTON_BG, self.bpm_rect)
        pygame.draw.rect(screen, BUTTON_BORDER, self.bpm_rect, 2)
        draw_text_center(
            screen,
            f"BPM {int(PROJECT_SETTINGS['global_tempo_bpm'])}",
            self.font_bar,
            TEXT_DARK,
            self.bpm_rect.center
        )
        self.btn_bpm_plus.draw(screen)
        self.btn_save.draw(screen)
        self.btn_load.draw(screen)
        self._draw_transport_slider(screen)

        self.is_playing = PROJECT_TRANSPORT.is_playing

        if PROJECT_TRANSPORT.is_playing:
            pygame.draw.rect(screen, (60, 255, 60), self.btn_play.rect, 3)
        if bool(PROJECT_SETTINGS.get("global_loop", False)):
            pygame.draw.rect(screen, (255, 60, 60), self.btn_loop.rect, 3)

        if self.status_message and pygame.time.get_ticks() < self.status_until:
            draw_text_center(screen, self.status_message, self.font_status, TEXT_LIGHT, (screen.get_width() // 2, 165))

        for i, r in enumerate(self.rects):
            draw_rect_with_border(screen, r, BOX_COLOR, BOX_BORDER, 3)
            idx_text = self.font_index.render(str(i + 1), True, PLUS_COLOR)
            screen.blit(idx_text, (r.x + 8, r.y + 7))
            slot = INSTRUMENT_DATA.get(i + 1, {}) or {}
            inst = slot.get("instrument", "") or ""
            preset = slot.get("preset", "") or slot.get("kit_name", "") or ""
            if inst or preset:
                max_w = r.width - 18
                draw_text_center(screen, self._ellipsis(inst or "Instrument", self.font_slot, max_w), self.font_slot, TEXT_LIGHT, (r.centerx, r.centery - 14))
                if preset:
                    draw_text_center(screen, self._ellipsis(preset, self.font_preset, max_w), self.font_preset, TEXT_LIGHT, (r.centerx, r.centery + 18))
            else:
                draw_text_center(screen, "+", self.font_plus, PLUS_COLOR, r.center)

    def _draw_transport_slider(self, screen):
        rect = self.transport_slider_rect
        pygame.draw.rect(screen, (70, 70, 70), rect)
        if PROJECT_TRANSPORT.has_content():
            fill = pygame.Rect(rect.left, rect.top, max(0, self.transport_thumb_rect.centerx - rect.left), rect.height)
            pygame.draw.rect(screen, (150, 150, 150), fill)
            thumb_color = (220, 220, 220)
        else:
            thumb_color = (95, 95, 95)
        pygame.draw.rect(screen, thumb_color, self.transport_thumb_rect, border_radius=2)
        pygame.draw.rect(screen, BUTTON_BORDER, self.transport_thumb_rect, 1, border_radius=2)
