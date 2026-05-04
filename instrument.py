import pygame
from settings.colors import TEXT_LIGHT, TEXT_DARK, BUTTON_BG, BUTTON_BORDER, BOX_COLOR, BOX_BORDER
from UI.layout import back_button_rect, compute_three_menu_rects, outer_frame_rect
from UI.widgets import Button, draw_rect_with_border, draw_text_center
from settings.selections import INSTRUMENT_DATA

class InstrumentScreen:
    def __init__(self, index, data):
        self.index = index
        self.data = data
        self.font_title = pygame.font.Font(None, 64)
        self.font_label = pygame.font.Font(None, 30)
        self.font_small = pygame.font.Font(None, 28)

        self.back_btn = Button(
            rect=back_button_rect(),
            bg_color=BUTTON_BG,
            border_color=BUTTON_BORDER,
            text="Πίσω",
            font=self.font_small,
            text_color=TEXT_DARK
        )

        self.hub_rects = compute_three_menu_rects(offset_y=40)
        self.hub_labels = ["Επιλογή Οργάνου", "Piano Roll", "Εφέ & Ρυθμίσεις"]

    def handle_event(self, event):
        next_state = None

        def go_back():
            nonlocal next_state
            next_state = "menu"

        self.back_btn.handle_event(event, go_back)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.hub_rects[0].collidepoint(mx, my):
                next_state = f"instrument_picker {self.index}"
            elif self.hub_rects[1].collidepoint(mx, my):
                slot = INSTRUMENT_DATA.get(self.index) or {}
                if slot.get("instrument") == "Drums" or int(slot.get("bank", -1)) == 128:
                    next_state = f"drum_rack {self.index}"
                else:
                    next_state = f"piano_roll {self.index}"
            elif self.hub_rects[2].collidepoint(mx, my):
                next_state = f"effects {self.index}"

        return next_state

    def draw(self, screen):
        pygame.draw.rect(screen, (30, 30, 30), outer_frame_rect(), 2)

        title_text = f"instrument {self.index}"
        draw_text_center(
            screen,
            title_text,
            self.font_title,
            TEXT_LIGHT,
            (screen.get_width() // 2, 100)
        )

        for i, (rect, label) in enumerate(zip(self.hub_rects, self.hub_labels)):
            draw_rect_with_border(screen, rect, BOX_COLOR, BOX_BORDER, 3)

            slot = INSTRUMENT_DATA.get(self.index) or {}
            is_drums = (slot.get("instrument") == "Drums") or (int(slot.get("bank", -1)) == 128)

            # Αν είναι Drums, το 2ο κουτί (Piano Roll) μετονομάζεται σε Drum Rack
            if i == 1:
                label = "Drum Rack" if is_drums else label
                draw_text_center(screen, label, self.font_label, TEXT_LIGHT, rect.center)
                continue

            # 1ο κουτί: δείχνει "Drums" + kit ή instrument + preset
            if i == 0:
                cx, cy = rect.center

                if is_drums:
                    kit_name = slot.get("preset", "") or slot.get("kit_name", "") or ""
                    # Γραμμή 1: "Drums"
                    draw_text_center(screen, "Drums", self.font_label, TEXT_LIGHT, (cx, cy - 12))
                    # Γραμμή 2: kit (μόνο αν υπάρχει)
                    if kit_name:
                        draw_text_center(screen, kit_name, self.font_small, TEXT_LIGHT, (cx, cy + 18))
                    else:
                        draw_text_center(screen, "—", self.font_small, TEXT_LIGHT, (cx, cy + 18))
                else:
                    inst = slot.get("instrument", "") or ""
                    preset = slot.get("preset", "") or ""

                    if not inst and not preset:
                        draw_text_center(screen, "Επιλογή οργάνου", self.font_label, TEXT_LIGHT, rect.center)
                    else:
                        # Γραμμή 1: instrument, Γραμμή 2: preset
                        draw_text_center(screen, inst if inst else "Instrument", self.font_label, TEXT_LIGHT, (cx, cy - 12))
                        if preset:
                            draw_text_center(screen, preset, self.font_small, TEXT_LIGHT, (cx, cy + 18))
                continue

            # 3ο κουτί (Effects)
            draw_text_center(screen, label, self.font_label, TEXT_LIGHT, rect.center)

        self.back_btn.draw(screen)
