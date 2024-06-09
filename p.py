import os
import sys
import pygame
import hid
import threading
import queue
import math
import logging

# Constants for the display
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
JOYSTICK_RADIUS = 100  

# Set up the colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
DARK_GREY = (169, 169, 169)
LIGHT_BLUE = (173, 216, 230)

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("X-keys XK-12 Joystick Debug Visualization")
clock = pygame.time.Clock()

# Set up logging
logging.basicConfig(filename='joystick_debug.log', level=logging.DEBUG, format='%(asctime)s - %(message)s')

def normalize_joystick_value(value):
    # Normalization to -1 to 1 range
    if value > 128:
        normalized_value = (value - 256) / 128
    else:
        normalized_value = value / 127
    logging.debug(f"Normalized joystick value: {normalized_value}")
    return normalized_value

def normalize_y_axis(value):
    # Normalize Y-axis value to handle the inversion correctly
    if value >= 0 and value <= 127:
        normalized_value = (value - 127) / 127.0  # Downward movement
    else:
        normalized_value = (255 - value) / 128.0  # Upward movement
    logging.debug(f"Normalized Y-axis value: {normalized_value}")
    return normalized_value

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
    y_normalized = normalize_y_axis(raw_y)  # Invert Y-axis for correct screen coordinates
    z_normalized = -normalize_joystick_value(raw_z)
    logging.debug(f"Raw values - X: {raw_x}, Y: {raw_y}, Z: {raw_z}")
    logging.debug(f"Normalized values - X: {x_normalized}, Y: {y_normalized}, Z: {z_normalized}")
    return x_normalized, y_normalized, z_normalized

def draw_joystick(joystick_x, joystick_y, joystick_z):
    joystick_center_x = SCREEN_WIDTH // 2
    joystick_center_y = SCREEN_HEIGHT // 2 - 150  # Move joystick area up
    joystick_pos_x = int(joystick_center_x + joystick_x * JOYSTICK_RADIUS)
    joystick_pos_y = int(joystick_center_y - joystick_y * JOYSTICK_RADIUS)  # Ensure correct direction
    logging.debug(f"Calculated joystick position - X: {joystick_pos_x}, Y: {joystick_pos_y}")

    # Draw joystick position as a circle
    pygame.draw.circle(screen, GREEN, (joystick_pos_x, joystick_pos_y), 10)

    # Indicate joystick twist with a line representing rotation
    angle_radians = joystick_z * math.pi  # Convert normalized rotation to radians
    end_x = joystick_pos_x + JOYSTICK_RADIUS * math.cos(angle_radians)
    end_y = joystick_pos_y - JOYSTICK_RADIUS * math.sin(angle_radians)
    pygame.draw.line(screen, RED, (joystick_pos_x, joystick_pos_y), (end_x, end_y), 5)


def draw_keyboard(button_states):
    keyboard_area_top = SCREEN_HEIGHT // 2 + 50  # Place below joystick area
    keyboard_area_height = 160
    keyboard_area_width = 210
    keyboard_area_left = (SCREEN_WIDTH - keyboard_area_width) // 2
    pygame.draw.rect(screen, DARK_GREY, (keyboard_area_left, keyboard_area_top, keyboard_area_width, keyboard_area_height))
    pygame.draw.rect(screen, RED, (keyboard_area_left, keyboard_area_top, keyboard_area_width, keyboard_area_height), 2)

    # Draw keys
    key_width = 40
    key_height = 40
    font = pygame.font.Font(None, 36)  # Set up font for numbering

    for i in range(12):
        row = i // 4
        col = i % 4
        key_left = keyboard_area_left + col * (key_width + 10) + 10
        key_top = keyboard_area_top + row * (key_height + 10) + 10
        if button_states[i] == "Pressed":
            pygame.draw.rect(screen, LIGHT_BLUE, (key_left, key_top, key_width, key_height))
        pygame.draw.rect(screen, RED, (key_left, key_top, key_width, key_height), 2)

        # Draw button numbers
        text_surface = font.render(str(i + 1), True, WHITE)
        text_rect = text_surface.get_rect(center=(key_left + key_width // 2, key_top + key_height // 2))
        screen.blit(text_surface, text_rect)

def draw_visualization(joystick_x, joystick_y, joystick_z, button_states):
    screen.fill(BLACK)  # Clear screen
    draw_joystick(joystick_x, joystick_y, joystick_z)
    draw_keyboard(button_states)
    pygame.display.flip()

def main():
    try:
        device = open_device()
        data_queue = queue.Queue()
        stop_event = threading.Event()
        read_thread = threading.Thread(target=device_read_thread, args=(device, data_queue, stop_event))
        read_thread.start()

        button_states = [None] * 12  # Initialize button states

        # Main loop
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    stop_event.set()

            # Process joystick data
            while not data_queue.empty():
                data = data_queue.get_nowait()
                if data:
                    joystick_x, joystick_y, joystick_z = parse_joystick(data, button_states)
                    draw_visualization(joystick_x, joystick_y, joystick_z, button_states)

            clock.tick(FPS)

        read_thread.join()
        device.close()
        pygame.quit()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
