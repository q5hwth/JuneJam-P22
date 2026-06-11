import pygame
import random
import math

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

WIDTH, HEIGHT = 800, 600
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Adaptation")
CLOCK = pygame.time.Clock()
FONT       = pygame.font.SysFont("arial", 18)
FONT_SM    = pygame.font.SysFont("arial", 13)
FONT_LG    = pygame.font.SysFont("arial", 28, bold=True)
TITLE_FONT = pygame.font.SysFont("arial", 52, bold=True)
PIXEL_FONT = pygame.font.SysFont("courier", 16, bold=True)

# ── Physics ───────────────────────────────────────────────────────────────────
GRAVITY              = 0.7
ACCELERATION         = 0.8
FRICTION             = 0.78
JUMP_VELOCITY        = -15
MAX_SPEED            = 8
FLOOR_Y              = HEIGHT - 40
FLOOR_HEIGHT         = 40
ENEMY_SPEED          = 2.5
COYOTE_TIME_FRAMES   = 8
ENEMY_DAMAGE         = 1
ATTACK_COOLDOWN      = 45
PARTICLE_LIFETIME    = 22
PARTICLE_SPAWN_RATE  = 3

# ── Dash ──────────────────────────────────────────────────────────────────────
DASH_SPEED           = 22
DASH_DURATION        = 8
DASH_COOLDOWN        = 120

# ── XP ────────────────────────────────────────────────────────────────────────
XP_PER_KILL          = 3
XP_PER_LEVEL         = 50
XP_PER_ORB           = 5

# ── Health (hearts) ───────────────────────────────────────────────────────────
MAX_HEARTS           = 10
LOW_HEALTH_THRESHOLD = 2

# ── Camera ────────────────────────────────────────────────────────────────────
PLAYER_SCREEN_X = WIDTH  // 2
PLAYER_SCREEN_Y = HEIGHT - 120
camera_offset_x = 0
camera_offset_y = 0

# ── Screen Shake ──────────────────────────────────────────────────────────────
shake_timer    = 0
shake_strength = 0
shake_x        = 0
shake_y        = 0

def trigger_shake(strength, duration):
    global shake_timer, shake_strength
    shake_timer    = max(shake_timer, duration)
    shake_strength = max(shake_strength, strength)

def update_shake():
    global shake_timer, shake_strength, shake_x, shake_y
    if shake_timer > 0:
        shake_timer -= 1
        t = shake_timer / max(1, shake_strength * 3)
        mag = shake_strength * t
        shake_x = random.randint(-int(mag), int(mag))
        shake_y = random.randint(-int(mag), int(mag))
    else:
        shake_x = shake_y = 0

# ── Audio ─────────────────────────────────────────────────────────────────────
def _make_beep(freq, duration_ms, vol=0.4, wave="square", decay=True):
    """Synthesize a simple sound effect procedurally."""
    sample_rate = 44100
    n = int(sample_rate * duration_ms / 1000)
    buf = []
    for i in range(n):
        t = i / sample_rate
        f = freq
        if wave == "square":
            v = 1.0 if math.sin(2 * math.pi * f * t) > 0 else -1.0
        elif wave == "noise":
            v = random.uniform(-1, 1)
        else:
            v = math.sin(2 * math.pi * f * t)
        if decay:
            v *= max(0, 1 - i / n)
        buf.append(int(v * vol * 32767))
    import array as arr
    stereo = arr.array('h')
    for s in buf:
        stereo.append(s)
        stereo.append(s)
    sound = pygame.sndarray.make_sound(pygame.surfarray.make_surface(
        __import__('numpy').array([[s, s] for s in buf], dtype='int16')
    )) if False else None
    # Fallback: build via bytes
    raw = arr.array('h')
    for s in buf:
        raw.append(max(-32767, min(32767, s)))
        raw.append(max(-32767, min(32767, s)))
    snd = pygame.mixer.Sound(buffer=raw)
    return snd

# Build sound library
_SOUNDS = {}
def _init_sounds():
    try:
        import numpy as np
        sr = 44100
        def synth(freqs, dur, vol=0.4, wave="sine", vibrato=0):
            n = int(sr * dur)
            t = np.linspace(0, dur, n, False)
            sig = np.zeros(n)
            for f in freqs:
                if wave == "square":
                    sig += np.sign(np.sin(2 * np.pi * (f + vibrato * np.sin(2*np.pi*6*t)) * t))
                elif wave == "noise":
                    sig += np.random.uniform(-1, 1, n)
                else:
                    sig += np.sin(2 * np.pi * (f + vibrato * np.sin(2*np.pi*6*t)) * t)
            env = np.linspace(1, 0, n) ** 0.5
            sig = (sig / max(len(freqs), 1)) * env * vol
            sig = np.clip(sig, -1, 1)
            audio = (sig * 32767).astype(np.int16)
            stereo = np.column_stack([audio, audio])
            return pygame.sndarray.make_sound(stereo)

        _SOUNDS['jump']     = synth([220, 440], 0.12, 0.3, "sine")
        _SOUNDS['dash']     = synth([880], 0.1, 0.35, "square")
        _SOUNDS['stomp']    = synth([110, 55], 0.18, 0.5, "square")
        _SOUNDS['hit']      = synth([160, 80], 0.15, 0.4, "square")
        _SOUNDS['levelup']  = synth([262, 330, 392, 523], 0.6, 0.45, "sine")
        _SOUNDS['raid']     = synth([196, 220, 294], 0.5, 0.45, "square")
        _SOUNDS['crit']     = synth([523, 659, 784], 0.25, 0.5, "sine", vibrato=10)
        _SOUNDS['coin']     = synth([660, 880], 0.1, 0.3, "sine")
        _SOUNDS['shop']     = synth([330, 440, 550], 0.3, 0.35, "sine")
    except Exception:
        pass  # no numpy – silent mode

_init_sounds()

def play_sound(name):
    snd = _SOUNDS.get(name)
    if snd:
        try:
            snd.play()
        except Exception:
            pass

# ── Infinite platform generation ──────────────────────────────────────────────
CHUNK_HEIGHT = 240
PLAT_RNG     = random.Random(1337)

# Zone thresholds (world-Y above floor)
ZONE_EASY_MAX   =  600   # 0–600 above floor = easy
ZONE_MED_MAX    = 1800   # 600–1800 = medium
# above 1800 = hard

def altitude_above_floor(world_y):
    return FLOOR_Y - world_y

def zone_for_altitude(alt):
    if alt < ZONE_EASY_MAX:
        return "easy"
    elif alt < ZONE_MED_MAX:
        return "medium"
    return "hard"

# All platform data: (rect, type)
# type: "normal", "spike", "bounce", "moving", "falling"
PLATFORMS_DATA = []  # list of [rect, plat_type, extra_data]

# Static low platforms
_static_plats = [
    pygame.Rect(-300, FLOOR_Y - 120, 200, 18),
    pygame.Rect( 250, FLOOR_Y - 120, 200, 18),
    pygame.Rect( 800, FLOOR_Y - 120, 200, 18),
    pygame.Rect( -80, FLOOR_Y - 240, 180, 18),
    pygame.Rect( 430, FLOOR_Y - 240, 180, 18),
    pygame.Rect( 980, FLOOR_Y - 240, 180, 18),
    pygame.Rect( 150, FLOOR_Y - 360, 160, 18),
    pygame.Rect( 660, FLOOR_Y - 360, 160, 18),
    pygame.Rect( 380, FLOOR_Y - 480, 160, 18),
]
for r in _static_plats:
    PLATFORMS_DATA.append([r, "normal", {}])

PLATFORMS = [d[0] for d in PLATFORMS_DATA]  # kept in sync

generated_chunks = set()
moving_platforms = []   # separate list for easy updating

def ensure_platforms_above(world_y):
    chunk = int(-(world_y - FLOOR_Y) // CHUNK_HEIGHT) + 1
    for c in range(0, chunk + 3):
        if c in generated_chunks:
            continue
        generated_chunks.add(c)
        if c <= 1:
            continue
        base_y = FLOOR_Y - c * CHUNK_HEIGHT
        alt = FLOOR_Y - base_y
        zone = zone_for_altitude(alt)

        if zone == "easy":
            count   = PLAT_RNG.randint(3, 5)
            min_w, max_w = 120, 220
            gap_mul = 1.0
        elif zone == "medium":
            count   = PLAT_RNG.randint(2, 4)
            min_w, max_w = 80, 160
            gap_mul = 1.3
        else:
            count   = PLAT_RNG.randint(2, 3)
            min_w, max_w = 50, 110
            gap_mul = 1.8

        xs = sorted(PLAT_RNG.sample(range(-400, 1300, int(120 * gap_mul)), min(count, 8)))
        for x in xs:
            w     = PLAT_RNG.randint(min_w, max_w)
            y_off = PLAT_RNG.randint(-40, 40)
            rect  = pygame.Rect(x, base_y + y_off, w, 18)

            # Determine platform type by zone + chance
            r = PLAT_RNG.random()
            if zone == "easy":
                if r < 0.05:
                    ptype = "bounce"
                elif r < 0.08:
                    ptype = "spike"
                else:
                    ptype = "normal"
            elif zone == "medium":
                if r < 0.12:
                    ptype = "bounce"
                elif r < 0.20:
                    ptype = "spike"
                elif r < 0.28:
                    ptype = "moving"
                elif r < 0.33:
                    ptype = "falling"
                else:
                    ptype = "normal"
            else:
                if r < 0.15:
                    ptype = "bounce"
                elif r < 0.28:
                    ptype = "spike"
                elif r < 0.42:
                    ptype = "moving"
                elif r < 0.52:
                    ptype = "falling"
                else:
                    ptype = "normal"

            extra = {}
            if ptype == "moving":
                extra = {"ox": x, "range": PLAT_RNG.randint(60, 160),
                         "speed": PLAT_RNG.uniform(0.8, 2.0),
                         "phase": PLAT_RNG.uniform(0, math.tau)}
                moving_platforms.append(len(PLATFORMS_DATA))
            elif ptype == "falling":
                extra = {"shake_timer": 0, "fallen": False, "respawn": 0}

            PLATFORMS_DATA.append([rect, ptype, extra])
            PLATFORMS.append(rect)

        # Occasionally add enemy nest spawner marker at hard altitude
        if zone == "hard" and PLAT_RNG.random() < 0.4:
            nest_x = PLAT_RNG.randint(-200, 1100)
            nest_rect = pygame.Rect(nest_x, base_y - 20, 10, 10)
            PLATFORMS_DATA.append([nest_rect, "nest", {"y": base_y}])
            PLATFORMS.append(nest_rect)  # not collidable but tracked

# ── Moving platform updater ────────────────────────────────────────────────────
_tick = 0

def update_platforms():
    global _tick
    _tick += 1
    for idx in moving_platforms:
        if idx >= len(PLATFORMS_DATA):
            continue
        data = PLATFORMS_DATA[idx]
        rect, ptype, extra = data
        if ptype != "moving":
            continue
        ox   = extra["ox"]
        rng  = extra["range"]
        spd  = extra["speed"]
        ph   = extra["phase"]
        new_x = int(ox + math.sin(_tick * spd * 0.02 + ph) * rng)
        rect.x = new_x
        data[0] = rect

def trigger_falling_platform(idx, player):
    """When player lands on a falling platform, start shake countdown."""
    if idx >= len(PLATFORMS_DATA):
        return
    data = PLATFORMS_DATA[idx]
    rect, ptype, extra = data
    if ptype != "falling":
        return
    if extra.get("fallen"):
        return
    if extra.get("shake_timer", 0) == 0:
        extra["shake_timer"] = 60  # 1 second then fall

def update_falling_platforms():
    for i, data in enumerate(PLATFORMS_DATA):
        rect, ptype, extra = data
        if ptype != "falling":
            continue
        if extra.get("fallen"):
            extra["respawn"] = extra.get("respawn", 0) - 1
            if extra["respawn"] <= 0:
                extra["fallen"] = False
                extra["shake_timer"] = 0
                # restore rect to original
            continue
        if extra.get("shake_timer", 0) > 0:
            extra["shake_timer"] -= 1
            if extra["shake_timer"] == 0:
                extra["fallen"] = True
                extra["respawn"] = 300  # 5 sec respawn
                # push rect offscreen
                rect.y += 9999
                data[0] = rect

# ── Parallax layers ───────────────────────────────────────────────────────────
class ParallaxLayer:
    def __init__(self, color, rects, factor):
        self.factor = factor
        self.surf = pygame.Surface((WIDTH * 2, HEIGHT), pygame.SRCALPHA)
        self.surf.fill((0, 0, 0, 0))
        for r in rects:
            pygame.draw.rect(self.surf, color, r)
            pygame.draw.rect(self.surf, color, r.move(WIDTH, 0))

    def draw(self, surface, cam_x, cam_y):
        scroll_x = int(cam_x * self.factor) % WIDTH
        scroll_y = int(cam_y * self.factor * 0.25)
        surface.blit(self.surf, (-scroll_x, -scroll_y))
        if scroll_x > 0:
            surface.blit(self.surf, (WIDTH - scroll_x, -scroll_y))


def build_parallax_layers():
    layers = []
    rng = random.Random(99)

    rects = []
    for i in range(7):
        x = i * 140 - 40
        w = rng.randint(100, 170)
        h = rng.randint(130, 230)
        rects.append(pygame.Rect(x, HEIGHT - FLOOR_HEIGHT - h, w, h))
    layers.append(ParallaxLayer((34, 38, 68, 210), rects, 0.12))

    rects = []
    for i in range(9):
        x = i * 100 - 20
        w = rng.randint(65, 115)
        h = rng.randint(55, 125)
        rects.append(pygame.Rect(x, HEIGHT - FLOOR_HEIGHT - h, w, h))
    layers.append(ParallaxLayer((44, 50, 86, 190), rects, 0.32))

    rects = []
    for i in range(12):
        x = i * 75 - 10
        w = rng.randint(25, 55)
        h = rng.randint(35, 95)
        rects.append(pygame.Rect(x, HEIGHT - FLOOR_HEIGHT - h, w, h))
    layers.append(ParallaxLayer((55, 62, 98, 170), rects, 0.58))

    return layers


# ── Particles ─────────────────────────────────────────────────────────────────
class Particle:
    def __init__(self, x, y, vx, vy, color=(250, 220, 120),
                 lifetime=PARTICLE_LIFETIME, size=5, use_gravity=False):
        self.world_x  = x
        self.world_y  = y
        self.vx       = vx
        self.vy       = vy
        self.age      = 0
        self.lifetime = lifetime
        self.size     = size
        self.color    = color
        self.use_gravity = use_gravity

    def update(self):
        self.world_x += self.vx
        self.world_y += self.vy
        if self.use_gravity:
            self.vy += 0.25
        self.vx *= 0.96
        self.age += 1

    def is_alive(self):
        return self.age < self.lifetime

    def draw(self, surface):
        t = 1 - self.age / self.lifetime
        alpha = int(255 * t)
        sz = max(1, int(self.size * t))
        surf = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*self.color, alpha), (sz, sz), sz)
        surface.blit(surf, (self.world_x - camera_offset_x + shake_x - sz,
                            self.world_y - camera_offset_y + shake_y - sz))


def burst(x, y, color, n=10, speed=4, lifetime=20, size=4, gravity=True):
    parts = []
    for i in range(n):
        angle = (i / n) * math.tau + random.uniform(-0.3, 0.3)
        s = random.uniform(speed * 0.5, speed)
        parts.append(Particle(x, y, math.cos(angle) * s, math.sin(angle) * s,
                               color=color, lifetime=lifetime, size=size,
                               use_gravity=gravity))
    return parts


# ── XP Orb / Coin / Health pickup ─────────────────────────────────────────────
class Collectible:
    def __init__(self, x, y, ctype="xp"):
        self.world_x  = x
        self.world_y  = y
        self.ctype    = ctype   # "xp", "coin", "health"
        self.vel_y    = -4.0
        self.age      = 0
        self.collected = False
        self.bob_offset = random.uniform(0, math.tau)
        self.radius   = 7

    def update(self):
        self.vel_y = min(self.vel_y + 0.3, 6)
        self.world_y += self.vel_y
        if self.world_y + self.radius >= FLOOR_Y:
            self.world_y = FLOOR_Y - self.radius
            self.vel_y   = 0
        for plat in PLATFORMS:
            if (self.world_x >= plat.left and self.world_x <= plat.right and
                    self.world_y + self.radius >= plat.top and
                    self.world_y + self.radius <= plat.top + 20):
                self.world_y = plat.top - self.radius
                self.vel_y   = 0
        self.age += 1

    def get_rect(self):
        return pygame.Rect(self.world_x - self.radius, self.world_y - self.radius,
                           self.radius * 2, self.radius * 2)

    def draw(self, surface):
        bob = math.sin(self.age * 0.08 + self.bob_offset) * 2
        sx = int(self.world_x - camera_offset_x + shake_x)
        sy = int(self.world_y - camera_offset_y + shake_y + bob)
        r  = self.radius
        if self.ctype == "xp":
            col = (80, 255, 120)
            glow_col = (20, 120, 40)
        elif self.ctype == "coin":
            col = (255, 220, 40)
            glow_col = (140, 100, 0)
        else:  # health
            col = (255, 80, 100)
            glow_col = (120, 20, 40)

        # Glow
        g_surf = pygame.Surface((r * 6, r * 6), pygame.SRCALPHA)
        pygame.draw.circle(g_surf, (*glow_col, 60), (r * 3, r * 3), r * 3)
        surface.blit(g_surf, (sx - r * 3, sy - r * 3))

        # Pixel square collectible
        size = r * 2
        pygame.draw.rect(surface, col, (sx - r, sy - r, size, size))
        pygame.draw.rect(surface, (255, 255, 255), (sx - r, sy - r, size, size), 1)
        # Inner shine
        pygame.draw.rect(surface, (255, 255, 255), (sx - r + 2, sy - r + 1, 3, 2))


# ── Player (pixel glowing cube) ───────────────────────────────────────────────
_PLAYER_CACHE = {}

def _build_player_surf(facing, dashing, frame, state="idle", double_jump_flash=False):
    key = (facing, dashing, frame % 12, state, double_jump_flash)
    if key in _PLAYER_CACHE:
        return _PLAYER_CACHE[key]

    W, H = 32, 32
    surf = pygame.Surface((W + 16, H + 16), pygame.SRCALPHA)

    # White light glow radius
    cx, cy = (W + 16) // 2, (H + 16) // 2
    for gr in range(18, 0, -2):
        alpha = int(40 * (1 - gr / 18))
        if dashing:
            gc = (100, 200, 255, alpha)
        elif double_jump_flash:
            gc = (180, 255, 100, alpha)
        elif state == "hurt":
            gc = (255, 100, 80, alpha)
        else:
            gc = (200, 230, 255, alpha)
        g_surf = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(g_surf, gc, (gr, gr), gr)
        surf.blit(g_surf, (cx - gr, cy - gr))

    # Core cube (pixel art)
    ox, oy = 8, 8  # offset inside surface

    if dashing:
        FACE   = (160, 235, 255)
        TOP    = (220, 255, 255)
        SIDE   = (80, 170, 230)
        CORE   = (200, 255, 255)
        EDGE   = (20, 80, 160)
    elif state == "hurt":
        FACE   = (255, 140, 120)
        TOP    = (255, 200, 180)
        SIDE   = (200, 60, 60)
        CORE   = (255, 180, 160)
        EDGE   = (80, 0, 0)
    else:
        FACE   = (90, 180, 255)
        TOP    = (160, 220, 255)
        SIDE   = (40, 110, 210)
        CORE   = (220, 245, 255)
        EDGE   = (15, 40, 100)

    f = frame % 12
    bob = int(math.sin(f * math.pi / 6) * 1) if state == "idle" else 0
    jump_squish = -2 if state == "jump" else (2 if state == "fall" else 0)

    cw, ch = 22, 22 + jump_squish
    bx = ox + (W - cw) // 2
    by = oy + (H - ch) // 2 + bob

    # Front face
    pygame.draw.rect(surf, FACE, (bx, by, cw, ch))

    # Top face (isometric)
    th = 6
    top_pts = [
        (bx, by),
        (bx + cw, by),
        (bx + cw + th, by - th),
        (bx + th, by - th)
    ]
    pygame.draw.polygon(surf, TOP, top_pts)

    # Side face
    if facing == 1:
        side_pts = [
            (bx + cw, by),
            (bx + cw + th, by - th),
            (bx + cw + th, by - th + ch),
            (bx + cw, by + ch)
        ]
    else:
        side_pts = [
            (bx, by),
            (bx - th, by - th),
            (bx - th, by - th + ch),
            (bx, by + ch)
        ]
    pygame.draw.polygon(surf, SIDE, side_pts)

    # Edge outline
    pygame.draw.rect(surf, EDGE, (bx, by, cw, ch), 1)

    # Blue core (glowing inner pixel)
    core_size = 6
    cx2 = bx + cw // 2 - core_size // 2
    cy2 = by + ch // 2 - core_size // 2
    pygame.draw.rect(surf, CORE, (cx2, cy2, core_size, core_size))
    # Core shimmer
    shine_alpha = int(150 + 80 * math.sin(f * math.pi / 6))
    sc = pygame.Surface((core_size, core_size), pygame.SRCALPHA)
    sc.fill((255, 255, 255, shine_alpha))
    surf.blit(sc, (cx2, cy2))

    # Pixel "eye" — small bright dot in facing direction
    ex = bx + cw - 4 if facing == 1 else bx + 2
    ey = by + ch // 2 - 2
    pygame.draw.rect(surf, (255, 255, 255), (ex, ey, 3, 3))
    pygame.draw.rect(surf, (100, 200, 255), (ex + 1, ey + 1, 1, 1))

    # Running particles / anim — small trailing pixel
    if state == "run":
        tail_alpha = int(100 + 80 * math.sin(f * math.pi / 3))
        tc = pygame.Surface((4, 4), pygame.SRCALPHA)
        tc.fill((*SIDE, tail_alpha))
        tx = bx - 6 if facing == 1 else bx + cw + 2
        surf.blit(tc, (tx, by + ch - 8))

    # Dash afterimage tint
    if dashing:
        tint = pygame.Surface((W + 16, H + 16), pygame.SRCALPHA)
        tint.fill((80, 200, 255, 50))
        surf.blit(tint, (0, 0))

    _PLAYER_CACHE[key] = surf
    return surf


# ── Enemy drawing (all types) ─────────────────────────────────────────────────
_ENEMY_CACHE = {}

def _build_enemy_surf(frame, flash=False, enemy_type=0, size_scale=1.0):
    key = (frame % 12, flash, enemy_type)
    if key in _ENEMY_CACHE:
        return _ENEMY_CACHE[key]

    # Enemy is a dark pixel cube, larger than player
    W, H = int(40 * size_scale), int(40 * size_scale)
    surf = pygame.Surface((W + 8, H + 8), pygame.SRCALPHA)

    # Type colors
    if enemy_type == 1:    # Elite (purple)
        FACE  = (150, 50, 200) if not flash else (220, 150, 255)
        TOP   = (100, 20, 150) if not flash else (180, 100, 220)
        SIDE  = (60, 10, 110)
        CORE  = (200, 80, 255)
        EDGE  = (20, 0, 40)
    elif enemy_type == 2:  # Jumper (teal)
        FACE  = (30, 180, 160) if not flash else (150, 255, 240)
        TOP   = (20, 130, 110)
        SIDE  = (10, 80, 70)
        CORE  = (100, 255, 220)
        EDGE  = (0, 30, 25)
    elif enemy_type == 3:  # Charger (orange)
        FACE  = (220, 120, 20) if not flash else (255, 200, 100)
        TOP   = (160, 80, 10)
        SIDE  = (100, 50, 5)
        CORE  = (255, 180, 50)
        EDGE  = (40, 15, 0)
    elif enemy_type == 4:  # Flying (dark blue)
        FACE  = (40, 50, 180) if not flash else (150, 160, 255)
        TOP   = (25, 35, 130)
        SIDE  = (15, 20, 90)
        CORE  = (100, 120, 255)
        EDGE  = (5, 5, 50)
    elif enemy_type == 5:  # Boss (dark red/black)
        FACE  = (120, 20, 20) if not flash else (255, 100, 100)
        TOP   = (80, 10, 10)
        SIDE  = (40, 5, 5)
        CORE  = (255, 60, 60)
        EDGE  = (5, 0, 0)
    else:                  # Standard (dark red)
        FACE  = (180, 40, 40) if not flash else (255, 150, 150)
        TOP   = (120, 20, 20)
        SIDE  = (70, 10, 10)
        CORE  = (255, 80, 80)
        EDGE  = (20, 0, 0)

    f = frame % 12
    bob = int(math.sin(f * math.pi / 6) * 2)

    ox, oy = 4, 4
    cw, ch = W - 4, H - 4
    bx = ox
    by = oy + bob

    # Dark ambient glow
    for gr in range(12, 0, -3):
        alpha = int(30 * (1 - gr / 12))
        g_surf = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(g_surf, (*EDGE, alpha), (gr, gr), gr)
        surf.blit(g_surf, (W // 2 - gr + 4, H // 2 - gr + 4))

    # Front face (darker tint than player)
    pygame.draw.rect(surf, FACE, (bx, by, cw, ch))

    # Top face
    th = 5
    top_pts = [(bx, by), (bx + cw, by), (bx + cw + th, by - th), (bx + th, by - th)]
    pygame.draw.polygon(surf, TOP, top_pts)

    # Side face (right)
    side_pts = [(bx + cw, by), (bx + cw + th, by - th),
                (bx + cw + th, by - th + ch), (bx + cw, by + ch)]
    pygame.draw.polygon(surf, SIDE, side_pts)

    pygame.draw.rect(surf, EDGE, (bx, by, cw, ch), 1)

    # Core glow
    cs = 5
    pygame.draw.rect(surf, CORE, (bx + cw // 2 - cs // 2, by + ch // 2 - cs // 2, cs, cs))

    # Pixel "angry eyes"
    for ex_off in [cw // 4, 3 * cw // 4 - 3]:
        ey = by + ch // 3
        pygame.draw.rect(surf, CORE, (bx + ex_off, ey, 4, 3))
        pygame.draw.rect(surf, (5, 0, 0), (bx + ex_off + 1, ey + 1, 2, 1))

    # Type-specific visual features
    if enemy_type == 4:  # Flying: small wings
        wing_col = (60, 80, 220)
        pygame.draw.polygon(surf, wing_col,
            [(bx - 8, by + ch // 2), (bx, by + 2), (bx, by + ch - 2)])
        pygame.draw.polygon(surf, wing_col,
            [(bx + cw + 8, by + ch // 2), (bx + cw, by + 2), (bx + cw, by + ch - 2)])
    elif enemy_type == 5:  # Boss: crown
        for cx_off in range(0, cw, 5):
            pygame.draw.rect(surf, (200, 180, 20), (bx + cx_off, by - 6, 3, 6))

    if flash:
        tint = pygame.Surface((W + 8, H + 8), pygame.SRCALPHA)
        tint.fill((255, 255, 255, 80))
        surf.blit(tint, (0, 0))

    _ENEMY_CACHE[key] = surf
    return surf


# ── Hearts HUD ────────────────────────────────────────────────────────────────
def draw_heart(surface, x, y, filled, low=False):
    color = (255, 60, 80) if filled else (80, 30, 40)
    if filled and low:
        pulse = abs(math.sin(pygame.time.get_ticks() * 0.008)) * 30
        color = (255, int(60 + pulse * 0.3), int(80 + pulse * 0.3))
    outline = (180, 20, 40) if filled else (50, 20, 30)
    hi      = (255, 150, 160) if filled else (100, 50, 60)
    pattern = [
        "  ##  ##  ",
        " #### ####",
        "##########",
        "##########",
        "##########",
        " ########",
        "  ######",
        "   ####",
        "    ##",
    ]
    for row, line in enumerate(pattern):
        for col, ch in enumerate(line):
            if ch == '#':
                px = x + col
                py = y + row
                c = hi if (row == 0 and col in [2,3,6,7]) else color
                surface.fill(c, (px, py, 1, 1))
    if filled:
        surface.fill(hi, (x + 2, y, 1, 1))
        surface.fill(hi, (x + 6, y, 1, 1))


def draw_hud(surface, player, combo=0, coins=0, objectives=None):
    hearts = player.hearts
    low    = hearts <= LOW_HEALTH_THRESHOLD

    panel_w = player.max_hearts * 14 + 10
    panel_r = pygame.Rect(10, 8, panel_w, 22)
    pygame.draw.rect(surface, (15, 10, 25, 180), panel_r, border_radius=4)
    pygame.draw.rect(surface, (80, 40, 60), panel_r, 1, border_radius=4)
    for i in range(player.max_hearts):
        hx = 14 + i * 14
        hy = 12
        filled = i < hearts
        draw_heart(surface, hx, hy, filled, low=low and filled)

    # XP bar
    XP_Y = 34
    BAR_X, BAR_W, BAR_H = 14, 160, 6
    xp_ratio = player.xp / player.xp_to_next
    pygame.draw.rect(surface, (10, 30, 10),   (BAR_X, XP_Y, BAR_W, BAR_H))
    pygame.draw.rect(surface, (80, 220, 40),  (BAR_X, XP_Y, int(BAR_W * xp_ratio), BAR_H))
    pygame.draw.rect(surface, (140, 255, 80), (BAR_X, XP_Y, BAR_W, BAR_H), 1)
    xp_txt = FONT_SM.render(f"Lv {player.level}", True, (120, 255, 60))
    surface.blit(xp_txt, (BAR_X + BAR_W + 6, XP_Y - 1))

    # Dash bar
    DASH_X, DASH_Y = 14, XP_Y + BAR_H + 8
    DASH_W, DASH_H = 80, 10
    actual_cd = player.upgrades.get("dash_cd", DASH_COOLDOWN)
    cd_ratio = 1.0 - (player.dash_cd / actual_cd) if actual_cd > 0 else 1.0
    pygame.draw.rect(surface, (20, 20, 40), (DASH_X - 2, DASH_Y - 2, DASH_W + 4, DASH_H + 4))
    pygame.draw.rect(surface, (20, 20, 60), (DASH_X, DASH_Y, DASH_W, DASH_H))
    dash_fill = (100, 220, 255) if player.dash_cd == 0 else (40, 100, 160)
    pygame.draw.rect(surface, dash_fill, (DASH_X, DASH_Y, int(DASH_W * cd_ratio), DASH_H))
    pygame.draw.rect(surface, (100, 160, 220), (DASH_X, DASH_Y, DASH_W, DASH_H), 1)
    label = "DASH ✓" if player.dash_cd == 0 else f"DASH {player.dash_cd // 60 + 1}s"
    dash_col = (200, 240, 255) if player.dash_cd == 0 else (120, 160, 200)
    surface.blit(FONT_SM.render(label, True, dash_col), (DASH_X + 2, DASH_Y))

    # Double jump indicator
    if player.upgrades.get("double_jump"):
        dj_col = (180, 255, 80) if player.double_jumps_left > 0 else (60, 80, 30)
        surface.blit(FONT_SM.render("2x↑" if player.double_jumps_left > 0 else "2x↑✗",
                                    True, dj_col), (DASH_X + DASH_W + 6, DASH_Y))

    # Coins
    coin_surf = FONT_SM.render(f"⬡ {coins}", True, (255, 220, 40))
    surface.blit(coin_surf, (14, DASH_Y + DASH_H + 6))

    # Combo counter
    if combo >= 2:
        scale = min(2.0, 1.0 + combo * 0.08)
        combo_color = (255, min(255, 100 + combo * 20), 30)
        cs = FONT_LG.render(f"COMBO x{combo}!", True, combo_color)
        surface.blit(cs, (WIDTH // 2 - cs.get_width() // 2, 90))

    # Objectives panel (bottom-left)
    if objectives:
        oy_start = HEIGHT - 14 - len(objectives) * 20
        for i, (text, done) in enumerate(objectives):
            col = (80, 255, 100) if done else (180, 180, 180)
            tick = "✓ " if done else "• "
            ots = FONT_SM.render(tick + text, True, col)
            surface.blit(ots, (10, oy_start + i * 20))

    # Zone indicator
    alt = altitude_above_floor(player.world_y)
    zone = zone_for_altitude(alt)
    zone_col = {"easy": (80, 220, 80), "medium": (220, 180, 40), "hard": (220, 60, 60)}[zone]
    zs = FONT_SM.render(f"Zone: {zone.upper()}  Alt: {int(alt)}", True, zone_col)
    surface.blit(zs, (WIDTH - zs.get_width() - 14, HEIGHT - 22))


# ── Player ────────────────────────────────────────────────────────────────────
class Player:
    def __init__(self, x, y):
        self.world_x       = x
        self.world_y       = y
        self.velocity_x    = 0.0
        self.velocity_y    = 0.0
        self.on_ground     = False
        self.hearts        = MAX_HEARTS
        self.max_hearts    = MAX_HEARTS
        self.facing        = 1
        self.width         = 40
        self.height        = 40
        self.particles     = []
        self.particle_timer = 0
        self.coyote_timer  = 0
        self.anim_frame    = 0
        self.dash_timer    = 0
        self.dash_cd       = 0
        self.xp            = 0
        self.level         = 1
        self.xp_to_next    = XP_PER_LEVEL
        self.hurt_timer    = 0
        self.double_jumps_left = 0
        self.hit_freeze    = 0   # frames frozen after stomp
        self.upgrades = {
            "max_hearts":    MAX_HEARTS,
            "dash_cd":       DASH_COOLDOWN,
            "jump_vel":      JUMP_VELOCITY,
            "max_speed":     MAX_SPEED,
            "stomp_dmg":     100,
            "double_jump":   False,
        }
        self.pending_levelup = False
        self.quiz_index      = 0   # which python question comes next
        self._last_on_ground = False

    @property
    def health(self):
        return self.hearts

    @health.setter
    def health(self, v):
        self.hearts = max(0, min(self.max_hearts, v))

    def get_rect(self):
        return pygame.Rect(self.world_x, self.world_y, self.width, self.height)

    def get_screen_rect(self):
        return pygame.Rect(PLAYER_SCREEN_X, PLAYER_SCREEN_Y, self.width, self.height)

    def handle_input(self, events):
        if self.hit_freeze > 0:
            return
        keys = pygame.key.get_pressed()
        accel = 0.0
        ms = self.upgrades["max_speed"]
        jv = self.upgrades["jump_vel"]
        if keys[pygame.K_a]:
            accel    -= ACCELERATION
            self.facing = -1
        if keys[pygame.K_d]:
            accel    += ACCELERATION
            self.facing = 1
        if keys[pygame.K_w]:
            if self.on_ground or self.coyote_timer > 0:
                self.velocity_y   = jv
                self.on_ground    = False
                self.coyote_timer = 0
                self._emit_jump_dust()
                play_sound('jump')
            elif self.upgrades.get("double_jump") and self.double_jumps_left > 0:
                self.velocity_y = jv * 0.85
                self.double_jumps_left -= 1
                self._double_jump_flash = 8
                play_sound('jump')
        if keys[pygame.K_s] and not self.on_ground:
            self.velocity_y += 0.5
        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                cd = self.upgrades["dash_cd"]
                if self.dash_cd == 0 and self.dash_timer == 0:
                    self.dash_timer = DASH_DURATION
                    self.dash_cd    = cd
                    cx = self.world_x + self.width  // 2
                    cy = self.world_y + self.height // 2
                    self.particles += burst(cx, cy, (100, 220, 255), n=14,
                                            speed=5, lifetime=16, size=5, gravity=False)
                    play_sound('dash')
        self.velocity_x += accel
        if accel == 0 and self.on_ground:
            self.velocity_x *= FRICTION
        else:
            self.velocity_x *= 0.985
        ms = self.upgrades["max_speed"]
        self.velocity_x = max(-ms, min(ms, self.velocity_x))

    def apply_gravity(self):
        if self.dash_timer > 0 or self.hit_freeze > 0:
            return
        self.velocity_y += GRAVITY

    def move_and_collide(self):
        global camera_offset_x, camera_offset_y
        if self.hit_freeze > 0:
            self.hit_freeze -= 1
            camera_offset_x = self.world_x - PLAYER_SCREEN_X
            camera_offset_y = self.world_y - PLAYER_SCREEN_Y
            return
        if self.dash_timer > 0:
            self.world_x    += int(self.facing * DASH_SPEED)
            self.velocity_x  = self.facing * self.upgrades["max_speed"]
            self.dash_timer -= 1
            if self.dash_timer % 2 == 0:
                cx = self.world_x + self.width  // 2
                cy = self.world_y + self.height // 2
                self.particles.append(
                    Particle(cx, cy,
                             -self.facing * random.uniform(1, 3),
                             random.uniform(-1, 1),
                             color=(80, 200, 255), lifetime=12, size=4))
        else:
            self.world_x += int(self.velocity_x)
        self.world_y   += int(self.velocity_y)
        self.on_ground  = False

        if self.world_y + self.height >= FLOOR_Y:
            self.world_y    = FLOOR_Y - self.height
            self.velocity_y = 0
            self.on_ground  = True

        if self.velocity_y >= 0:
            for i, data in enumerate(PLATFORMS_DATA):
                plat, ptype, extra = data
                if ptype in ("nest",):
                    continue
                if ptype == "falling" and extra.get("fallen"):
                    continue
                pr = self.get_rect()
                if pr.colliderect(plat):
                    prev_bottom = self.world_y + self.height - int(self.velocity_y)
                    if prev_bottom <= plat.top + 2:
                        if ptype == "spike":
                            self.take_damage(1)
                        elif ptype == "bounce":
                            self.velocity_y = self.upgrades["jump_vel"] * 1.3
                            play_sound('jump')
                        elif ptype == "falling":
                            trigger_falling_platform(i, self)
                            self.world_y    = plat.top - self.height
                            self.velocity_y = 0
                            self.on_ground  = True
                        else:
                            self.world_y    = plat.top - self.height
                            self.velocity_y = 0
                            self.on_ground  = True
                        break

        if self.on_ground:
            self.coyote_timer = COYOTE_TIME_FRAMES
            if not self._last_on_ground:
                self.double_jumps_left = 1  # restore on landing
        elif self.coyote_timer > 0:
            self.coyote_timer -= 1
        self._last_on_ground = self.on_ground

        camera_offset_x = self.world_x - PLAYER_SCREEN_X
        camera_offset_y = self.world_y - PLAYER_SCREEN_Y

    def _emit_jump_dust(self):
        for _ in range(6):
            vx = random.uniform(-2, 2)
            vy = random.uniform(-2, 0)
            self.particles.append(
                Particle(self.world_x + self.width // 2,
                         self.world_y + self.height,
                         vx, vy, color=(200, 200, 220),
                         lifetime=18, size=4, use_gravity=False))

    def _emit_run_dust(self):
        cx = self.world_x + (self.width if self.facing > 0 else 0)
        cy = self.world_y + self.height - 4
        vx = -self.facing * random.uniform(0.5, 1.5)
        vy = random.uniform(-0.5, 0.2)
        self.particles.append(
            Particle(cx, cy, vx, vy, color=(180, 180, 200),
                     lifetime=14, size=3, use_gravity=False))

    def update_particles(self):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.is_alive()]

    def gain_xp(self, amount):
        self.xp += amount
        while self.xp >= self.xp_to_next:
            self.xp        -= self.xp_to_next
            self.level     += 1
            self.hearts = min(self.max_hearts, self.hearts + 1)
            self.pending_levelup = True
            play_sound('levelup')

    def take_damage(self, amount):
        if self.hurt_timer > 0:
            return
        self.hearts    = max(0, self.hearts - amount)
        self.hurt_timer = 40  # invincibility frames
        trigger_shake(4, 12)
        if self.hearts <= LOW_HEALTH_THRESHOLD:
            trigger_shake(3, 8)

    def update(self, events):
        if not hasattr(self, '_double_jump_flash'):
            self._double_jump_flash = 0
        self.handle_input(events)
        self.apply_gravity()
        self.move_and_collide()
        ensure_platforms_above(self.world_y)
        update_platforms()
        update_falling_platforms()
        if self.dash_cd > 0:
            self.dash_cd -= 1
        self.update_particles()
        self.anim_frame += 1
        if self.hurt_timer > 0:
            self.hurt_timer -= 1
        if self._double_jump_flash > 0:
            self._double_jump_flash -= 1
        if (self.on_ground and abs(self.velocity_x) > 1
                and self.particle_timer <= 0):
            self._emit_run_dust()
            self.particle_timer = PARTICLE_SPAWN_RATE
        else:
            self.particle_timer -= 1

    def draw(self, surface):
        for p in self.particles:
            p.draw(surface)
        dashing = self.dash_timer > 0
        if dashing:
            state = "idle"
        elif self.hurt_timer > 0 and (self.hurt_timer // 4) % 2 == 0:
            state = "hurt"
        elif not self.on_ground:
            state = "jump" if self.velocity_y < 0 else "fall"
        elif abs(self.velocity_x) > 1:
            state = "run"
        else:
            state = "idle"
        djf = getattr(self, '_double_jump_flash', 0) > 0
        frame = self.anim_frame
        img   = _build_player_surf(self.facing, dashing, frame, state, djf)
        # Blink during hurt
        if self.hurt_timer > 0 and (self.hurt_timer // 4) % 2 == 1:
            img = img.copy()
            img.set_alpha(120)
        surface.blit(img, (PLAYER_SCREEN_X - 8 + shake_x, PLAYER_SCREEN_Y - 8 + shake_y))

    def is_squashing_enemy(self, enemy):
        if not enemy.is_alive:
            return False
        if self.velocity_y > 2 and self.get_rect().colliderect(enemy.get_rect()):
            if self.world_y + self.height <= enemy.get_rect().bottom + 20:
                return True
        return False


# ── Enemy base ────────────────────────────────────────────────────────────────
class Enemy:
    ENEMY_SIZES = {0: (36, 38), 1: (44, 46), 2: (32, 34),
                   3: (38, 40), 4: (36, 36), 5: (64, 60)}

    def __init__(self, x, y, enemy_type=0):
        self.world_x      = x
        self.world_y      = y
        self.velocity_x   = 0.0
        self.velocity_y   = 0.0
        self.on_ground    = False
        self.attack_timer = 0
        self.enemy_type   = enemy_type
        self.width, self.height = self.ENEMY_SIZES.get(enemy_type, (36, 38))
        hp_map = {0: 60, 1: 120, 2: 50, 3: 80, 4: 70, 5: 400}
        self.health       = hp_map.get(enemy_type, 60)
        self.max_health   = self.health
        self.is_alive     = True
        self.anim_frame   = 0
        self.flash_timer  = 0
        # Type-specific state
        self._jump_cd     = 0
        self._charge_state = "idle"   # for charger: idle, windup, charge
        self._charge_cd   = 0
        self._windup_timer = 0
        self._charge_dir  = 1
        self._boss_attack_timer = 0
        self._boss_phase  = 0
        self._spawn_cd    = 0  # for nest spawner

    def get_rect(self):
        return pygame.Rect(self.world_x, self.world_y, self.width, self.height)

    def get_screen_rect(self):
        return pygame.Rect(self.world_x - camera_offset_x + shake_x,
                           self.world_y - camera_offset_y + shake_y,
                           self.width, self.height)

    def apply_gravity(self):
        if self.enemy_type == 4:  # Flying ignores gravity
            return
        self.velocity_y += GRAVITY

    def move_toward_player(self, player):
        if not self.is_alive:
            return
        et = self.enemy_type
        if et == 0:   # Standard
            speed = ENEMY_SPEED
        elif et == 1: # Elite
            speed = ENEMY_SPEED * 1.3
        elif et == 2: # Jumper — handled separately
            return
        elif et == 3: # Charger — handled separately
            return
        elif et == 4: # Flying
            dx = (player.world_x + player.width // 2) - (self.world_x + self.width // 2)
            dy = (player.world_y + player.height // 2) - (self.world_y + self.height // 2)
            dist = math.hypot(dx, dy) or 1
            spd  = 2.2
            self.velocity_x = (dx / dist) * spd
            self.velocity_y = (dy / dist) * spd
            return
        elif et == 5: # Boss
            speed = ENEMY_SPEED * 0.8
        else:
            speed = ENEMY_SPEED

        if (self.world_x + self.width) <= player.world_x:
            self.velocity_x = speed
        elif self.world_x >= (player.world_x + player.width):
            self.velocity_x = -speed
        else:
            self.velocity_x = 0

    def _update_jumper(self, player):
        """Jumper: periodically leaps toward player."""
        self.move_toward_player(player)  # baseline walk
        self._jump_cd = max(0, self._jump_cd - 1)
        if self._jump_cd == 0 and self.on_ground:
            dx = player.world_x - self.world_x
            dist = abs(dx) or 1
            if dist < 500:
                self.velocity_y = -13
                self.velocity_x = (dx / dist) * 6
                self._jump_cd   = random.randint(60, 120)

    def _update_charger(self, player):
        """Charger: windup then dash."""
        self._charge_cd = max(0, self._charge_cd - 1)
        if self._charge_state == "idle":
            # Walk slowly toward player
            dx = (player.world_x - self.world_x)
            self.velocity_x = (1 if dx > 0 else -1) * 1.2
            if abs(dx) < 300 and self._charge_cd == 0:
                self._charge_state = "windup"
                self._windup_timer = 60
                self._charge_dir   = 1 if dx > 0 else -1
                self.velocity_x    = 0
        elif self._charge_state == "windup":
            self._windup_timer -= 1
            self.velocity_x     = 0
            if self._windup_timer <= 0:
                self._charge_state = "charge"
                self._charge_cd    = 18
        elif self._charge_state == "charge":
            self.velocity_x    = self._charge_dir * 18
            if self._charge_cd == 0:
                self._charge_state = "idle"
                self._charge_cd    = random.randint(90, 180)
                self.velocity_x    = 0

    def _update_boss(self, player):
        """Boss: mix of charge + jump + projectile (screen shake) attacks."""
        self.move_toward_player(player)
        self._boss_attack_timer = max(0, self._boss_attack_timer - 1)
        if self._boss_attack_timer == 0:
            # Cycle attacks
            phase = self._boss_phase % 3
            if phase == 0:
                # Ground slam
                if self.on_ground:
                    trigger_shake(8, 20)
                    self.velocity_y = -16
            elif phase == 1:
                # Charge
                dx = player.world_x - self.world_x
                self.velocity_x = (1 if dx > 0 else -1) * 14
            elif phase == 2:
                pass  # Just walk
            self._boss_phase         += 1
            self._boss_attack_timer   = random.randint(80, 140)

    def move_and_collide(self):
        if not self.is_alive:
            return
        if self.enemy_type != 4:
            self.world_x += int(self.velocity_x)
            self.world_y += int(self.velocity_y)
        else:
            self.world_x += int(self.velocity_x)
            self.world_y += int(self.velocity_y)

        self.on_ground = False
        if self.enemy_type != 4:
            if self.world_y + self.height >= FLOOR_Y:
                self.world_y    = FLOOR_Y - self.height
                self.velocity_y = 0
                self.on_ground  = True
            if self.velocity_y >= 0:
                for data in PLATFORMS_DATA:
                    plat, ptype, extra = data
                    if ptype in ("nest", "spike"):
                        continue
                    if ptype == "falling" and extra.get("fallen"):
                        continue
                    er = self.get_rect()
                    if er.colliderect(plat):
                        prev_bottom = self.world_y + self.height - int(self.velocity_y)
                        if prev_bottom <= plat.top + 2:
                            self.world_y    = plat.top - self.height
                            self.velocity_y = 0
                            self.on_ground  = True
                            break

    def attack_player(self, player):
        if not self.is_alive:
            return
        if self.attack_timer > 0:
            self.attack_timer -= 1
            return
        if (self.get_rect().colliderect(player.get_rect())
                and abs(player.world_y - self.world_y) < 60):
            dmg_map = {0: 1, 1: 2, 2: 1, 3: 2, 4: 1, 5: 3}
            player.take_damage(dmg_map.get(self.enemy_type, 1))
            self.attack_timer = ATTACK_COOLDOWN

    def resolve_overlap_with_player(self, player):
        if not self.is_alive:
            return
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
        et = self.enemy_type
        if et == 2:
            self._update_jumper(player)
        elif et == 3:
            self._update_charger(player)
        elif et == 5:
            self._update_boss(player)
        else:
            self.move_toward_player(player)

        self.apply_gravity()
        self.move_and_collide()
        self.attack_player(player)
        self.resolve_overlap_with_player(player)
        self.anim_frame  += 1
        if self.flash_timer > 0:
            self.flash_timer -= 1

    def draw(self, surface):
        if not self.is_alive:
            return
        sr  = self.get_screen_rect()
        # Charger windup visual
        if self.enemy_type == 3 and self._charge_state == "windup":
            pulse = abs(math.sin(self._windup_timer * 0.15)) * 40
            wsurf = pygame.Surface((self.width + 20, self.height + 20), pygame.SRCALPHA)
            pygame.draw.rect(wsurf, (255, int(120 + pulse), 0, 100),
                             (0, 0, self.width + 20, self.height + 20), border_radius=4)
            surface.blit(wsurf, (sr.x - 10, sr.y - 10))

        ss = 1.0 if self.enemy_type != 5 else 1.5
        img = _build_enemy_surf(self.anim_frame, flash=self.flash_timer > 0,
                                 enemy_type=self.enemy_type, size_scale=ss)
        surface.blit(img, (sr.x - 4, sr.y - 4))

        # Health bar
        bar_w = self.width
        bar_h = 5 if self.enemy_type == 5 else 4
        bx, by = sr.x, sr.y - 10
        ratio  = self.health / self.max_health
        pygame.draw.rect(surface, (40, 10, 10), (bx, by, bar_w, bar_h))
        col = {0: (220, 60, 60), 1: (180, 60, 220), 2: (40, 200, 180),
               3: (220, 120, 30), 4: (60, 80, 220), 5: (220, 30, 30)}.get(self.enemy_type, (200, 60, 60))
        pygame.draw.rect(surface, col, (bx, by, int(bar_w * ratio), bar_h))
        pygame.draw.rect(surface, (180, 180, 180), (bx, by, bar_w, bar_h), 1)

        # Boss label
        if self.enemy_type == 5:
            bs = FONT_SM.render("BOSS", True, (255, 60, 60))
            surface.blit(bs, (sr.centerx - bs.get_width() // 2, sr.y - 22))

    def take_damage(self, amount, knockback_direction=1):
        self.health      = max(0, self.health - amount)
        self.velocity_x  = knockback_direction * (6 if self.enemy_type == 5 else 10)
        self.velocity_y  = -5 if self.enemy_type == 5 else -7
        self.flash_timer = 6
        if self.health == 0:
            self.is_alive = False


# ── Platform drawing ──────────────────────────────────────────────────────────
def draw_platforms(surface):
    cam_y_top    = camera_offset_y - 100
    cam_y_bottom = camera_offset_y + HEIGHT + 100
    t = pygame.time.get_ticks()
    for data in PLATFORMS_DATA:
        plat, ptype, extra = data
        if ptype == "nest":
            continue
        if ptype == "falling" and extra.get("fallen"):
            continue
        if plat.y < cam_y_top or plat.y > cam_y_bottom:
            continue
        sr = pygame.Rect(plat.x - camera_offset_x + shake_x,
                         plat.y - camera_offset_y + shake_y,
                         plat.width, plat.height)

        if ptype == "spike":
            pygame.draw.rect(surface, (110, 40, 40), sr, border_radius=2)
            pygame.draw.rect(surface, (200, 60, 60), pygame.Rect(sr.x + 2, sr.y, sr.width - 4, 3))
            # Draw spike teeth on top
            for sx in range(sr.x + 2, sr.x + sr.width - 2, 6):
                pygame.draw.polygon(surface, (220, 80, 80),
                    [(sx, sr.y), (sx + 3, sr.y - 6), (sx + 6, sr.y)])
        elif ptype == "bounce":
            pulse = int(40 + 30 * math.sin(t * 0.004))
            pygame.draw.rect(surface, (30, int(150 + pulse), 80), sr, border_radius=3)
            pygame.draw.rect(surface, (60, 255, 140), pygame.Rect(sr.x + 2, sr.y, sr.width - 4, 4))
            bs = FONT_SM.render("↑", True, (60, 255, 140))
            surface.blit(bs, (sr.centerx - 4, sr.y - 12))
        elif ptype == "moving":
            pygame.draw.rect(surface, (60, 100, 170), sr, border_radius=3)
            pygame.draw.rect(surface, (120, 180, 255), pygame.Rect(sr.x + 2, sr.y, sr.width - 4, 4))
        elif ptype == "falling":
            shake_amount = 0
            if extra.get("shake_timer", 0) > 0:
                shake_amount = random.randint(-2, 2)
            tint = int(extra.get("shake_timer", 0) / 60 * 180)
            pygame.draw.rect(surface, (int(85 + tint), 95 - tint // 2, 130 - tint),
                             sr.move(shake_amount, 0), border_radius=3)
            pygame.draw.rect(surface, (130, 148, 185),
                             pygame.Rect(sr.x + 2 + shake_amount, sr.y, sr.width - 4, 4))
        else:  # normal
            pygame.draw.rect(surface, (85, 95, 130), sr, border_radius=3)
            pygame.draw.rect(surface, (130, 148, 185),
                             pygame.Rect(sr.x + 2, sr.y, sr.width - 4, 4))


# ── Enemy spawning ────────────────────────────────────────────────────────────
def spawn_wave(raid_number, player_y=0, player=None):
    rng      = random.Random(raid_number * 17)
    enemies  = []

    # Determine if this is a boss raid
    is_boss_raid = (raid_number % 5 == 0)

    if is_boss_raid:
        # Boss raid: 1 boss + some minions
        cx = rng.randint(100, 700)
        cy = player_y - rng.randint(50, 200) if player_y != 0 else FLOOR_Y - 100
        enemies.append(Enemy(cx, cy, enemy_type=5))
        n_minions = 3 + raid_number // 3
        for _ in range(n_minions):
            x = rng.randint(-400, 1200)
            y = player_y - rng.randint(0, 300) if player_y else FLOOR_Y - 40
            enemies.append(Enemy(x, y, enemy_type=rng.choice([0, 1])))
        return enemies

    # Progressive enemy unlocks
    available_types = [0]  # always have basic
    if raid_number >= 2:  available_types.append(1)  # elites
    if raid_number >= 3:  available_types.append(2)  # jumpers
    if raid_number >= 4:  available_types.append(3)  # chargers
    if raid_number >= 6:  available_types.append(4)  # flying

    n_base = 4 + raid_number * 2
    # Scale enemy count more interestingly at higher raids
    if raid_number >= 5:
        n_base = int(n_base * 0.85)  # cap growth, but add specials

    for i in range(n_base):
        x = rng.randint(-500, 1300)
        y_off = rng.randint(-CHUNK_HEIGHT * 2, CHUNK_HEIGHT)
        y = max(player_y - 100, FLOOR_Y - 40 + y_off) if player_y else FLOOR_Y - 40
        # Weight toward more dangerous types at higher raids
        weights = [max(1, 6 - raid_number)] + [2] * (len(available_types) - 1)
        total_w = sum(weights)
        r_val   = rng.random() * total_w
        cumul   = 0
        chosen  = available_types[0]
        for t, w in zip(available_types, weights):
            cumul += w
            if r_val <= cumul:
                chosen = t
                break
        enemies.append(Enemy(x, y, enemy_type=chosen))

    return enemies


# ── Level-up screen ───────────────────────────────────────────────────────────
UPGRADE_OPTIONS = [
    ("❤ +1 Heart",         "heart"),
    ("⚡ Dash Cooldown -20%", "dash_cd"),
    ("↑ Higher Jump",      "jump_vel"),
    ("⚡ Faster Movement", "max_speed"),
    ("☠ Stomp Damage +25%","stomp_dmg"),
    ("↑↑ Double Jump",     "double_jump"),
]

def levelup_screen(player):
    """Show 3 random upgrade choices. Returns chosen upgrade key."""
    bg = SCREEN.copy()
    # Pick 3 distinct options
    choices = random.sample(UPGRADE_OPTIONS, 3)
    btns = [pygame.Rect(WIDTH // 2 - 180, HEIGHT // 2 - 60 + i * 80, 360, 60)
            for i in range(3)]
    glow = 0

    while True:
        glow = (glow + 2) % 360
        mp = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for i, btn in enumerate(btns):
                    if btn.collidepoint(mp):
                        return choices[i][1]

        # Dim background
        SCREEN.blit(bg, (0, 0))
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        SCREEN.blit(ov, (0, 0))

        # Title
        pulse = int(200 + 40 * math.sin(glow * 0.05))
        t = TITLE_FONT.render("LEVEL UP!", True, (80, pulse, 255))
        tg = TITLE_FONT.render("LEVEL UP!", True, (20, 40, 100))
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            SCREEN.blit(tg, (WIDTH // 2 - t.get_width() // 2 + dx, HEIGHT // 2 - 160 + dy))
        SCREEN.blit(t, (WIDTH // 2 - t.get_width() // 2, HEIGHT // 2 - 160))

        sub = FONT.render("Choose an upgrade:", True, (180, 180, 220))
        SCREEN.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 - 100))

        for i, (btn, (label, key)) in enumerate(zip(btns, choices)):
            hovered = btn.collidepoint(mp)
            col = (80, 140, 255) if hovered else (40, 70, 140)
            col2 = (120, 180, 255) if hovered else (60, 100, 200)
            # Already unlocked double jump?
            if key == "double_jump" and player.upgrades.get("double_jump"):
                col = (60, 60, 80)
                col2 = (80, 80, 100)
                label = "↑↑ Double Jump (owned)"

            pygame.draw.rect(SCREEN, (0, 0, 0, 80), btn.move(3, 3), border_radius=8)
            pygame.draw.rect(SCREEN, col, btn, border_radius=8)
            pygame.draw.rect(SCREEN, col2, btn, 2, border_radius=8)
            ts = FONT_LG.render(label, True, (230, 235, 255))
            SCREEN.blit(ts, (btn.centerx - ts.get_width() // 2,
                              btn.centery - ts.get_height() // 2))

        pygame.display.flip()
        CLOCK.tick(60)


def apply_upgrade(player, key):
    if key == "heart":
        player.max_hearts = min(20, player.max_hearts + 1)
        player.hearts     = min(player.max_hearts, player.hearts + 1)
    elif key == "dash_cd":
        player.upgrades["dash_cd"] = max(40, int(player.upgrades["dash_cd"] * 0.8))
    elif key == "jump_vel":
        player.upgrades["jump_vel"] = player.upgrades["jump_vel"] * 1.12  # more negative = higher
    elif key == "max_speed":
        player.upgrades["max_speed"] = min(16, player.upgrades["max_speed"] + 1.5)
    elif key == "stomp_dmg":
        player.upgrades["stomp_dmg"] = int(player.upgrades["stomp_dmg"] * 1.25)
    elif key == "double_jump":
        player.upgrades["double_jump"] = True


# ── Python quiz (level-up gate) ───────────────────────────────────────────────
# Each level-up, the player must debug a Python snippet before claiming an
# upgrade. Questions are ordered easiest → hardest. Each entry has the buggy
# code, the symptom the "player" reported, and answer options (one correct).
QUIZ_QUESTIONS = [
    {
        "code": ['print(“hello world)'],
        "symptom": "\"Why won't my hello world print?\"",
        "options": [
            ('The closing quote is missing — write print("hello world")', True),
            ("print can only show numbers, not text", False),
            ("hello and world must be split with a comma", False),
        ],
    },
    {
        "code": ['Name = adaptation',
                 'Print(name?)'],
        "symptom": "\"Why isn't the name appearing?\"",
        "options": [
            ('Use lowercase print, match the name (Name), and quote "adaptation"', True),
            ("You can't name a variable Name", False),
            ("Just delete the ?, and it will work", False),
        ],
    },
    {
        "code": ['x  =  5',
                 'if x  >  3',
                 '        print(“big\')'],
        "symptom": "\"Why doesn't it print 'big'?\"",
        "options": [
            ('The if line needs a colon ":" and the quotes must match', True),
            ("5 is not actually bigger than 3", False),
            ("print isn't allowed inside an if", False),
        ],
    },
    {
        "code": ['class Player:',
                 '    def init[self, name]',
                 '        self.name = name',
                 '        self.hp = 100'],
        "symptom": "\"Is something wrong here?\"",
        "options": [
            ('Use def __init__(self, name): — dunder, parentheses and a colon', True),
            ("hp should be renamed to health", False),
            ("A class can't store name and hp together", False),
        ],
    },
    {
        "code": ['def take_damage(self, amount):',
                 '    if amount < self.hp',
                 '        self.hp -= amount',
                 '        print[f"{self.name} has {self.hp}HP left!"]'],
        "symptom": "\"Wait, I didn't even know I was healing!\"",
        "options": [
            ('The if needs a colon ":" and print uses parentheses (), not []', True),
            ("Use += instead of -= to take damage", False),
            ("f-strings can't go inside print", False),
        ],
    },
    {
        "code": ['def take_damage(self, amount):',
                 '    self.health.take_damage(amount)',
                 '',
                 'def heal(self =  amount):',
                 '    self.health.heal[amount]'],
        "symptom": "\"Healing isn't working — I'm dead!\"",
        "options": [
            ('Write def heal(self, amount): with a comma, and call heal(amount)', True),
            ("heal must return self.health", False),
            ("A class can't have two methods that both print", False),
        ],
    },
    {
        "code": ['from dataclasses import dataclass, field',
                 '',
                 '@dataclass',
                 'class Inventory:',
                 '    items: list[sting] - field(default_factory=list)'],
        "symptom": "\"My inventory is all over the place!\"",
        "options": [
            ('It should be list[str] = field(...): fix "sting"→"str" and "-"→"="', True),
            ("field must be imported from typing", False),
            ("Lists can't be dataclass fields", False),
        ],
    },
]


def _wrap_text(text, font, max_w):
    """Break text into lines that fit within max_w pixels."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if font.size(trial)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def quiz_screen(player):
    """Debug-the-Python gate shown on level-up. Player must pick the correct
    fix before the upgrade screen opens. Returns "quit" if the window closes."""
    bg = SCREEN.copy()
    q = QUIZ_QUESTIONS[player.quiz_index % len(QUIZ_QUESTIONS)]
    player.quiz_index += 1

    # Shuffle option order so the answer isn't always first.
    opts = q["options"][:]
    random.shuffle(opts)

    btn_w = 560
    btns = [pygame.Rect(WIDTH // 2 - btn_w // 2, 360 + i * 70, btn_w, 60)
            for i in range(len(opts))]

    feedback   = ""        # "" | "wrong" | "right"
    feedback_t = 0
    glow = 0

    while True:
        glow = (glow + 2) % 360
        mp = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return "quit"
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and feedback != "right":
                for i, btn in enumerate(btns):
                    if btn.collidepoint(mp):
                        if opts[i][1]:
                            feedback   = "right"
                            feedback_t = 35
                            play_sound('levelup')
                        else:
                            feedback   = "wrong"
                            feedback_t = 45
                            play_sound('hit')

        if feedback == "right":
            feedback_t -= 1
            if feedback_t <= 0:
                return "ok"
        elif feedback_t > 0:
            feedback_t -= 1

        # ── draw ──
        SCREEN.blit(bg, (0, 0))
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 190))
        SCREEN.blit(ov, (0, 0))

        pulse = int(200 + 40 * math.sin(glow * 0.05))
        title = FONT_LG.render("DEBUG TO LEVEL UP!", True, (80, pulse, 255))
        SCREEN.blit(title, (WIDTH // 2 - title.get_width() // 2, 36))
        sub = FONT_SM.render("Pick the fix to claim your upgrade", True, (170, 180, 220))
        SCREEN.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 72))

        # Bug report
        rep = FONT.render(q["symptom"], True, (255, 170, 90))
        SCREEN.blit(rep, (WIDTH // 2 - rep.get_width() // 2, 98))

        # Code panel
        code = q["code"]
        line_h = 22
        panel = pygame.Rect(WIDTH // 2 - 300, 130, 600, 24 + len(code) * line_h)
        pygame.draw.rect(SCREEN, (18, 22, 34), panel, border_radius=6)
        pygame.draw.rect(SCREEN, (70, 90, 140), panel, 2, border_radius=6)
        for li, line in enumerate(code):
            ls = PIXEL_FONT.render(line, True, (150, 230, 170))
            SCREEN.blit(ls, (panel.x + 16, panel.y + 12 + li * line_h))

        # Options
        for i, (btn, (label, _correct)) in enumerate(zip(btns, opts)):
            hovered = btn.collidepoint(mp) and feedback != "right"
            col  = (80, 140, 255) if hovered else (40, 70, 140)
            col2 = (120, 180, 255) if hovered else (60, 100, 200)
            pygame.draw.rect(SCREEN, col, btn, border_radius=8)
            pygame.draw.rect(SCREEN, col2, btn, 2, border_radius=8)
            wrapped = _wrap_text(label, FONT_SM, btn_w - 24)
            ty = btn.centery - (len(wrapped) * 16) // 2
            for wl in wrapped:
                ws = FONT_SM.render(wl, True, (230, 235, 255))
                SCREEN.blit(ws, (btn.centerx - ws.get_width() // 2, ty))
                ty += 16

        # Feedback line
        if feedback == "wrong" and feedback_t > 0:
            fb = FONT.render("Not quite — try again!", True, (255, 90, 90))
            SCREEN.blit(fb, (WIDTH // 2 - fb.get_width() // 2, HEIGHT - 56))
        elif feedback == "right":
            fb = FONT.render("Correct! Level up!", True, (90, 255, 120))
            SCREEN.blit(fb, (WIDTH // 2 - fb.get_width() // 2, HEIGHT - 56))

        pygame.display.flip()
        CLOCK.tick(60)


# ── Shop screen (between raids) ───────────────────────────────────────────────
SHOP_ITEMS = [
    ("❤ +1 Heart",          "heart",       30),
    ("⚡ Dash CD -20%",      "dash_cd",     40),
    ("↑↑ Double Jump",       "double_jump", 60),
    ("↑ Higher Jump",        "jump_vel",    35),
    ("⚡ Faster Movement",   "max_speed",   35),
]

def shop_screen(player, coins):
    """Between-raid shop. Returns remaining coins."""
    bg = SCREEN.copy()
    btns = [pygame.Rect(WIDTH // 2 - 220, 140 + i * 72, 440, 60) for i in range(len(SHOP_ITEMS))]
    close_btn = pygame.Rect(WIDTH // 2 - 100, HEIGHT - 80, 200, 50)

    while True:
        mp = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return coins
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return coins
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if close_btn.collidepoint(mp):
                    return coins
                for i, btn in enumerate(btns):
                    if btn.collidepoint(mp):
                        label, key, cost = SHOP_ITEMS[i]
                        if coins >= cost:
                            coins -= cost
                            apply_upgrade(player, key)
                            play_sound('shop')

        SCREEN.blit(bg, (0, 0))
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        SCREEN.blit(ov, (0, 0))

        ts = TITLE_FONT.render("SHOP", True, (255, 220, 40))
        SCREEN.blit(ts, (WIDTH // 2 - ts.get_width() // 2, 40))
        cs = FONT_LG.render(f"Coins: {coins}", True, (255, 220, 40))
        SCREEN.blit(cs, (WIDTH // 2 - cs.get_width() // 2, 95))

        for i, (btn, (label, key, cost)) in enumerate(zip(btns, SHOP_ITEMS)):
            hovered = btn.collidepoint(mp)
            can_buy = coins >= cost
            if key == "double_jump" and player.upgrades.get("double_jump"):
                col, col2 = (50, 50, 70), (70, 70, 90)
                label_draw = label + " (owned)"
            else:
                col  = (80, 140, 60) if (hovered and can_buy) else (50, 80, 40) if can_buy else (60, 40, 40)
                col2 = (120, 200, 80) if can_buy else (80, 50, 50)
                label_draw = label

            pygame.draw.rect(SCREEN, (0, 0, 0, 80), btn.move(3, 3), border_radius=8)
            pygame.draw.rect(SCREEN, col, btn, border_radius=8)
            pygame.draw.rect(SCREEN, col2, btn, 2, border_radius=8)

            ls = FONT_LG.render(label_draw, True, (220, 230, 200))
            SCREEN.blit(ls, (btn.x + 16, btn.centery - ls.get_height() // 2))
            ps = FONT_LG.render(f"⬡{cost}", True, (255, 220, 40) if can_buy else (120, 100, 40))
            SCREEN.blit(ps, (btn.right - ps.get_width() - 16, btn.centery - ps.get_height() // 2))

        draw_button(SCREEN, "Close Shop", close_btn, close_btn.collidepoint(mp),
                    (160, 120, 40), (100, 70, 20))
        pygame.display.flip()
        CLOCK.tick(60)


# ── Objectives system ─────────────────────────────────────────────────────────
class Objectives:
    def __init__(self):
        self.list = [
            {"text": "Survive 3 raids",      "key": "raids",    "target": 3,   "done": False},
            {"text": "Kill 20 enemies",       "key": "kills",    "target": 20,  "done": False},
            {"text": "Reach Alt 600",         "key": "altitude", "target": 600, "done": False},
            {"text": "Collect 5 XP orbs",    "key": "xp_orbs",  "target": 5,   "done": False},
            {"text": "Earn 50 XP",            "key": "total_xp", "target": 50,  "done": False},
        ]
        self.progress = {o["key"]: 0 for o in self.list}

    def update(self, key, value):
        self.progress[key] = value
        for obj in self.list:
            if obj["key"] == key and not obj["done"]:
                if self.progress[key] >= obj["target"]:
                    obj["done"] = True

    def get_hud_items(self):
        active = [o for o in self.list if not o["done"]][:3]
        return [(f"{o['text']} ({self.progress[o['key']]}/{o['target']})", o["done"])
                for o in active] + \
               [(o["text"], True) for o in self.list if o["done"]][-2:]


# ── Buttons ───────────────────────────────────────────────────────────────────
def draw_button(surface, text, rect, hovered, color_on=(160, 220, 110), color_off=(100, 170, 60)):
    color = color_on if hovered else color_off
    pygame.draw.rect(surface, (0, 0, 0, 80), rect.move(3, 3), border_radius=6)
    pygame.draw.rect(surface, color, rect, border_radius=6)
    pygame.draw.rect(surface, (255, 255, 255), rect, 2, border_radius=6)
    ts = FONT.render(text, True, (15, 15, 15))
    surface.blit(ts, (rect.centerx - ts.get_width() // 2,
                      rect.centery - ts.get_height() // 2))


# ── Title Screen ──────────────────────────────────────────────────────────────
def title_screen():
    play_btn     = pygame.Rect(WIDTH // 2 - 110, HEIGHT // 2 - 10, 220, 52)
    tutorial_btn = pygame.Rect(WIDTH // 2 - 110, HEIGHT // 2 + 56, 220, 52)
    exit_btn     = pygame.Rect(WIDTH // 2 - 110, HEIGHT // 2 + 122, 220, 52)
    stars = [(random.randint(0, WIDTH), random.randint(0, HEIGHT),
              random.uniform(0.5, 2.5)) for _ in range(120)]
    t = 0
    while True:
        mp = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return "quit"
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if play_btn.collidepoint(mp):     return "play"
                if tutorial_btn.collidepoint(mp): return "tutorial"
                if exit_btn.collidepoint(mp):     return "quit"
        t += 1
        SCREEN.fill((12, 14, 32))
        for sx, sy, sz in stars:
            bri = int(100 + 80 * math.sin(t * 0.03 + sx * 0.1))
            pygame.draw.circle(SCREEN, (bri, bri, min(255, bri + 40)),
                               (int(sx), int(sy + math.sin(t * 0.01 + sx) * 0.5)), int(sz))
        title_surf = TITLE_FONT.render("ADAPTATION", True, (255, 255, 255))
        glow_surf  = TITLE_FONT.render("ADAPTATION", True, (60, 120, 255))
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2),(-1,-1),(1,-1),(-1,1),(1,1)]:
            SCREEN.blit(glow_surf, (WIDTH // 2 - title_surf.get_width() // 2 + dx,
                                    HEIGHT // 2 - 140 + dy))
        SCREEN.blit(title_surf, (WIDTH // 2 - title_surf.get_width() // 2, HEIGHT // 2 - 140))
        sub = FONT.render("A pixel cube survival adventure", True, (140, 160, 210))
        SCREEN.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 - 82))
        preview_img = _build_player_surf(1, False, t, "run")
        SCREEN.blit(preview_img, (WIDTH // 2 - 20, HEIGHT // 2 - 55))
        draw_button(SCREEN, "▶  Play",     play_btn,     play_btn.collidepoint(mp),
                    (100, 210, 80), (60, 150, 40))
        draw_button(SCREEN, "?  Tutorial", tutorial_btn, tutorial_btn.collidepoint(mp),
                    (80, 160, 220), (40, 100, 170))
        draw_button(SCREEN, "✕  Exit",     exit_btn,     exit_btn.collidepoint(mp),
                    (210, 80, 80), (150, 40, 40))
        pygame.display.flip()
        CLOCK.tick(60)


# ── Tutorial Screen ───────────────────────────────────────────────────────────
def tutorial_screen():
    back_btn = pygame.Rect(WIDTH // 2 - 100, HEIGHT - 80, 200, 46)
    lines = [
        ("MOVEMENT",   (180, 220, 255)),
        ("A / D          Move left / right", (200, 200, 200)),
        ("W              Jump  (coyote time supported)", (200, 200, 200)),
        ("W (air)         Double jump (if unlocked)", (200, 200, 200)),
        ("S (air)         Fast-fall", (200, 200, 200)),
        ("Shift           Dash  (upgradeable cooldown)", (200, 200, 200)),
        ("",           (0,0,0)),
        ("COMBAT",     (255, 200, 100)),
        ("Land on an enemy to stomp it!", (200, 200, 200)),
        ("Critical stomps (rare) do double damage + big shake.", (200, 200, 200)),
        ("Build COMBOS for bonus score.", (200, 200, 200)),
        ("",           (0,0,0)),
        ("ENEMIES",    (255, 140, 80)),
        ("Jumper: leaps toward you.  Charger: winds up then dashes.", (200, 200, 200)),
        ("Flying: ignores platforms.  Boss: every 5th raid!", (200, 200, 200)),
        ("",           (0,0,0)),
        ("PROGRESSION",(120, 255, 160)),
        ("Level up -> choose an upgrade.  Shop opens after each raid.", (200, 200, 200)),
        ("Collect XP orbs, coins, and health pickups from enemies.", (200, 200, 200)),
        ("",           (0,0,0)),
        ("WORLD",      (180, 160, 255)),
        ("Easy / Medium / Hard zones as you climb higher.", (200, 200, 200)),
        ("Spike, bounce, moving, and falling platforms await!", (200, 200, 200)),
    ]
    while True:
        mp = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return "quit"
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return "title"
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if back_btn.collidepoint(mp):
                    return "title"
        SCREEN.fill((14, 16, 34))
        t_surf = FONT_LG.render("HOW TO PLAY", True, (255, 255, 255))
        SCREEN.blit(t_surf, (WIDTH // 2 - t_surf.get_width() // 2, 18))
        pygame.draw.line(SCREEN, (80, 100, 180), (60, 52), (WIDTH - 60, 52), 1)
        y = 64
        for text, color in lines:
            if text == "":
                y += 6
                continue
            is_header = color != (200, 200, 200)
            fnt = FONT_LG if is_header else FONT_SM
            surf = fnt.render(text, True, color)
            SCREEN.blit(surf, (60 if not is_header else WIDTH // 2 - surf.get_width() // 2, y))
            y += 24 if is_header else 18
        draw_button(SCREEN, "← Back", back_btn, back_btn.collidepoint(mp),
                    (80, 160, 220), (40, 100, 170))
        pygame.display.flip()
        CLOCK.tick(60)


# ── Death Screen ──────────────────────────────────────────────────────────────
def death_screen(raid_number, kills, coins, max_combo):
    title_btn = pygame.Rect(WIDTH // 2 - 120, HEIGHT // 2 + 110, 240, 52)
    snapshot = SCREEN.copy()
    shake_frames = 40
    for i in range(shake_frames):
        t  = 1 - i / shake_frames
        sx = random.randint(-int(14 * t), int(14 * t))
        sy = random.randint(-int(14 * t), int(14 * t))
        SCREEN.fill((5, 5, 15))
        SCREEN.blit(snapshot, (sx, sy))
        pygame.display.flip()
        CLOCK.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: return "quit"
    fade_surf = pygame.Surface((WIDTH, HEIGHT))
    fade_surf.fill((0, 0, 0))
    for alpha in range(0, 256, 4):
        SCREEN.blit(snapshot, (0, 0))
        fade_surf.set_alpha(alpha)
        SCREEN.blit(fade_surf, (0, 0))
        pygame.display.flip()
        CLOCK.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: return "quit"
    while True:
        mp = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return "quit"
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if title_btn.collidepoint(mp):
                    return "title"
        SCREEN.fill((8, 5, 18))
        for r_size in range(300, 0, -30):
            alpha = max(0, 60 - r_size // 6)
            vsurf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.ellipse(vsurf, (180, 10, 10, alpha),
                                (WIDTH//2 - r_size, HEIGHT//2 - r_size, r_size*2, r_size*2), 20)
            SCREEN.blit(vsurf, (0, 0))
        t1 = TITLE_FONT.render("YOU DIED", True, (220, 40, 40))
        tg = TITLE_FONT.render("YOU DIED", True, (100, 10, 10))
        for dx, dy in [(-3,0),(3,0),(0,-3),(0,3)]:
            SCREEN.blit(tg, (WIDTH//2 - t1.get_width()//2 + dx, HEIGHT//2 - 130 + dy))
        SCREEN.blit(t1, (WIDTH//2 - t1.get_width()//2, HEIGHT//2 - 130))
        stats = [
            f"Raids Survived:  {raid_number - 1}",
            f"Enemies Killed:  {kills}",
            f"Coins Collected: {coins}",
            f"Max Combo:       x{max_combo}",
        ]
        for i, line in enumerate(stats):
            s = FONT_LG.render(line, True, (180, 140, 140))
            SCREEN.blit(s, (WIDTH//2 - s.get_width()//2, HEIGHT//2 - 40 + i * 36))
        draw_button(SCREEN, "↩  Back to Title", title_btn, title_btn.collidepoint(mp),
                    (180, 80, 80), (120, 40, 40))
        pygame.display.flip()
        CLOCK.tick(60)


# ── Pause Menu ────────────────────────────────────────────────────────────────
def pause_menu():
    bg = SCREEN.copy()
    resume_btn = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 - 30, 200, 50)
    exit_btn   = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 40, 200, 50)
    while True:
        mp = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:                                  return "quit"
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE: return "resume"
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if resume_btn.collidepoint(mp): return "resume"
                if exit_btn.collidepoint(mp):   return "quit"
        SCREEN.blit(bg, (0, 0))
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 130))
        SCREEN.blit(ov, (0, 0))
        t = TITLE_FONT.render("PAUSED", True, (255, 255, 255))
        SCREEN.blit(t, (WIDTH // 2 - t.get_width() // 2, HEIGHT // 2 - 120))
        draw_button(SCREEN, "Resume", resume_btn, resume_btn.collidepoint(mp))
        draw_button(SCREEN, "Exit",   exit_btn,   exit_btn.collidepoint(mp),
                    (210, 80, 80), (150, 40, 40))
        pygame.display.flip()
        CLOCK.tick(60)


# ── Raid Banner ───────────────────────────────────────────────────────────────
raid_banner_timer = 0
raid_banner_text  = ""

def show_raid_banner(text):
    global raid_banner_timer, raid_banner_text
    raid_banner_text  = text
    raid_banner_timer = 180

def draw_raid_banner(surface):
    global raid_banner_timer
    if raid_banner_timer <= 0:
        return
    raid_banner_timer -= 1
    alpha = min(255, raid_banner_timer * 4, (180 - raid_banner_timer + 1) * 4)
    alpha = max(0, alpha)
    bs = TITLE_FONT.render(raid_banner_text, True, (255, 200, 60))
    bx = WIDTH // 2 - bs.get_width() // 2
    by = HEIGHT // 3
    shadow = TITLE_FONT.render(raid_banner_text, True, (100, 60, 0))
    tmp = pygame.Surface((bs.get_width(), bs.get_height()), pygame.SRCALPHA)
    tmp.blit(shadow, (2, 2))
    tmp.blit(bs, (0, 0))
    tmp.set_alpha(alpha)
    surface.blit(tmp, (bx, by))


# ── Floating text popups ──────────────────────────────────────────────────────
class FloatingText:
    def __init__(self, x, y, text, color=(255, 255, 100), size=18):
        self.world_x = x
        self.world_y = y
        self.text    = text
        self.color   = color
        self.age     = 0
        self.lifetime = 50
        self.font    = pygame.font.SysFont("arial", size, bold=True)

    def update(self):
        self.world_y -= 1.2
        self.age     += 1

    def is_alive(self):
        return self.age < self.lifetime

    def draw(self, surface):
        alpha = max(0, int(255 * (1 - self.age / self.lifetime)))
        ts = self.font.render(self.text, True, self.color)
        ts.set_alpha(alpha)
        sx = int(self.world_x - camera_offset_x + shake_x)
        sy = int(self.world_y - camera_offset_y + shake_y)
        surface.blit(ts, (sx - ts.get_width() // 2, sy))


# ── Main Game Loop ────────────────────────────────────────────────────────────
def main():
    global camera_offset_x, camera_offset_y

    state = "title"

    while True:
        if state == "title":
            result = title_screen()
            if result == "quit":
                break
            elif result == "tutorial":
                state = "tutorial"
            elif result == "play":
                state = "game"

        elif state == "tutorial":
            result = tutorial_screen()
            if result == "quit":
                break
            else:
                state = "title"

        elif state == "game":
            # Reset global world state
            random.seed(42)
            PLATFORMS.clear()
            PLATFORMS_DATA.clear()
            moving_platforms.clear()
            generated_chunks.clear()
            for r in _static_plats:
                PLATFORMS_DATA.append([r, "normal", {}])
                PLATFORMS.append(r)

            parallax_layers = build_parallax_layers()
            player      = Player(100, HEIGHT - 100)
            raid_number = 1
            total_kills = 0
            total_coins = 0
            total_xp_orbs_collected = 0
            combo       = 0
            combo_timer = 0
            max_combo   = 0
            collectibles = []
            floating_texts = []
            objectives  = Objectives()
            enemies     = spawn_wave(raid_number, player.world_y, player)
            show_raid_banner(f"RAID  {raid_number}")
            play_sound('raid')

            running = True
            world_particles = []

            while running:
                events = pygame.event.get()
                for ev in events:
                    if ev.type == pygame.QUIT:
                        state = "quit"
                        running = False
                    if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                        result = pause_menu()
                        if result == "quit":
                            state = "quit"
                            running = False

                if not running:
                    break

                # ── update ──
                player.update(events)
                update_shake()

                # Level-up screen trigger
                if player.pending_levelup:
                    player.pending_levelup = False
                    # Must debug a Python question before claiming the upgrade
                    if quiz_screen(player) == "quit":
                        state = "quit"
                        running = False
                        break
                    key = levelup_screen(player)
                    if key:
                        apply_upgrade(player, key)

                # Combo timer decay
                combo_timer -= 1
                if combo_timer <= 0:
                    combo = 0

                # Stomp detection
                for enemy in enemies:
                    if player.is_squashing_enemy(enemy) and enemy.is_alive:
                        cx = enemy.world_x + enemy.width  // 2
                        cy = enemy.world_y + enemy.height // 2

                        # Critical check (15% chance)
                        is_crit = random.random() < 0.15
                        dmg = player.upgrades["stomp_dmg"]
                        if is_crit:
                            dmg *= 2

                        col = {0: (220, 80, 80), 1: (180, 60, 220), 2: (40, 200, 180),
                               3: (220, 120, 30), 4: (60, 80, 220), 5: (255, 40, 40)}.get(
                            enemy.enemy_type, (220, 80, 80))

                        n_parts = 35 if is_crit else 20
                        sz      = 8  if is_crit else 5
                        world_particles += burst(cx, cy, col, n=n_parts, speed=7 if is_crit else 5,
                                                 lifetime=30 if is_crit else 22, size=sz)

                        enemy.take_damage(dmg, player.facing)
                        player.velocity_y = -9

                        # Hit freeze
                        player.hit_freeze = 6 if is_crit else 3

                        if is_crit:
                            trigger_shake(10, 20)
                            floating_texts.append(FloatingText(cx, cy - 20, "CRITICAL!", (255, 200, 50), 22))
                            play_sound('crit')
                        else:
                            trigger_shake(4, 10)
                            play_sound('stomp')

                        if not enemy.is_alive:
                            xp_gained = XP_PER_KILL * (3 if enemy.enemy_type == 5 else
                                                        2 if enemy.enemy_type == 1 else 1)
                            player.gain_xp(xp_gained)
                            total_kills += 1
                            play_sound('hit')

                            # Combo
                            combo += 1
                            combo_timer = 90
                            max_combo = max(max_combo, combo)
                            if combo >= 3:
                                bonus = combo * 5
                                floating_texts.append(FloatingText(cx, cy - 40,
                                    f"COMBO x{combo}! +{bonus}XP", (255, 160, 30), 16))
                                player.gain_xp(bonus)

                            # Loot drops
                            loot_rolls = []
                            if enemy.enemy_type == 5:   # Boss drops lots
                                loot_rolls = ["coin"]*4 + ["xp"]*4 + ["health"]
                            elif enemy.enemy_type == 1: # Elite
                                loot_rolls = ["coin"]*2 + ["xp"]*2
                            else:
                                if random.random() < 0.5:
                                    loot_rolls.append(random.choice(["xp", "coin"]))
                                if random.random() < 0.08:
                                    loot_rolls.append("health")

                            for ltype in loot_rolls:
                                collectibles.append(Collectible(
                                    cx + random.randint(-20, 20),
                                    cy, ltype))

                    enemy.update(player)

                # Collectible pickup
                for c in collectibles:
                    c.update()
                    if not c.collected and c.get_rect().colliderect(player.get_rect()):
                        c.collected = True
                        if c.ctype == "xp":
                            player.gain_xp(XP_PER_ORB)
                            total_xp_orbs_collected += 1
                            floating_texts.append(FloatingText(
                                c.world_x, c.world_y - 10, f"+{XP_PER_ORB} XP", (80, 255, 120)))
                        elif c.ctype == "coin":
                            total_coins += 1
                            play_sound('coin')
                            floating_texts.append(FloatingText(
                                c.world_x, c.world_y - 10, "+1 Coin", (255, 220, 40)))
                        else:  # health
                            player.hearts = min(player.max_hearts, player.hearts + 1)
                            floating_texts.append(FloatingText(
                                c.world_x, c.world_y - 10, "+1 ❤", (255, 80, 100)))
                collectibles = [c for c in collectibles if not c.collected]

                # Floating texts
                for ft in floating_texts:
                    ft.update()
                floating_texts = [ft for ft in floating_texts if ft.is_alive()]

                # World particles
                world_particles = [p for p in world_particles if p.is_alive()]
                for p in world_particles:
                    p.update()

                # Objectives update
                alt = altitude_above_floor(player.world_y)
                objectives.update("raids",    raid_number - 1)
                objectives.update("kills",    total_kills)
                objectives.update("altitude", int(alt))
                objectives.update("xp_orbs",  total_xp_orbs_collected)
                objectives.update("total_xp", player.xp + player.level * XP_PER_LEVEL)

                # Low-health shake
                if player.hearts <= LOW_HEALTH_THRESHOLD and player.hearts > 0:
                    if pygame.time.get_ticks() % 90 < 3:
                        trigger_shake(2, 6)

                # ── Check raid clear ──
                alive_enemies = [e for e in enemies if e.is_alive]
                if len(alive_enemies) == 0:
                    raid_number += 1
                    # Open shop every 2 raids
                    if raid_number % 2 == 0:
                        total_coins = shop_screen(player, total_coins)
                    enemies = spawn_wave(raid_number, player.world_y, player)
                    is_boss_raid = (raid_number % 5 == 0)
                    banner_txt = f"⚔ BOSS RAID {raid_number}!" if is_boss_raid else f"RAID  {raid_number}"
                    show_raid_banner(banner_txt)
                    trigger_shake(6, 25)
                    play_sound('raid')

                # ── Check death ──
                if player.hearts <= 0:
                    trigger_shake(14, 50)
                    for _ in range(50):
                        update_shake()
                        SCREEN.fill((20, 24, 38))
                        for layer in parallax_layers:
                            layer.draw(SCREEN, camera_offset_x - shake_x, camera_offset_y - shake_y)
                        floor_sr = pygame.Rect(shake_x, FLOOR_Y - camera_offset_y + shake_y,
                                               WIDTH * 4, FLOOR_HEIGHT)
                        pygame.draw.rect(SCREEN, (80, 88, 112), floor_sr)
                        draw_platforms(SCREEN)
                        player.draw(SCREEN)
                        for e in enemies:
                            e.draw(SCREEN)
                        draw_hud(SCREEN, player, combo, total_coins)
                        pygame.display.flip()
                        CLOCK.tick(60)
                        for ev in pygame.event.get():
                            pass

                    death_result = death_screen(raid_number, total_kills, total_coins, max_combo)
                    if death_result == "quit":
                        state = "quit"
                    else:
                        state = "title"
                    running = False
                    break

                # ── draw ──
                SCREEN.fill((20, 24, 38))
                for layer in parallax_layers:
                    layer.draw(SCREEN, camera_offset_x - shake_x, camera_offset_y - shake_y)

                floor_sy = FLOOR_Y - camera_offset_y + shake_y
                pygame.draw.rect(SCREEN, (80, 88, 112),
                                 (shake_x, floor_sy, WIDTH * 4, FLOOR_HEIGHT))
                pygame.draw.rect(SCREEN, (110, 120, 150),
                                 (shake_x, floor_sy, WIDTH * 4, 4))
                pygame.draw.rect(SCREEN, (45, 48, 62),
                                 (shake_x, floor_sy + FLOOR_HEIGHT, WIDTH * 4, HEIGHT))

                draw_platforms(SCREEN)

                for p in world_particles:
                    p.draw(SCREEN)

                for c in collectibles:
                    c.draw(SCREEN)

                player.draw(SCREEN)
                for enemy in enemies:
                    enemy.draw(SCREEN)

                for ft in floating_texts:
                    ft.draw(SCREEN)

                draw_hud(SCREEN, player, combo, total_coins, objectives.get_hud_items())

                rc = FONT_LG.render(f"RAID {raid_number}  |  {total_kills} kills", True, (200, 180, 100))
                SCREEN.blit(rc, (WIDTH - rc.get_width() - 14, 10))
                alive_txt = FONT_SM.render(f"Enemies: {len(alive_enemies)}", True, (180, 150, 100))
                SCREEN.blit(alive_txt, (WIDTH - alive_txt.get_width() - 14, 40))

                draw_raid_banner(SCREEN)

                pygame.display.flip()
                CLOCK.tick(60)

        elif state == "quit":
            break

    pygame.quit()


if __name__ == "__main__":
    main()