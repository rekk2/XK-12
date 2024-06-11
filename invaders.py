import pygame
import hid
import threading
import queue
import math
import random
import sys
import json

# Constants
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)

class JoystickHandler:
    def __init__(self):
        print("Initializing JoystickHandler...")
        self.device_info = self.find_device(0x05f3, 0x0429)
        if not self.device_info:
            print("Device not found. Exiting...")
            sys.exit()
        self.device = self.open_device()
        self.data_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.button_states = ['Released'] * 12
        threading.Thread(target=self.device_read_thread, daemon=True).start()
        print("JoystickHandler initialized.")

    def find_device(self, vid, pid):
        for device_info in hid.enumerate():
            if device_info['vendor_id'] == vid and device_info['product_id'] == pid:
                return device_info
        return None

    def open_device(self):
        try:
            device = hid.device()
            device.open_path(self.device_info['path'])
            print("Device opened successfully.")
            return device
        except Exception as e:
            print(f"Failed to open HID device: {e}")
            sys.exit()


    def device_read_thread(self):
        while not self.stop_event.is_set():
            try:
                data = self.device.read(33)
                if data:
                    self.data_queue.put(data)
            except Exception as e:
                print(f"Error reading device: {e}")
                break


    def normalize_joystick_value(self, value):
        if value > 128:
            return (value - 256) / 128
        else:
            return value / 127

    def parse_joystick(self, data):
        button_map = {0: [1, 5, 9], 1: [2, 6, 10], 2: [3, 7, 11], 3: [4, 8, 12]}
        pressed_buttons = []
        for column in range(4):
            byte_value = data[2 + column]
            for bit in range(3):
                button_index = button_map[column][bit] - 1
                if byte_value & (1 << bit):
                    if self.button_states[button_index] != "Pressed":
                        self.button_states[button_index] = "Pressed"
                        pressed_buttons.append(button_map[column][bit])
                        print(f"Button {button_map[column][bit]} pressed")
                else:
                    if self.button_states[button_index] == "Pressed":
                        self.button_states[button_index] = "Released"
        raw_x, raw_y, raw_z = data[6], data[7], data[8]
        return (self.normalize_joystick_value(raw_x),
                self.normalize_joystick_value(raw_y),
                self.normalize_joystick_value(raw_z),
                pressed_buttons)

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.is_game_over = False
        self.load_round_data()
        self.reset_game()
        self.joystick = JoystickHandler()
        
    def load_round_data(self):
        try:
            with open('rounds.json', 'r') as file:
                self.rounds = json.load(file)["rounds"]
        except FileNotFoundError:
            print("Error: 'rounds.json' file not found.")
            sys.exit()
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            sys.exit()
            
    def reset_game(self):
        self.current_round_index = 0
        self.score = 0
        self.setup_round(self.current_round_index)
        self.is_game_over = False
        self.player.lives = 3  # Ensure lives are reset

            
    def setup_round(self, round_index):
        round_data = self.rounds[round_index]
        enemy_color = round_data["enemy_color"]
        self.asteroids = pygame.sprite.Group(Asteroid(color=enemy_color) for _ in range(10))
        self.player = Player(self.screen)


    def check_round_completion(self):
        if not self.asteroids:  # Checks if the group is empty
            if self.current_round_index < len(self.rounds) - 1:
                self.current_round_index += 1
            else:
                self.current_round_index = len(self.rounds) - 1  # Stay on the last round
            self.setup_round(self.current_round_index)
            
    def run(self):
        while True:
            self.handle_events()
            self.update_game_state()
            self.render_game()
            self.check_round_completion()
            pygame.display.flip()
            self.clock.tick(FPS)
            


    def handle_collisions(self):
        # Check collisions between player and asteroids
        if pygame.sprite.spritecollide(self.player, self.asteroids, True):
            self.player.lose_life()

        # Check for bullet collisions with asteroids
        for bullet in self.player.bullets:
            if pygame.sprite.spritecollide(bullet, self.asteroids, True):
                self.score += 100  # Update the score for each asteroid hit
                bullet.kill()  # Remove the bullet

    def update_game_state(self):
        if not self.joystick.data_queue.empty():
            data = self.joystick.data_queue.get()
            joystick_x, joystick_y, joystick_z, pressed_buttons = self.joystick.parse_joystick(data)
            if not self.is_game_over:  # Only update player if game is not over
                self.player.update(joystick_x, joystick_y, joystick_z, pressed_buttons)
        
        if self.is_game_over:
            if 2 in pressed_buttons:  # Check if button 2 is pressed
                print("Restarting game on button 2 press.")
                self.reset_game()

        self.asteroids.update()
        self.handle_collisions()  # Ensure collisions are checked outside the game over condition
        self.check_round_completion()
        self.player.bullets.update()


    def render_game(self):
        self.screen.fill(BLACK)
        if not self.is_game_over:
            self.asteroids.draw(self.screen)
            self.player.draw(self.screen)
            # Score and lives display
            score_text = self.font.render(f"Score: {self.score}", True, WHITE)
            self.screen.blit(score_text, (10, 10))
            lives_text = self.font.render(f"Lives: {self.player.lives}", True, WHITE)
            self.screen.blit(lives_text, (SCREEN_WIDTH - 100, 10))
        else:
            game_over_text = self.font.render("Game Over! Press Button 2 to Restart", True, RED)
            self.screen.blit(game_over_text, (SCREEN_WIDTH // 2 - game_over_text.get_width() // 2, SCREEN_HEIGHT // 2))
            
    def display_game_over_screen(self):
        self.screen.fill(BLACK)
        game_over_text = self.font.render("Game Over! Press 2 to Restart", True, RED)
        self.screen.blit(game_over_text, (SCREEN_WIDTH // 2 - game_over_text.get_width() // 2, SCREEN_HEIGHT // 2))
        
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.joystick.stop_event.set()
                self.joystick.device.close()
                pygame.quit()
                sys.exit()


class Player(pygame.sprite.Sprite):
    def __init__(self, screen):
        super().__init__()
        self.screen = screen  # Store the screen as an attribute
        self.image = pygame.Surface((50, 50), pygame.SRCALPHA)
        self.image.fill(GREEN)
        self.rect = self.image.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        self.turret_angle = 0
        self.bullets = pygame.sprite.Group()
        self.speed = 5
        self.lives = 3
        self.is_game_over = False
    
    def lose_life(self):
        if self.lives > 0:
            self.lives -= 1
        if self.lives <= 0:
            self.kill()
            self.is_game_over = True

    def update(self, joystick_x, joystick_y, joystick_z, button_states):
        self.rect.x += int(joystick_x * self.speed)
        self.rect.y += int(joystick_y * self.speed)
        self.rect.clamp_ip(self.screen.get_rect())
        
        self.turret_angle = joystick_z * math.pi * 180 / math.pi  # Convert radians to degrees
        self.turret_angle %= 360
        
        if 1 in button_states:
            self.fire()

    def fire(self):
        bullet = Bullet(self.rect.centerx, self.rect.centery, self.turret_angle, self.screen)  # Pass screen to Bullet
        self.bullets.add(bullet)

    def draw(self, surface):
        surface.blit(self.image, self.rect)
        self.bullets.draw(surface)
        turret_length = 30
        rad_turret_angle = math.radians(self.turret_angle)
        tip = (self.rect.centerx + turret_length * math.cos(rad_turret_angle),
               self.rect.centery + turret_length * math.sin(rad_turret_angle))
        pygame.draw.line(surface, RED, self.rect.center, tip, 5)


class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y, angle, screen):
        super().__init__()
        self.screen = screen  # Store the screen as an attribute
        self.image = pygame.Surface((5, 5))
        self.image.fill(WHITE)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = 10
        self.angle = angle

    def update(self):
        rad_angle = math.radians(self.angle)
        self.rect.x += self.speed * math.cos(rad_angle)
        self.rect.y += self.speed * math.sin(rad_angle)
        if not self.screen.get_rect().contains(self.rect):
            self.kill()


class Asteroid(pygame.sprite.Sprite):
    def __init__(self, color):
        super().__init__()
        self.image = pygame.Surface((30, 30))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=(random.randint(0, SCREEN_WIDTH), random.randint(0, SCREEN_HEIGHT)))
        self.speed = random.randint(1, 3)
        self.angle = random.randint(0, 360)

    def update(self):
        rad_angle = math.radians(self.angle)
        self.rect.x += self.speed * math.cos(rad_angle)
        self.rect.y += self.speed * math.sin(rad_angle)
        if self.rect.left <= 0 or self.rect.right >= SCREEN_WIDTH:
            self.angle = 180 - self.angle
        if self.rect.top <= 0 or self.rect.bottom >= SCREEN_HEIGHT:
            self.angle = -self.angle



if __name__ == "__main__":
    try:
        game = Game()
        game.run()
    except Exception as e:
        print(f"Unhandled exception: {e}")
        pygame.quit()
        sys.exit()
