"""{{name}}: {{t:game_doc}}"""

import random

import pygame

WIDTH, HEIGHT = 640, 480
SPEED = 5
BACKGROUND = (24, 28, 48)
PLAYER_COLOR = (59, 130, 246)
STAR_COLOR = (250, 204, 21)
TEXT_COLOR = (230, 230, 230)


def new_star() -> pygame.Rect:
    x = random.randint(20, WIDTH - 40)
    y = random.randint(60, HEIGHT - 40)
    return pygame.Rect(x, y, 20, 20)


def run(max_frames: int | None = None) -> int:
    """{{t:game_run_doc}}"""
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("{{name}}")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 32)

    player = pygame.Rect(WIDTH // 2 - 15, HEIGHT // 2 - 15, 30, 30)
    star = new_star()
    score = 0
    frames = 0
    running = True

    while running:
        for event in pygame.event.get():
            escape = event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            if event.type == pygame.QUIT or escape:
                running = False

        keys = pygame.key.get_pressed()
        player.x += (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * SPEED
        player.y += (keys[pygame.K_DOWN] - keys[pygame.K_UP]) * SPEED
        player.clamp_ip(screen.get_rect())

        if player.colliderect(star):
            score += 1
            star = new_star()

        screen.fill(BACKGROUND)
        pygame.draw.rect(screen, STAR_COLOR, star, border_radius=10)
        pygame.draw.rect(screen, PLAYER_COLOR, player, border_radius=6)
        score_text = font.render(f"{{t:game_score}}", True, TEXT_COLOR)
        screen.blit(score_text, (12, 12))
        hint = font.render("{{t:game_hint}}", True, TEXT_COLOR)
        screen.blit(hint, (12, HEIGHT - hint.get_height() - 12))
        pygame.display.flip()
        clock.tick(60)

        frames += 1
        if max_frames is not None and frames >= max_frames:
            running = False

    pygame.quit()
    return score


if __name__ == "__main__":
    run()
