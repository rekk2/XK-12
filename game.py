import os
import sys
import pygame
import hid
import math
import threading
import queue

# Constants for the game
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
JOYSTICK_CENTER = (400, 300)
JOYSTICK_RADIUS = 300  # Increased radius for wider movement
ACCELERATION = 0.5
DECELERATION = 0.95

# Set up the colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("X-keys XK-12 Joystick Visualization")
clock = pygame.time.Clock()

# Determine the path to the arrow image
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader extends the sys module by a flag frozen=True
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(__file__)

image_path = os.path.join(application_path, 'arrow.png')

# Load the arrow image and scale it
arrow_image = pygame.image.load(image_path).convert_alpha()
arrow_image = pygame.transform.scale(arrow_image, (100, 100))

def find_device(vid, pid):
    for device_info in hid.enumerate():
        if device_info['vendor_id'] == vid and device_info['product_id'] == pid:
            return device_info
    return None

def device_read_thread(device, data_queue, stop_event):
    while not stop_event.is_set():
        data = device.read(33)
        if data:
            data_queue.put(data)

def open_device():
    device_info = find_device(0x05f3, 0x0429)  # VID and PID for X-keys device
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

def parse_joystick(data):
    x = (data[6] - 128) / 128.0 * JOYSTICK_RADIUS
    y = (data[7] - 128) / 128.0 * JOYSTICK_RADIUS
    z = (data[8] - 128) / 128.0 * 360  # Twist should affect the rotation fully around 360 degrees
    return x, y, z

def draw_joystick(x, y, z):
    # Calculate angle for arrow rotation based on Z-axis (twist) movement
    rotated_image = pygame.transform.rotate(arrow_image, -z)
    new_rect = rotated_image.get_rect(center=(x, y))
    screen.fill(BLACK)  # Clear the screen
    screen.blit(rotated_image, new_rect)  # Draw rotated image at new position
    pygame.display.flip()  # Update the display

def main():
    device = open_device()
    data_queue = queue.Queue()
    stop_event = threading.Event()
    read_thread = threading.Thread(target=device_read_thread, args=(device, data_queue, stop_event))
    read_thread.start()

    # Initialize positions and velocities
    x, y = JOYSTICK_CENTER
    velocity_x = velocity_y = 0
    rotation = 0

    # Main loop
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Try to get data from the queue
        while not data_queue.empty():
            data = data_queue.get_nowait()
            if data:
                joystick_x, joystick_y, joystick_z = parse_joystick(data)
                
                # Adjust y to move correctly up and down
                joystick_y = -joystick_y

                # Update velocities based on joystick input
                if abs(joystick_x) > 1 or abs(joystick_y) > 1:
                    velocity_x += joystick_x * ACCELERATION / 128.0
                    velocity_y += joystick_y * ACCELERATION / 128.0
                    rotation = joystick_z
                else:
                    # Apply deceleration when joystick is not being moved
                    velocity_x *= DECELERATION
                    velocity_y *= DECELERATION

        # Update positions based on velocity
        x += velocity_x
        y += velocity_y

        # Reverse direction if edge of canvas is reached
        if x <= 0 or x >= SCREEN_WIDTH:
            velocity_x = -velocity_x
            x = max(0, min(SCREEN_WIDTH, x))
        if y <= 0 or y >= SCREEN_HEIGHT:
            velocity_y = -velocity_y
            y = max(0, min(SCREEN_HEIGHT, y))

        # Draw joystick position and rotation
        draw_joystick(x, y, rotation)

        # Maintain framerate
        clock.tick(FPS)

    stop_event.set()
    read_thread.join()
    device.close()
    print("Device closed.")
    pygame.quit()

if __name__ == "__main__":
    main()
