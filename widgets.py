import pygame

class Button:
    def __init__(self, rect, bg_color, border_color, text, font, text_color):
        self.rect = pygame.Rect(rect)
        self.bg_color = bg_color
        self.border_color = border_color
        self.text = text
        self.font = font
        self.text_color = text_color

    def draw(self, surf):
        pygame.draw.rect(surf, self.bg_color, self.rect)
        pygame.draw.rect(surf, self.border_color, self.rect, 2)
        label = self.font.render(self.text, True, self.text_color)
        surf.blit(label, label.get_rect(center=self.rect.center))

    def is_hover(self, pos):
        return self.rect.collidepoint(pos)

    def handle_event(self, event, on_click):
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.is_hover(event.pos):
                on_click()

def draw_rect_with_border(surf, rect, fill_color, border_color, border_width=3):
    pygame.draw.rect(surf, fill_color, rect)
    pygame.draw.rect(surf, border_color, rect, border_width)

def draw_text_center(surf, text, font, color, center):
    label = font.render(text, True, color)
    surf.blit(label, label.get_rect(center=center))