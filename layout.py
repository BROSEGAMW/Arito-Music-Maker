import pygame
from settings.config import WIDTH, HEIGHT, BOX_W, BOX_H, GAP

def compute_grid_rects(cols=4, rows=3, box_w=160, box_h=105, gap=24, top_y=235):
    total_width = box_w * cols + gap * (cols - 1)
    start_x = (WIDTH - total_width) // 2
    rects = []
    for row in range(rows):
        for col in range(cols):
            x = start_x + col * (box_w + gap)
            y = top_y + row * (box_h + gap)
            rects.append(pygame.Rect(x, y, box_w, box_h))
    return rects

def back_button_rect():
    return pygame.Rect(20, 20, 100, 40)

def outer_frame_rect(margin=20):
    return pygame.Rect(margin, margin, WIDTH - 2*margin, HEIGHT - 2*margin)

def compute_three_menu_rects(offset_y=60):
    center_y = (HEIGHT // 2) + offset_y
    total_width = 3 * BOX_W + 2 * GAP
    start_x = (WIDTH - total_width) // 2
    y = center_y - (BOX_H // 2)
    rects = [
        pygame.Rect(start_x, y, BOX_W, BOX_H),
        pygame.Rect(start_x + BOX_W + GAP, y, BOX_W, BOX_H),
        pygame.Rect(start_x + 2*(BOX_W + GAP), y, BOX_W, BOX_H),
    ]
    return rects
