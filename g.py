import os
import sys
import pygame
import hid
import threading
import queue
import random
import logging

# Configure logging to log to both a file and the console
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s')
file_handler = logging.FileHandler('game_log.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
logging.getLogger().addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

# Constants for the display
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60

# Set up the colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Arcade Game with XK-12 Joystick")
clock = pygame.time.Clock()
global game_over
game_over = False
MAX_FOOD_ITEMS = 10  # Maximum number of food items allowed at any time

def normalize_joystick_value(value):
    # Normalization to -1 to 1 range
    if value > 128:
        normalized_value = (value - 256) / 128
    else:
        normalized_value = value / 127
    return normalized_value

def normalize_y_axis(value):
    return normalize_joystick_value(value)

def find_device(vid, pid):
    # Look for the device with the specified Vendor ID and Product ID
    for device_info in hid.enumerate():
        if device_info['vendor_id'] == vid and device_info['product_id'] == pid:
            return device_info
    return None

def device_read_thread(device, data_queue, stop_event):
    while not stop_event.is_set():
        data = device.read(33)  # Adjust the number of bytes per XK-12 specification
        if data:
            data_queue.put(data)

def open_device():
    # Vendor ID and Product ID for X-keys device
    device_info = find_device(0x05f3, 0x0429)
    if not device_info:
        print("Device not found.")
        sys.exit()

    device = hid.device()
    device_path = device_info['path']
    try:
        device.open_path(device_path)
        print("Device opened successfully.")
        return device
    except Exception as e:
        print(f"Failed to open device: {e}")
        sys.exit()

def parse_joystick(data, button_states):
    # Interpret bytes for button states
    button_map = {
        0: [1, 5, 9],   # Byte 2: Column 1
        1: [2, 6, 10],  # Byte 3: Column 2
        2: [3, 7, 11],  # Byte 4: Column 3
        3: [4, 8, 12]   # Byte 5: Column 4
    }

    pressed_buttons = []

    for column in range(4):  # Four bytes for columns (D1 to D4)
        byte_value = data[2 + column]
        for bit in range(3):  # Each byte has 3 relevant bits
            button_index = button_map[column][bit] - 1
            mask = 1 << bit
            if byte_value & mask:
                if button_states[button_index] != "Pressed":
                    button_states[button_index] = "Pressed"
                    pressed_buttons.append(button_map[column][bit])
            else:
                if button_states[button_index] == "Pressed":
                    button_states[button_index] = "Released"
    
    if pressed_buttons:
        print(" and ".join(map(str, pressed_buttons)) + " pressed")

    # Extract raw X, Y, and Z data
    raw_x = data[6]
    raw_y = data[7]
    raw_z = data[8]

    # Normalize X, Y, and Z
    x_normalized = normalize_joystick_value(raw_x)
    y_normalized = -normalize_y_axis(raw_y)  # Invert Y-axis for correct screen coordinates
    z_normalized = -normalize_joystick_value(raw_z)
    return x_normalized, y_normalized, z_normalized

class Player(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.image = pygame.Surface((50, 50))
        self.image.fill(GREEN)
        self.rect = self.image.get_rect()
        self.rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        self.speed = 5
        self.size = 50

    def move(self, x, y):
        self.rect.x += x * self.speed
        self.rect.y -= y * self.speed  # Invert y for correct screen coordinates
        self.rect.clamp_ip(screen.get_rect())

    def grow(self, value=1):
        self.size += 5 * value
        self.image = pygame.Surface((self.size, self.size))
        self.image.fill(GREEN)
        self.rect = self.image.get_rect(center=self.rect.center)

def scale_down_and_spawn_enemy():
    scaling_factor = 0.9  # Example scaling for noticeable effect
    for sprite in all_sprites:
        # Adjust sprite size
        new_width = int(sprite.rect.width * scaling_factor)
        new_height = int(sprite.rect.height * scaling_factor)
        sprite.image = pygame.transform.scale(sprite.image, (new_width, new_height))
        sprite.rect.size = (new_width, new_height)
        # Adjust sprite position to scale towards the center
        sprite.rect.x = int(sprite.rect.x * scaling_factor)
        sprite.rect.y = int(sprite.rect.y * scaling_factor)

    spawn_new_enemy()

def adjust_zoom():
    target_size_percentage = 0.15  # Target size of the player as a percentage of screen width
    actual_percentage = player.rect.width / SCREEN_WIDTH
    if actual_percentage > target_size_percentage:
        zoom_factor = target_size_percentage / actual_percentage
        # Adjust sizes and positions of all sprites
        for sprite in all_sprites:
            old_center = sprite.rect.center  # Store the old center
            sprite.rect.width = int(sprite.rect.width * zoom_factor)
            sprite.rect.height = int(sprite.rect.height * zoom_factor)
            sprite.image = pygame.transform.scale(sprite.image, (sprite.rect.width, sprite.rect.height))
            sprite.rect.center = old_center  # Reset center to keep position consistent

        # Ensure the player remains properly positioned at the center
        player.rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)



def spawn_new_enemy():
    new_enemy = Enemy()
    new_enemy.size = random.randint(60, 100)  # Set a random size
    new_enemy.image = pygame.Surface((new_enemy.size, new_enemy.size))
    new_enemy.image.fill(RED)
    new_enemy.rect = new_enemy.image.get_rect()
    place_enemy_safely(new_enemy)
    enemies.add(new_enemy)
    all_sprites.add(new_enemy)
    logging.debug(f"New enemy spawned, size: {new_enemy.size}")

def place_enemy_safely(enemy):
    """ Place new enemy ensuring it doesn't overlap with the player or other enemies. """
    placed = False
    while not placed:
        enemy.rect.x = random.randint(0, SCREEN_WIDTH - enemy.rect.width)
        enemy.rect.y = random.randint(0, SCREEN_HEIGHT - enemy.rect.height)
        if not pygame.sprite.collide_rect(player, enemy) and not any(pygame.sprite.collide_rect(enemy, other) for other in enemies if other != enemy):
            placed = True

class Food(pygame.sprite.Sprite):
    def __init__(self, value=1):
        super().__init__()
        self.image = pygame.Surface((20, 20))
        self.image.fill(WHITE)
        self.rect = self.image.get_rect()
        self.rect.x = random.randint(0, SCREEN_WIDTH - 20)
        self.rect.y = random.randint(0, SCREEN_HEIGHT - 20)
        self.speed = 1  # Add speed attribute
        self.direction = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])  # Random initial direction
        self.value = value  # Nutritional value of the food

    def update(self):
        self.rect.x += self.direction[0] * self.speed
        self.rect.y += self.direction[1] * self.speed

        # Bounce off walls
        if self.rect.left < 0 or self.rect.right > SCREEN_WIDTH:
            self.direction = (-self.direction[0], self.direction[1])
        if self.rect.top < 0 or self.rect.bottom > SCREEN_HEIGHT:
            self.direction = (self.direction[0], -self.direction[1])

            
class Enemy(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.size = random.randint(60, 100)
        self.image = pygame.Surface((self.size, self.size))
        self.image.fill(RED)
        self.rect = self.image.get_rect()
        self.rect.x = random.randint(0, SCREEN_WIDTH - self.size)
        self.rect.y = random.randint(0, SCREEN_HEIGHT - self.size)
        self.is_converted = False
        self.speed = 2
        self.direction = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])

    def update(self):
        # Check if should be converted to food
        if player.size > self.size and not self.is_converted:
            self.is_converted = True
            self.image.fill(YELLOW)  # Change color to yellow to indicate it's now food
            self.speed = 1  # Make the converted enemy move like food
            self.direction = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])  # Give it a random direction

        # Movement logic
        if self.is_converted:
            self.rect.x += self.direction[0] * self.speed
            self.rect.y += self.direction[1] * self.speed
            # Bounce off walls
            if self.rect.left < 0 or self.rect.right > SCREEN_WIDTH:
                self.direction = (-self.direction[0], self.direction[1])
            if self.rect.top < 0 or self.rect.bottom > SCREEN_HEIGHT:
                self.direction = (self.direction[0], -self.direction[1])
        else:
            self.rect.x += random.choice([-1, 1]) * self.speed
            self.rect.y += random.choice([-1, 1]) * self.speed

        self.rect.clamp_ip(screen.get_rect())





def spawn_player_safely():
    safe = False
    while not safe:
        player.rect.center = (random.randint(50, SCREEN_WIDTH - 50), random.randint(50, SCREEN_HEIGHT - 50))
        safe = True
        for enemy in enemies:
            if pygame.sprite.collide_rect(player, enemy):
                safe = False
                break

def reset_game():
    global game_over
    spawn_player_safely()
    player.size = 50
    player.image = pygame.Surface((player.size, player.size))
    player.image.fill(GREEN)

    foods.empty()
    enemies.empty()
    all_sprites.empty()
    all_sprites.add(player)

    for _ in range(5):
        food = Food()
        foods.add(food)
        all_sprites.add(food)

    for _ in range(3):
        enemy = Enemy()
        enemies.add(enemy)
        all_sprites.add(enemy)

    game_over = False
    logging.info("Game reset, total food items: {}, total enemies: {}".format(len(foods), len(enemies)))

def process_events():
    global running
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            stop_event.set()

def handle_joystick_input(button_states, data_queue):
    while not data_queue.empty():
        data = data_queue.get_nowait()
        if data:
            joystick_x, joystick_y, joystick_z = parse_joystick(data, button_states)
            if not game_over:
                player.move(joystick_x, joystick_y)

def handle_reset_game(button_states):
    if button_states[0] == "Pressed":
        if game_over:
            reset_game()
        else:
            reset_game()

def handle_food_collisions():
    collided_foods = pygame.sprite.spritecollide(player, foods, True)
    for food in collided_foods:
        player.grow(food.value)  # Grow based on food value
        logging.debug(f"Food eaten, value: {food.value}, player size: {player.size}")
        # Only add new food if we are below the limit
        if len(foods) < MAX_FOOD_ITEMS:
            new_food = Food()
            foods.add(new_food)
            all_sprites.add(new_food)
            logging.debug(f"New food added, total food items: {len(foods)}")
        else:
            logging.debug("Food limit reached, not adding new food")

def handle_enemy_collisions():
    global game_over
    for enemy in enemies:
        if pygame.sprite.collide_rect(player, enemy) and not enemy.is_converted:
            game_over = True
            logging.info("Game Over")



def update_game_state(button_states, data_queue):
    global game_over
    handle_joystick_input(button_states, data_queue)
    handle_reset_game(button_states)
    handle_food_collisions()
    handle_enemy_collisions()

    # Update all sprites
    all_sprites.update()
    # Adjust game zoom
    adjust_zoom()

    # Check for eaten enemies and potentially spawn new ones
    for enemy in list(enemies):
        if enemy.is_converted and pygame.sprite.collide_rect(player, enemy):
            enemies.remove(enemy)
            all_sprites.remove(enemy)
            logging.debug("Enemy eaten")
    
    # Maintain three enemies on the field
    while len(enemies) < 3:
        spawn_new_enemy()



def draw_game():
    screen.fill(BLACK)
    all_sprites.draw(screen)
    pygame.display.flip()

def initialize_game():
    global player, all_sprites, foods, enemies, game_over

    player = Player()
    all_sprites = pygame.sprite.Group(player)
    foods = pygame.sprite.Group()
    enemies = pygame.sprite.Group()

    for _ in range(5):
        food = Food()
        foods.add(food)
        all_sprites.add(food)

    for _ in range(3):
        enemy = Enemy()
        enemies.add(enemy)
        all_sprites.add(enemy)

    # Spawn player in a safe place
    spawn_player_safely()

    game_over = False

def main():
    try:
        device = open_device()
        data_queue = queue.Queue()
        stop_event = threading.Event()
        read_thread = threading.Thread(target=device_read_thread, args=(device, data_queue, stop_event))
        read_thread.start()

        global running
        running = True
        button_states = [None] * 12  # Initialize button states

        initialize_game()

        while running:
            process_events()
            update_game_state(button_states, data_queue)
            draw_game()
            clock.tick(FPS)

        read_thread.join()
        device.close()
        pygame.quit()

    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
