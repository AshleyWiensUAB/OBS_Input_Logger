import obspython as obs
import time
import csv
import threading
import queue
import os
from datetime import datetime

try:
    from pynput import keyboard, mouse
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

try:
    from inputs import get_gamepad, UnpluggedError
    GAMEPAD_AVAILABLE = True
except ImportError:
    GAMEPAD_AVAILABLE = False

# --- GLOBALS ---
is_recording = False
is_running = True
start_time = 0.0
event_queue = queue.Queue()
fps = 30.0                  #Used as a default if fetch fails

writer_thread = None
gamepad_thread = None
keyboard_listener = None
mouse_listener = None
req_client = None

OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = "hH72oSHyCsMVdS2n"

# --- XBOX CONTROLLER MAPPINGS ---
XBOX_BUTTONS = {
    'BTN_SOUTH': 'A Button',
    'BTN_EAST': 'B Button',
    'BTN_NORTH': 'X Button',
    'BTN_WEST': 'Y Button',
    'BTN_TL': 'Left Bumper (LB)',
    'BTN_TR': 'Right Bumper (RB)',
    'BTN_SELECT': 'View Button (Back)',
    'BTN_START': 'Menu Button (Start)',
    'BTN_THUMBL': 'Left Stick Click (L3)',
    'BTN_THUMBR': 'Right Stick Click (R3)',
    'BTN_MODE': 'Xbox Guide Button'
}

XBOX_AXES = {
    'ABS_Z': 'Left Trigger (LT)',
    'ABS_RZ': 'Right Trigger (RT)',
    'ABS_X': 'Left Stick X',
    'ABS_Y': 'Left Stick Y',
    'ABS_RX': 'Right Stick X',
    'ABS_RY': 'Right Stick Y'
}

def log_event(event_type, details):
    """Calculates the time since recording started using system time and queues the event."""
    if is_recording:
        timestamp = time.perf_counter() - start_time
        event_queue.put(("INPUT", [round(timestamp, 4), (timestamp * fps) // 1, event_type, details]))

# --- KEYBOARD & MOUSE CALLBACKS ---
def on_press(key):
    try:
        log_event("KEY_PRESS", key.char)
    except AttributeError:
        log_event("KEY_PRESS", str(key))

def on_release(key):
    try:
        log_event("KEY_RELEASE", key.char)
    except AttributeError:
        log_event("KEY_RELEASE", str(key))

def on_click(x, y, button, pressed):
    action = "MOUSE_DOWN" if pressed else "MOUSE_UP"
    log_event(action, f"{button.name} at ({x}, {y})")

def on_scroll(x, y, dx, dy):
    direction = "SCROLL_UP" if dy > 0 else "SCROLL_DOWN"
    log_event(direction, f"({x}, {y})")

# --- XBOX GAMEPAD WORKER THREAD ---
def gamepad_worker():
    """Continuously polls for Xbox gamepad inputs with specific hardware translations."""
    last_states = {}
    
    # Filter thresholds
    STICK_DEADZONE = 4000      # Thumbsticks: -32768 to 32767
    STICK_DELTA = 500          # Minimum stick movement required to log
    TRIGGER_DEADZONE = 10      # Triggers: 0 to 255
    TRIGGER_DELTA = 5          # Minimum trigger movement required to log

    while is_running:
        try:
            events = get_gamepad()
            for event in events:
                if not is_recording or event.ev_type == 'Sync':
                    continue
                    
                code = event.code
                state = event.state
                
                # 1. Digital Face Buttons & Bumpers
                if event.ev_type == 'Key':
                    button_name = XBOX_BUTTONS.get(code, code)
                    action = "XBOX_BUTTON_DOWN" if state == 1 else "XBOX_BUTTON_UP"
                    log_event(action, button_name)
                    
                # 2. Analog Inputs (Sticks, Triggers, and D-Pad)
                elif event.ev_type == 'Absolute':
                    last_val = last_states.get(code, 0)
                    
                    # --- D-PAD CARVE-OUT (HAT AXES) ---
                    if "HAT" in code:
                        if code == 'ABS_HAT0Y': # Up / Down
                            if state == -1:
                                log_event("XBOX_DPAD", "D-Pad Up Pressed")
                            elif state == 1:
                                log_event("XBOX_DPAD", "D-Pad Down Pressed")
                            elif state == 0 and last_val != 0:
                                log_event("XBOX_DPAD", "D-Pad Y Released")
                        elif code == 'ABS_HAT0X': # Left / Right
                            if state == -1:
                                log_event("XBOX_DPAD", "D-Pad Left Pressed")
                            elif state == 1:
                                log_event("XBOX_DPAD", "D-Pad Right Pressed")
                            elif state == 0 and last_val != 0:
                                log_event("XBOX_DPAD", "D-Pad X Released")
                        last_states[code] = state
                        continue
                        
                    # --- TRIGGERS (LT / RT) ---
                    if code in ['ABS_Z', 'ABS_RZ']:
                        if state < TRIGGER_DEADZONE:
                            state = 0
                        if abs(state - last_val) >= TRIGGER_DELTA or (state == 0 and last_val != 0):
                            last_states[code] = state
                            axis_name = XBOX_AXES.get(code, code)
                            log_event("XBOX_TRIGGER", f"{axis_name} = {state}")
                            
                    # --- THUMBSTICKS (LS / RS) ---
                    else:
                        if abs(state) < STICK_DEADZONE:
                            state = 0
                        if abs(state - last_val) >= STICK_DELTA or (state == 0 and last_val != 0):
                            last_states[code] = state
                            axis_name = XBOX_AXES.get(code, code)
                            log_event("XBOX_STICK", f"{axis_name} = {state}")
                            
        except Exception:
            time.sleep(1.0)

# --- CSV WRITER THREAD ---
def csv_writer_worker():
    current_file = None
    writer = None
    
    while True:
        command, payload = event_queue.get()
        
        if command == "QUIT":
            if current_file:
                current_file.close()
            break
            
        elif command == "START_RECORDING":
            current_file = open(payload, 'w', newline='')
            writer = csv.writer(current_file)
            writer.writerow(["Timestamp (s)", "Frame", "Event Type", "Details"])
            
        elif command == "STOP_RECORDING":
            if current_file:
                current_file.close()
                current_file = None
                writer = None
                
        elif command == "INPUT":
            if writer:
                writer.writerow(payload)

# --- OBS EVENT LISTENER ---
def on_event(event):
    global is_recording, start_time, fps
    
    if event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTED:
        start_time = time.perf_counter()
        is_recording = True
        
        csv_path = None
        
        # Fetch the exact FPS from OBS settings when recording starts
        try:
            fps = obs.obs_get_active_fps()
        except Exception as e:
            print(f"[Warning] Could not fetch FPS from OBS: {e}. Defaulting to {fps:.1f}")

        try:
            output = obs.obs_frontend_get_recording_output()
            if output:
                settings = obs.obs_output_get_settings(output)
                video_path = obs.obs_data_get_string(settings, "path")
                
                if video_path:
                    csv_path = video_path.rsplit('.', 1)[0] + ".csv"
                    
                obs.obs_data_release(settings)
                obs.obs_output_release(output)
        except Exception as e:
            print(f"[Input Logger] Warning: Could not fetch video path ({e})")
            
        if not csv_path:
            csv_path = os.path.join(os.path.expanduser("~"), f"input_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

        event_queue.put(("START_RECORDING", csv_path))
        print(f"[Input Logger] Recording STARTED. Saving inputs to: {csv_path}")
        
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED:
        is_recording = False
        event_queue.put(("STOP_RECORDING", None))
        print("[Input Logger] Recording STOPPED.")

# --- OBS SCRIPT LIFECYCLE ---
def script_description():
    return "Logs keyboard, mouse, and Xbox controller inputs (with D-Pad support and clean mappings) using system time."

def script_load(settings):
    global writer_thread, gamepad_thread, keyboard_listener, mouse_listener, is_running, req_client
    is_running = True
    
    if not PYNPUT_AVAILABLE:
        print("[Input Logger] ERROR: 'pynput' is not installed.")
    if not GAMEPAD_AVAILABLE:
        print("[Input Logger] WARNING: 'inputs' is not installed. Gamepad logging disabled.")

    obs.obs_frontend_add_event_callback(on_event)

    writer_thread = threading.Thread(target=csv_writer_worker, daemon=True)
    writer_thread.start()

    if PYNPUT_AVAILABLE:
        keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        mouse_listener = mouse.Listener(on_click=on_click, on_scroll=on_scroll)
        keyboard_listener.start()
        mouse_listener.start()

    if GAMEPAD_AVAILABLE:
        gamepad_thread = threading.Thread(target=gamepad_worker, daemon=True)
        gamepad_thread.start()

    print("[Input Logger] Xbox-ready script loaded successfully.")

def script_unload():
    global keyboard_listener, mouse_listener, is_running
    
    is_running = False
    obs.obs_frontend_remove_event_callback(on_event)
    event_queue.put(("QUIT", None))
    
    if keyboard_listener:
        keyboard_listener.stop()
    if mouse_listener:
        mouse_listener.stop()
        
    print("[Input Logger] Script unloaded cleanly.")