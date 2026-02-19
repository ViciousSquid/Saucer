
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import math
import random
import zipfile
import json
from io import BytesIO
import tkinter as tk
from tkinter import filedialog
from PIL import Image

# --- Vector & Math Helpers ---
class Vec3:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

    def copy(self): return Vec3(self.x, self.y, self.z)
    def add(self, v): return Vec3(self.x + v.x, self.y + v.y, self.z + v.z)
    def sub(self, v): return Vec3(self.x - v.x, self.y - v.y, self.z - v.z)
    def mul(self, scalar): return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)
    def mag(self): return math.sqrt(self.x**2 + self.y**2 + self.z**2)
    def normalize(self):
        m = self.mag()
        return Vec3(self.x/m, self.y/m, self.z/m) if m > 0 else Vec3(0,0,0)
    def dist(self, v): return self.sub(v).mag()

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_angle(current, target, t):
    diff = (target - current + 180) % 360 - 180
    return current + diff * t

# --- Enhanced Planet (supports editor data, textures, rings) ---
class Planet:
    def __init__(self, pos, data, heightmap_bytes=None):
        self.pos = pos
        self.data = data
        self.name = data.get('seed', 'Unknown')
        self.type = data.get('type', 'planet')
        self.radius = float(data.get('params', {}).get('radius', 100))
        self.orbitDistance = data.get('orbitDistance', 0)
        self.orbitSpeed = data.get('orbitSpeed', 0.2)
        self.orbitAngle = random.random() * math.pi * 2
        self.parent = None

        # Color fallback
        c = data.get('colors', {})
        ocean_hex = c.get('ocean', '#4488ff')
        self.color = (
            int(ocean_hex[1:3], 16) / 255,
            int(ocean_hex[3:5], 16) / 255,
            int(ocean_hex[5:7], 16) / 255
        )

        self.quadric = gluNewQuadric()
        self.texture_id = None
        if heightmap_bytes:
            self.load_texture(heightmap_bytes)

        # Rings
        params = data.get('params', {})
        self.hasRings = params.get('enableRings', False)
        self.ringDiameter = float(params.get('ringDiameter', 1.8))
        self.ringColorInner = params.get('ringColorInner', '#FFD700')
        self.ringColorOuter = params.get('ringColorOuter', '#DAA520')

    def load_texture(self, png_bytes):
        img = Image.open(BytesIO(png_bytes)).convert("RGBA")
        width, height = img.size
        data = img.tobytes("raw", "RGBA", 0, -1)

        self.texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)

    def draw(self):
        glPushMatrix()
        glTranslatef(self.pos.x, self.pos.y, self.pos.z)

        glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, [*self.color, 1.0])
        glMaterialfv(GL_FRONT, GL_SPECULAR, [0.3, 0.3, 0.3, 1.0])
        glMaterialf(GL_FRONT, GL_SHININESS, 30)

        if self.texture_id:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            gluQuadricTexture(self.quadric, GL_TRUE)
        else:
            gluQuadricTexture(self.quadric, GL_FALSE)

        gluSphere(self.quadric, self.radius, 48, 48)
        glDisable(GL_TEXTURE_2D)

        # Rings
        if self.hasRings:
            glPushMatrix()
            glRotatef(75, 1, 0, 0)
            glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, [0.9, 0.8, 0.6, 0.7])
            inner = self.radius * 1.2
            outer = self.radius * self.ringDiameter
            gluCylinder(self.quadric, inner, outer, 1.5, 64, 1)
            glPopMatrix()

        glPopMatrix()

    def update_orbit(self, dt, parent_pos):
        if self.orbitDistance > 0.1 and self.parent:
            self.orbitAngle += self.orbitSpeed * dt * 0.3
            self.pos.x = parent_pos.x + math.cos(self.orbitAngle) * self.orbitDistance
            self.pos.z = parent_pos.z + math.sin(self.orbitAngle) * self.orbitDistance

# --- Solar System Container ---
class SolarSystem:
    def __init__(self, name="Custom System"):
        self.name = name
        self.bodies = []
        self.center_pos = Vec3(0, 0, 0)

    def add_body(self, body):
        self.bodies.append(body)
        if body.type == 'sun':
            self.center_pos = body.pos.copy()

    def update(self, dt):
        for b in self.bodies:
            if b.parent:
                parent = next((p for p in self.bodies if p == b.parent), None)
                parent_pos = parent.pos if parent else self.center_pos
                b.update_orbit(dt, parent_pos)

    def draw(self):
        for b in self.bodies:
            b.draw()

# --- Procedural Universe (kept for background) ---
class Universe:
    def __init__(self):
        self.chunk_size = 2000
        self.planets = {}

    def get_chunk(self, pos):
        return (int(pos.x // self.chunk_size), int(pos.y // self.chunk_size), int(pos.z // self.chunk_size))

    def generate_chunk(self, cx, cy, cz):
        chunk_key = (cx, cy, cz)
        if chunk_key in self.planets: return
        random.seed(hash(chunk_key))
        num_planets = random.randint(0, 2)
        chunk_planets = []
        for _ in range(num_planets):
            px = cx * self.chunk_size + random.randint(0, self.chunk_size)
            py = cy * self.chunk_size + random.randint(0, self.chunk_size)
            pz = cz * self.chunk_size + random.randint(0, self.chunk_size)
            radius = random.randint(80, 250)
            color = (random.random(), random.random(), random.random())
            chunk_planets.append(Planet(Vec3(px, py, pz), {'seed': 'proc', 'params': {'radius': radius}, 'colors': {'ocean': '#4488ff'}}, None))
        self.planets[chunk_key] = chunk_planets

    def get_active_planets(self, player_pos):
        cx, cy, cz = self.get_chunk(player_pos)
        active = []
        for x in range(cx-1, cx+2):
            for y in range(cy-1, cy+2):
                for z in range(cz-1, cz+2):
                    self.generate_chunk(x, y, z)
                    active.extend(self.planets[(x, y, z)])
        return active

# --- Player (Flying Saucer with GTA camera) ---
class Saucer:
    def __init__(self):
        self.pos = Vec3(0, 150, 0)
        self.vel = Vec3(0, 0, 0)
        self.yaw = 0.0
        self.pitch = 0.0
        self.speed = 0.0
        self.max_speed = 42.0
        self.quadric = gluNewQuadric()

        self.cam_yaw = 180.0
        self.cam_pitch = 18.0
        self.cam_dist = 52.0

        self.landed_on = None
        self.ui_message = "W/S Thrust • A/D Yaw • RMB+Mouse = Camera • I = Load Editor ZIP"

    def get_forward_vector(self):
        rad_yaw = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)
        fx = math.sin(rad_yaw) * math.cos(rad_pitch)
        fy = -math.sin(rad_pitch)
        fz = -math.cos(rad_yaw) * math.cos(rad_pitch)
        return Vec3(fx, fy, fz)

    def update(self, keys, planets, mouse_dx, mouse_dy, right_held, wheel_delta):
        if self.landed_on:
            self.ui_message = f"Landed on {getattr(self.landed_on, 'name', 'Planet')} - SPACE to takeoff"
            if keys[K_SPACE]:
                self.landed_on = None
                self.speed = 10.0
                self.vel = self.get_forward_vector().mul(self.speed)
            return

        # WSAD Controls
        if keys[K_w]: self.speed += 0.85
        elif keys[K_s]: self.speed -= 0.95
        else: self.speed *= 0.96

        self.speed = max(-15.0, min(self.speed, self.max_speed))

        if keys[K_a] or keys[K_LEFT]: self.yaw += 3.2
        if keys[K_d] or keys[K_RIGHT]: self.yaw -= 3.2

        if keys[K_SPACE]: self.pos.y += 2.5
        if keys[K_LCTRL] or keys[K_c]: self.pos.y -= 2.5

        self.pitch -= wheel_delta * 4.5
        self.pitch = max(-78, min(78, self.pitch))

        forward = self.get_forward_vector()
        self.vel = forward.mul(self.speed)
        self.pos = self.pos.add(self.vel)

        # GTA Camera
        if right_held:
            self.cam_yaw += mouse_dx * 0.28
            self.cam_pitch -= mouse_dy * 0.26
            self.cam_pitch = max(-68, min(68, self.cam_pitch))
        else:
            target_yaw = self.yaw + 180.0
            self.cam_yaw = lerp_angle(self.cam_yaw, target_yaw, 0.12)
            self.cam_pitch = lerp(self.cam_pitch, 18.0, 0.09)

        # Landing / Collisions
        for p in planets:
            dist = self.pos.dist(p.pos)
            if dist < p.radius + 23:
                if abs(self.speed) < 11.0:
                    self.landed_on = p
                    self.speed = 0.0
                    self.vel = Vec3(0,0,0)
                    direction = self.pos.sub(p.pos).normalize()
                    self.pos = p.pos.add(direction.mul(p.radius + 7))
                    self.pitch = -82
                else:
                    self.ui_message = "WARNING: Too fast! Bouncing off atmosphere!"
                    self.pos = self.pos.sub(self.vel.mul(2.0))
                    self.speed *= 0.3

    def draw(self):
        glPushMatrix()
        glTranslatef(self.pos.x, self.pos.y, self.pos.z)
        glRotatef(self.yaw, 0, 1, 0)
        glRotatef(self.pitch, 1, 0, 0)

        glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, [0.78, 0.80, 0.85, 1.0])
        glMaterialf(GL_FRONT, GL_SHININESS, 85.0)
        glPushMatrix()
        glScalef(1.05, 0.21, 1.05)
        gluSphere(self.quadric, 5.4, 36, 36)
        glPopMatrix()

        glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, [0.08, 1.0, 0.22, 1.0])
        glMaterialfv(GL_FRONT, GL_EMISSION, [0.0, 0.45, 0.08, 1.0])
        glPushMatrix()
        glTranslatef(0, 1.6, 0)
        gluSphere(self.quadric, 2.9, 24, 24)
        glPopMatrix()
        glMaterialfv(GL_FRONT, GL_EMISSION, [0.0, 0.0, 0.0, 1.0])

        glPopMatrix()

# --- UI Text ---
def draw_text(x, y, text, font, window_size):
    text_surface = font.render(text, True, (0, 255, 110), (0, 0, 0, 0))
    text_data = pygame.image.tostring(text_surface, "RGBA", True)
    w, h = text_surface.get_size()

    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, window_size[0], 0, window_size[1])

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glRasterPos2i(x, y)
    glDrawPixels(w, h, GL_RGBA, GL_UNSIGNED_BYTE, text_data)
    glDisable(GL_BLEND)

    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

# --- Load Editor ZIPs ---
custom_systems = []

def load_editor_zip():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(filetypes=[("Editor Files", "*.zip")])
    if not file_path: return

    try:
        with zipfile.ZipFile(file_path) as z:
            if 'galaxy_data.json' in z.namelist():
                load_galaxy(z)
            elif 'system_data.json' in z.namelist():
                load_solar_system(z)
            elif 'planet_data.json' in z.namelist():
                load_single_planet(z)
            else:
                player.ui_message = "Unknown editor file format"
    except Exception as e:
        player.ui_message = f"Load error: {str(e)[:40]}"

def load_single_planet(zip_obj):
    data = json.loads(zip_obj.read("planet_data.json").decode())
    heightmap_bytes = zip_obj.read("heightmap.png") if "heightmap.png" in zip_obj.namelist() else None
    p = player.pos.add(Vec3(random.randint(800,1400), random.randint(80,300), random.randint(800,1400)))
    planet = Planet(p, data, heightmap_bytes)
    sys = SolarSystem(planet.name)
    sys.add_body(planet)
    custom_systems.append(sys)
    player.ui_message = f"Loaded planet: {planet.name}"

def load_solar_system(zip_obj):
    manifest = json.loads(zip_obj.read("system_data.json").decode())
    sys = SolarSystem(manifest.get('name', 'Imported System'))
    sys.center_pos = player.pos.copy()

    for info in manifest.get('bodies', []):
        if info['file'] in zip_obj.namelist():
            body_zip = zipfile.ZipFile(BytesIO(zip_obj.read(info['file'])))
            data = json.loads(body_zip.read("planet_data.json").decode())
            h_bytes = body_zip.read("heightmap.png") if "heightmap.png" in body_zip.namelist() else None
            pos = sys.center_pos.add(Vec3(info.get('orbitDistance', 300), 0, 0))
            planet = Planet(pos, data, h_bytes)
            planet.orbitDistance = info.get('orbitDistance', 0)
            planet.orbitSpeed = info.get('orbitSpeed', 0.2)
            # Simple parent (by order)
            if info.get('parentId') is not None and info['parentId'] < len(sys.bodies):
                planet.parent = sys.bodies[info['parentId']]
            sys.add_body(planet)

    custom_systems.append(sys)
    player.ui_message = f"Loaded system: {sys.name}"

def load_galaxy(zip_obj):
    galaxy = json.loads(zip_obj.read("galaxy_data.json").decode())
    for sys_data in galaxy.get('systems', [])[:4]:  # limit for performance
        sys = SolarSystem(sys_data.get('name', 'Galaxy System'))
        sys.center_pos = player.pos.add(Vec3(random.randint(-2000,2000), 0, random.randint(-2000,2000)))
        for body_data in sys_data.get('bodies', []):
            pos = sys.center_pos.add(Vec3(body_data.get('orbitDistance', 0), 0, 0))
            planet = Planet(pos, body_data)
            planet.orbitDistance = body_data.get('orbitDistance', 0)
            planet.orbitSpeed = body_data.get('orbitSpeed', 0.2)
            sys.add_body(planet)
        custom_systems.append(sys)
    player.ui_message = f"Loaded galaxy chunk: {galaxy.get('name', 'Galaxy')}"

# --- Main ---
def main():
    pygame.init()
    window_size = (1280, 720)
    pygame.display.set_mode(window_size, DOUBLEBUF | OPENGL)
    pygame.display.set_caption("Procedural Retro Saucer + Editor Integration")

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_COLOR_MATERIAL)
    glEnable(GL_NORMALIZE)

    glLightfv(GL_LIGHT0, GL_POSITION, [0.6, 1.0, 0.7, 0.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 0.98, 1.0])

    glEnable(GL_FOG)
    glFogi(GL_FOG_MODE, GL_EXP2)
    glFogf(GL_FOG_DENSITY, 0.00038)

    glMatrixMode(GL_PROJECTION)
    gluPerspective(66.0, window_size[0]/window_size[1], 1.0, 6000.0)
    glMatrixMode(GL_MODELVIEW)

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Consolas", 23, bold=True)

    global universe, player
    universe = Universe()
    player = Saucer()

    stars = [Vec3(random.randint(-1400,1400), random.randint(-900,900), random.randint(-1400,1400)) for _ in range(1400)]

    running = True
    i_pressed = False

    while running:
        wheel_delta = 0
        for event in pygame.event.get():
            if event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
                running = False
            if event.type == MOUSEWHEEL:
                wheel_delta = event.y

        keys = pygame.key.get_pressed()

        # Import key
        if keys[K_i]:
            if not i_pressed:
                i_pressed = True
                load_editor_zip()
        else:
            i_pressed = False

        right_held = pygame.mouse.get_pressed()[2]
        if right_held:
            pygame.mouse.set_visible(False)
            rel = pygame.mouse.get_rel()
            mouse_dx, mouse_dy = rel[0], rel[1]
        else:
            pygame.mouse.set_visible(True)
            mouse_dx, mouse_dy = 0, 0

        cx, cy, cz = universe.get_chunk(player.pos)
        random.seed(hash((cx, cy, cz)))
        nebula_color = [random.uniform(0.01, 0.17), random.uniform(0.0, 0.07), random.uniform(0.03, 0.20), 1.0]
        glFogfv(GL_FOG_COLOR, nebula_color)
        glClearColor(*nebula_color)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        active_planets = universe.get_active_planets(player.pos)

        player.update(keys, active_planets, mouse_dx, mouse_dy, right_held, wheel_delta)

        # Camera
        rad_y = math.radians(player.cam_yaw)
        rad_p = math.radians(player.cam_pitch)
        cam_x = player.pos.x - math.sin(rad_y) * math.cos(rad_p) * player.cam_dist
        cam_y = player.pos.y + math.sin(rad_p) * player.cam_dist + 16.0
        cam_z = player.pos.z - math.cos(rad_y) * math.cos(rad_p) * player.cam_dist

        gluLookAt(cam_x, cam_y, cam_z, player.pos.x, player.pos.y + 6, player.pos.z, 0, 1, 0)

        # Procedural planets
        for p in active_planets:
            p.draw()

        # Custom loaded systems
        for sys in custom_systems:
            sys.update(1/60.0)
            sys.draw()

        # Stars
        glDisable(GL_LIGHTING)
        glPointSize(1.8)
        glColor3f(0.95, 0.97, 1.0)
        glBegin(GL_POINTS)
        for star in stars:
            sx = ((star.x - player.pos.x) % 2800) - 1400 + player.pos.x
            sy = ((star.y - player.pos.y) % 2000) - 1000 + player.pos.y
            sz = ((star.z - player.pos.z) % 2800) - 1400 + player.pos.z
            glVertex3f(sx, sy, sz)
        glEnd()
        glEnable(GL_LIGHTING)

        player.draw()

        # UI
        speed_text = f"SPEED: {int(max(0, player.speed) / player.max_speed * 100)}%"
        sector_text = f"SECTOR: {cx}, {cy}, {cz}"
        draw_text(28, window_size[1] - 48, player.ui_message, font, window_size)
        draw_text(28, window_size[1] - 88, speed_text, font, window_size)
        draw_text(28, window_size[1] - 128, sector_text, font, window_size)

        pygame.display.flip()
        clock.tick(75)

    pygame.quit()

if __name__ == '__main__':
    main()
