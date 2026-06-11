import os
import random
import pygame
pygame.init()

WIDTH, HEIGHT = 800, 600
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Game Jam")
CLOCK = pygame.time.Clock()
FONT = pygame.font.SysFont("arial", 24)
TITLE_FONT = pygame.font.SysFont("arial", 48, bold=True)

GRAVITY = 0.8
ACCELERATION = 0.7
FRICTION = 0.8
JUMP_VELOCITY = -14
MAX_SPEED = 8
FLOOR_Y = HEIGHT - 40
FLOOR_HEIGHT = 40
ENEMY_SPEED = 4

PLAYER_SCREEN_X = WIDTH // 2
PLAYER_SCREEN_Y = HEIGHT - 120
camera_offset_x = 0
camera_offset_y = 0

ENEMY_DAMAGE = 25
ATTACK_COOLDOWN_FRAMES = 45
PARTICLE_LIFETIME = 18
PARTICLE_SPAWN_RATE = 4
COINS_PER_KILL = 25
KILLS_PER_LEVEL = 3
ENEMY_CAP = 8
SPAWN_COOLDOWN_FRAMES = 75
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

def load_image(name):
	return pygame.image.load(os.path.join(ASSET_DIR, name)).convert_alpha()

def scale(surface, size):
	return pygame.transform.scale(surface, size)

LEG_FRAMES = [scale(load_image(n), (28, 18)) for n in ("legs.png", "legs1.png", "legs2.png")]
MANA_FRAMES = [scale(load_image(f"mana_tank{i}.png" if i else "mana_tank.png"), (18, 33)) for i in range(6)]

def draw_actor(surface, screen_rect, color, anim_frame, walking):
	"""Draw a colored body (with animated legs when walking) anchored to a physics rect."""
	if walking:
		legs = LEG_FRAMES[anim_frame % len(LEG_FRAMES)]
		surface.blit(legs, (screen_rect.centerx - legs.get_width() // 2,
			screen_rect.bottom - legs.get_height()))
	body = pygame.Rect(screen_rect.x, screen_rect.y, screen_rect.width, screen_rect.height - 4)
	pygame.draw.rect(surface, color, body)

class Particle:
	def __init__(self, x, y, vx, vy):
		self.world_x = x
		self.world_y = y
		self.velocity_x = vx
		self.velocity_y = vy
		self.age = 0
		self.lifetime = PARTICLE_LIFETIME
		self.size = 6
		self.color = (250, 220, 120)

	def update(self):
		self.world_x += self.velocity_x
		self.world_y += self.velocity_y
		self.age += 1

	def is_alive(self):
		return self.age < self.lifetime

	def draw(self, surface):
		alpha = max(0, 255 * (1 - self.age / self.lifetime))
		particle_surf = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
		particle_surf.fill((*self.color, int(alpha)))
		surface.blit(particle_surf, (self.world_x - camera_offset_x, self.world_y - camera_offset_y))

class Player:
	def __init__(self, x, y):
		self.world_x = x
		self.world_y = y
		self.velocity_x = 0.0
		self.velocity_y = 0.0
		self.on_ground = False
		self.health = 100
		self.max_health = 100
		self.facing = 1
		self.width = 40
		self.height = 40
		self.particles = []
		self.particle_timer = 0
		self.anim_timer = 0
		self.anim_frame = 0
		# Shop / progression
		self.coins = 0
		self.max_speed = MAX_SPEED
		self.jump_velocity = JUMP_VELOCITY

	def get_rect(self):
		return pygame.Rect(self.world_x, self.world_y, self.width, self.height)

	def get_screen_rect(self):
		return pygame.Rect(PLAYER_SCREEN_X, PLAYER_SCREEN_Y, self.width, self.height)

	def handle_input(self):
		keys = pygame.key.get_pressed()
		acceleration_x = 0.0
		if keys[pygame.K_a]:
			acceleration_x -= ACCELERATION
			self.facing = -1
		if keys[pygame.K_d]:
			acceleration_x += ACCELERATION
			self.facing = 1
		if keys[pygame.K_w] and self.on_ground:
			self.velocity_y = self.jump_velocity
			self.on_ground = False
		self.velocity_x += acceleration_x
		if acceleration_x == 0 and self.on_ground:
			self.velocity_x *= FRICTION
		else:
			self.velocity_x *= 0.99
		if self.velocity_x > self.max_speed:
			self.velocity_x = self.max_speed
		elif self.velocity_x < -self.max_speed:
			self.velocity_x = -self.max_speed
		if keys[pygame.K_s] and not self.on_ground:
			self.velocity_y += 0.4

	def apply_gravity(self):
		self.velocity_y += GRAVITY

	def move_and_collide(self):
		global camera_offset_x, camera_offset_y
		self.world_x += int(self.velocity_x)
		self.world_y += int(self.velocity_y)
		self.on_ground = False

		if self.world_y + self.height >= FLOOR_Y:
			self.world_y = FLOOR_Y - self.height
			self.velocity_y = 0
			self.on_ground = True

		if self.world_y < 0:
			self.world_y = 0
			self.velocity_y = 0

		camera_offset_x = self.world_x - PLAYER_SCREEN_X
		camera_offset_y = self.world_y - PLAYER_SCREEN_Y

	def spawn_particle(self):
		offset_x = -6 if self.facing > 0 else self.width + 6
		particle_x = self.world_x + offset_x
		particle_y = self.world_y + self.height * 0.5
		velocity_x = (self.facing * -0.6) + (self.velocity_x * 0.05)
		velocity_y = -0.3
		self.particles.append(Particle(particle_x, particle_y, velocity_x, velocity_y))

	def update_particles(self):
		for particle in self.particles:
			particle.update()
		self.particles = [p for p in self.particles if p.is_alive()]

	def update(self):
		self.handle_input()
		self.apply_gravity()
		self.move_and_collide()
		self.update_particles()
		self.anim_timer += 1
		if self.anim_timer >= 6:
			self.anim_timer = 0
			self.anim_frame += 1
		moving_forward = (self.facing > 0 and self.velocity_x > 0) or (self.facing < 0 and self.velocity_x < 0)
		if self.particle_timer <= 0 and abs(self.velocity_x) > 1 and moving_forward:
			self.spawn_particle()
			self.particle_timer = PARTICLE_SPAWN_RATE
		else:
			self.particle_timer -= 1

	def draw(self, surface):
		for particle in self.particles:
			particle.draw(surface)
		walking = self.on_ground and abs(self.velocity_x) > 1
		draw_actor(surface, self.get_screen_rect(), (60, 160, 255), self.anim_frame, walking)

	def is_squashing_enemy(self, enemy):
		if not enemy.is_alive:
			return False
		if self.velocity_y > 2 and self.get_rect().colliderect(enemy.get_rect()):
			if self.world_y + self.height <= enemy.get_rect().bottom + 20:
				return True
		return False

class Enemy:
	def __init__(self, x, y, level=1):
		self.world_x = x
		self.world_y = y
		self.velocity_x = 0.0
		self.velocity_y = 0.0
		self.on_ground = False
		self.attack_timer = 0
		self.level = level
		self.max_health = 100 + (level - 1) * 20
		self.health = self.max_health
		self.damage = ENEMY_DAMAGE + (level - 1) * 5
		self.is_alive = True
		self.width = 40
		self.height = 40
		self.anim_timer = 0
		self.anim_frame = 0

	def get_rect(self):
		return pygame.Rect(self.world_x, self.world_y, self.width, self.height)

	def get_screen_rect(self):
		return pygame.Rect(self.world_x - camera_offset_x, self.world_y - camera_offset_y, self.width, self.height)

	def apply_gravity(self):
		self.velocity_y += GRAVITY

	def move_toward_player(self, player):
		player_left = player.world_x
		player_right = player.world_x + player.width
		enemy_left = self.world_x
		enemy_right = self.world_x + self.width
		if enemy_right < player_left:
			self.velocity_x = ENEMY_SPEED
		elif enemy_left > player_right:
			self.velocity_x = -ENEMY_SPEED
		else:
			self.velocity_x = 0

	def move_and_collide(self):
		self.world_x += int(self.velocity_x)
		self.world_y += int(self.velocity_y)
		self.on_ground = False

		if self.world_y + self.height >= FLOOR_Y:
			if self.velocity_y > 0:
				self.world_y = FLOOR_Y - self.height
				self.velocity_y = 0
				self.on_ground = True
			elif self.velocity_y < 0:
				self.world_y = FLOOR_Y + FLOOR_HEIGHT
				self.velocity_y = 0

		if self.world_y < 0:
			self.world_y = 0
			self.velocity_y = 0

	def attack_player(self, player):
		if self.attack_timer > 0:
			self.attack_timer -= 1
			return
		enemy_rect = self.get_rect()
		player_rect = player.get_rect()
		horizontal_touch = abs(enemy_rect.right - player_rect.left) <= 1 or abs(enemy_rect.left - player_rect.right) <= 1
		if horizontal_touch and abs(player.world_y - self.world_y) < 40:
			player.health = max(0, player.health - self.damage)
			self.attack_timer = ATTACK_COOLDOWN_FRAMES

	def resolve_overlap_with_player(self, player):
		if not self.get_rect().colliderect(player.get_rect()):
			return
		if player.is_squashing_enemy(self):
			return
		if player.world_x < self.world_x:
			self.world_x = player.world_x + player.width
		else:
			self.world_x = player.world_x - self.width
		self.velocity_x = 0

	def update(self, player):
		if not self.is_alive:
			return
		self.move_toward_player(player)
		self.apply_gravity()
		self.move_and_collide()
		self.attack_player(player)
		self.resolve_overlap_with_player(player)
		self.anim_timer += 1
		if self.anim_timer >= 6:
			self.anim_timer = 0
			self.anim_frame += 1

	def draw(self, surface):
		if not self.is_alive:
			return
		rect = self.get_screen_rect()
		walking = self.on_ground and abs(self.velocity_x) > 1
		draw_actor(surface, rect, (220, 80, 80), self.anim_frame, walking)
		# Health bar
		bar_w = self.width
		ratio = self.health / self.max_health
		pygame.draw.rect(surface, (60, 0, 0), pygame.Rect(rect.x, rect.y - 12, bar_w, 5))
		pygame.draw.rect(surface, (230, 80, 80), pygame.Rect(rect.x, rect.y - 12, int(bar_w * ratio), 5))

	def take_damage(self, amount, knockback_direction=1):
		self.health = max(0, self.health - amount)
		self.velocity_x = knockback_direction * 10
		self.velocity_y = -8
		if self.health == 0:
			self.is_alive = False

def draw_button(surface, text, rect, hovered, enabled=True):
	if not enabled:
		color = (90, 90, 90)
	elif hovered:
		color = (160, 220, 110)
	else:
		color = (120, 190, 80)
	pygame.draw.rect(surface, color, rect)
	pygame.draw.rect(surface, (255, 255, 255), rect, 3)
	text_surface = FONT.render(text, True, (20, 20, 20))
	surface.blit(text_surface, (rect.centerx - text_surface.get_width() // 2,
		rect.centery - text_surface.get_height() // 2))

def mana_icon(frame):
	return MANA_FRAMES[(frame // 8) % len(MANA_FRAMES)]

def title_screen():
	play_button = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 - 30, 200, 50)
	exit_button = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 40, 200, 50)
	while True:
		mouse_pos = pygame.mouse.get_pos()
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				return False
			if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
				if play_button.collidepoint(mouse_pos):
					return True
				if exit_button.collidepoint(mouse_pos):
					pygame.quit()
					return False
		SCREEN.fill((18, 22, 45))
		SCREEN.blit(TITLE_FONT.render("Game Jam", True, (255, 255, 255)), (WIDTH // 2 - 150, HEIGHT // 2 - 140))
		SCREEN.blit(FONT.render("Press Play to begin", True, (220, 220, 220)), (WIDTH // 2 - 100, HEIGHT // 2 - 80))
		draw_button(SCREEN, "Play", play_button, play_button.collidepoint(mouse_pos))
		draw_button(SCREEN, "Exit", exit_button, exit_button.collidepoint(mouse_pos))
		pygame.display.flip()
		CLOCK.tick(60)

# Each item: label, cost, and an effect(player) callable returning a result string.
SHOP_ITEMS = [
	("Heal to Full (15)", 15, lambda p: _heal(p)),
	("+2 Max Speed (25)", 25, lambda p: _upgrade_speed(p)),
	("+2 Jump Power (25)", 25, lambda p: _upgrade_jump(p)),
	("+25 Max Health (30)", 30, lambda p: _upgrade_health(p)),
]

def _heal(player):
	if player.health >= player.max_health:
		return "Already at full health"
	player.health = player.max_health
	return "Health restored"

def _upgrade_speed(player):
	player.max_speed += 2
	return "Max speed increased"

def _upgrade_jump(player):
	player.jump_velocity -= 2
	return "Jump power increased"

def _upgrade_health(player):
	player.max_health += 25
	player.health += 25
	return "Max health increased"

def shop_menu(player):
	"""Returns True to resume the game, False to quit the whole program."""
	button_rects = [pygame.Rect(WIDTH // 2 - 180, 160 + i * 70, 360, 50) for i in range(len(SHOP_ITEMS))]
	back_button = pygame.Rect(WIDTH // 2 - 100, 160 + len(SHOP_ITEMS) * 70 + 10, 200, 50)
	message = ""
	frame = 0
	while True:
		frame += 1
		mouse_pos = pygame.mouse.get_pos()
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				return False
			if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
				return True
			if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
				if back_button.collidepoint(mouse_pos):
					return True
				for rect, (label, cost, effect) in zip(button_rects, SHOP_ITEMS):
					if rect.collidepoint(mouse_pos):
						if player.coins >= cost:
							player.coins -= cost
							message = effect(player)
						else:
							message = "Not enough coins"

		SCREEN.fill((20, 24, 48))
		SCREEN.blit(TITLE_FONT.render("Shop", True, (255, 255, 255)), (WIDTH // 2 - 60, 50))
		SCREEN.blit(mana_icon(frame), (WIDTH // 2 - 90, 110))
		SCREEN.blit(FONT.render(f"Coins: {player.coins}", True, (255, 220, 120)), (WIDTH // 2 - 60, 115))
		for rect, (label, cost, effect) in zip(button_rects, SHOP_ITEMS):
			hovered = rect.collidepoint(mouse_pos)
			draw_button(SCREEN, label, rect, hovered, enabled=player.coins >= cost)
		draw_button(SCREEN, "Back", back_button, back_button.collidepoint(mouse_pos))
		if message:
			SCREEN.blit(FONT.render(message, True, (200, 230, 200)), (WIDTH // 2 - 180, back_button.bottom + 20))
		pygame.display.flip()
		CLOCK.tick(60)

def pause_menu(player):
	shop_button = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 - 20, 200, 50)
	exit_button = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 50, 200, 50)
	while True:
		mouse_pos = pygame.mouse.get_pos()
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				return False
			if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
				return True
			if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
				if shop_button.collidepoint(mouse_pos):
					if not shop_menu(player):
						return False
				if exit_button.collidepoint(mouse_pos):
					pygame.quit()
					return False
		overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
		overlay.fill((0, 0, 0, 50))
		SCREEN.blit(overlay, (0, 0))
		SCREEN.blit(TITLE_FONT.render("Paused", True, (255, 255, 255)), (WIDTH // 2 - 90, HEIGHT // 2 - 140))
		SCREEN.blit(FONT.render("Press ESC to resume", True, (220, 220, 220)), (WIDTH // 2 - 120, HEIGHT // 2 - 80))
		draw_button(SCREEN, "Shop", shop_button, shop_button.collidepoint(mouse_pos))
		draw_button(SCREEN, "Exit", exit_button, exit_button.collidepoint(mouse_pos))
		pygame.display.flip()
		CLOCK.tick(60)

def spawn_enemy(player, level):
	side = random.choice([-1, 1])
	distance = random.randint(WIDTH // 2 + 80, WIDTH // 2 + 360)
	x = player.world_x + side * distance
	return Enemy(x, FLOOR_Y - 40, level)

def main():
	if not title_screen():
		pygame.quit()
		return
	player = Player(100, HEIGHT - 80)
	enemies = [Enemy(600, FLOOR_Y - 40, 1)]
	level = 1
	total_kills = 0
	spawn_timer = SPAWN_COOLDOWN_FRAMES
	frame = 0
	running = True
	game_over = False
	while running:
		frame += 1
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				running = False
			if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
				if not game_over and not pause_menu(player):
					running = False
		if not running:
			break
		if not game_over:
			player.update()
			for enemy in enemies:
				if player.is_squashing_enemy(enemy):
					enemy.take_damage(100, player.facing)
					player.velocity_y = -8
				enemy.update(player)
			# Award and clear out defeated enemies
			killed = sum(1 for e in enemies if not e.is_alive)
			if killed:
				player.coins += COINS_PER_KILL * killed
				total_kills += killed
				enemies = [e for e in enemies if e.is_alive]
			level = 1 + total_kills // KILLS_PER_LEVEL
			# More enemies allowed on screen as level rises
			max_enemies = min(level, ENEMY_CAP)
			spawn_timer -= 1
			if len(enemies) < max_enemies and spawn_timer <= 0:
				enemies.append(spawn_enemy(player, level))
				spawn_timer = SPAWN_COOLDOWN_FRAMES
			if player.health <= 0:
				game_over = True

		SCREEN.fill((25, 28, 40))
		pygame.draw.rect(SCREEN, (90, 90, 110), pygame.Rect(0, FLOOR_Y - camera_offset_y, WIDTH, FLOOR_HEIGHT))
		pygame.draw.rect(SCREEN, (50, 50, 65), pygame.Rect(0, FLOOR_Y + FLOOR_HEIGHT - camera_offset_y, WIDTH, HEIGHT))
		for enemy in enemies:
			enemy.draw(SCREEN)
		player.draw(SCREEN)
		SCREEN.blit(FONT.render(f"Health: {player.health}/{player.max_health}", True, (255, 255, 255)), (16, 12))
		SCREEN.blit(FONT.render(f"Level: {level}", True, (180, 230, 255)), (16, 40))
		SCREEN.blit(FONT.render(f"Enemies: {len(enemies)}", True, (255, 210, 210)), (16, 68))
		SCREEN.blit(mana_icon(frame), (16, 96))
		SCREEN.blit(FONT.render(f"{player.coins}", True, (255, 220, 120)), (40, 100))
		if game_over:
			SCREEN.blit(TITLE_FONT.render("Game Over", True, (255, 120, 120)), (WIDTH // 2 - 130, HEIGHT // 2 - 40))
			SCREEN.blit(FONT.render(f"Reached level {level} - {total_kills} kills", True, (255, 200, 200)),
				(WIDTH // 2 - 140, HEIGHT // 2 + 20))
		pygame.display.flip()
		CLOCK.tick(60)
	pygame.quit()

if __name__ == "__main__":
	main()