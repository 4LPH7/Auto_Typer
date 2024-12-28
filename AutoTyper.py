import customtkinter as ctk
import pyautogui
import threading
import time
from pynput import keyboard
from tkinter import messagebox


# Global variables
stop_typing_flag = False
typing_thread = None
current_hotkey = set()
pressed_keys = set()
registering_hotkey = False
thread_lock = threading.Lock()  # Lock for managing thread safety
dark_mode = True  # Default appearance mode
typing_start_time = None  # Timer start time
typing_total_time = 0  # Total elapsed time

# Parse special keys
def parse_special_keys(text):
    text = text.replace("{Enter}", "\n")
    text = text.replace("{Tab}", "\t")
    return text

# Apply caps mode
def apply_caps_mode(text, mode):
    if mode == "uppercase":
        return text.upper()
    elif mode == "lowercase":
        return text.lower()
    elif mode == "sentence_case":
        return text.capitalize()
    return text  # Default: as_is

# Auto typing function
def auto_type(text, speed_ms, delay_ms):
    global stop_typing_flag, typing_thread, typing_start_time, typing_total_time

    text = parse_special_keys(apply_caps_mode(text, caps_mode_var.get()))
    typing_start_time = time.time()  # Start the timer

    for char in text:
        if stop_typing_flag:
            break
        pyautogui.write(char)
        time.sleep(speed_ms / 1000.0)  # Convert ms to seconds
    time.sleep(delay_ms / 1000.0)

    typing_total_time = time.time() - typing_start_time  # Calculate elapsed time
    typing_start_time = None

    with thread_lock:
        typing_thread = None  # Clear the thread reference when typing is done

    # Show popup with elapsed time
    messagebox.showinfo("Typing Complete", f"Typing session completed successfully.\nElapsed Time: {typing_total_time:.2f} seconds")


# Start typing
def start_typing():
    global stop_typing_flag, typing_thread

    with thread_lock:
        if typing_thread is not None:
            return

        stop_typing_flag = False
        text = text_input.get("1.0", "end").strip()
        try:
            speed_ms = int(speed_entry.get())
            delay_ms = int(delay_entry.get())
        except ValueError:
            return
        if not text:
            return

        typing_thread = threading.Thread(target=auto_type, args=(text, speed_ms, delay_ms), daemon=True)
        typing_thread.start()

# Stop typing
def stop_typing():
    global stop_typing_flag, typing_thread, typing_start_time, typing_total_time

    stop_typing_flag = True
    with thread_lock:
        if typing_thread is not None:
            typing_thread.join(timeout=1)  # Wait for the thread to terminate
            typing_thread = None

    # Reset the timer if typing is stopped
    typing_total_time += time.time() - typing_start_time if typing_start_time else 0
    typing_start_time = None

# Update timer display
def update_timer():
    global typing_start_time, typing_total_time
    if typing_start_time:
        elapsed = time.time() - typing_start_time + typing_total_time
        timer_label.configure(text=f"Total Typing Time: {elapsed:.2f} seconds")
    else:
        timer_label.configure(text=f"Total Typing Time: {typing_total_time:.2f} seconds")
    app.after(100, update_timer)

# Register a hotkey
def register_hotkey():
    global registering_hotkey, current_hotkey
    registering_hotkey = True
    current_hotkey.clear()
    hotkey_display.configure(text="Press keys for hotkey...")

# Handle key press
def on_press(key):
    global pressed_keys, registering_hotkey, current_hotkey

    if registering_hotkey:
        current_hotkey.add(key)
        hotkey_display.configure(text=f"Hotkey Registered: {hotkey_to_string(current_hotkey)}")
        registering_hotkey = False
        return

    pressed_keys.add(key)
    if pressed_keys == current_hotkey:
        start_typing()

# Handle key release
def on_release(key):
    global stop_typing_flag

    if key in pressed_keys:
        pressed_keys.remove(key)

    # Stop typing when ESC is released
    if key == keyboard.Key.esc:
        stop_typing()

# Convert hotkey to string
def hotkey_to_string(hotkey):
    return "+".join([str(k).replace("Key.", "").capitalize() for k in hotkey])

# Setup key listener
def setup_key_listener():
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()

# Toggle dark/light mode
def toggle_mode():
    global dark_mode
    dark_mode = not dark_mode
    mode = "dark" if dark_mode else "light"
    ctk.set_appearance_mode(mode)
    mode_button.configure(text=f"Switch to {'Light' if dark_mode else 'Dark'} Mode")

# GUI setup
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
caps_mode_var = ctk.StringVar(value="as_is")  # Default caps mode after root window initialization

app.title("Modern Auto Typer")
app.geometry("600x700")

# Title
title_label = ctk.CTkLabel(app, text="Auto Typer", font=("Arial", 24, "bold"))
title_label.pack(pady=10)

# Text input
text_input = ctk.CTkTextbox(app, width=500, height=150, font=("Arial", 14))
text_input.pack(pady=10)

# Timer label
timer_label = ctk.CTkLabel(app, text="Total Typing Time: 0.00 seconds", font=("Arial", 14))
timer_label.pack(pady=5)

# Speed and delay
speed_entry = ctk.CTkEntry(app, placeholder_text="Typing Speed (ms/char)", width=200)
speed_entry.pack(pady=5)
delay_entry = ctk.CTkEntry(app, placeholder_text="Delay Between Words (ms)", width=200)
delay_entry.pack(pady=5)

# Hotkey display and registration
hotkey_display = ctk.CTkLabel(app, text="Hotkey: Not Set", font=("Arial", 14))
hotkey_display.pack(pady=5)
register_button = ctk.CTkButton(app, text="Register Hotkey", command=register_hotkey)
register_button.pack(pady=10)

# Caps mode radio buttons (horizontally aligned)
caps_frame = ctk.CTkFrame(app)
caps_frame.pack(pady=10, fill="x")
caps_label = ctk.CTkLabel(caps_frame, text="Caps Lock Mode:", font=("Arial", 14))
caps_label.grid(row=0, column=0, padx=5)

caps_as_is = ctk.CTkRadioButton(
    caps_frame, text="Type As It Is", value="as_is", variable=caps_mode_var
)
caps_as_is.grid(row=0, column=1, padx=5)

caps_upper = ctk.CTkRadioButton(
    caps_frame, text="Type All Capital", value="uppercase", variable=caps_mode_var
)
caps_upper.grid(row=0, column=2, padx=5)

caps_sentence = ctk.CTkRadioButton(
    caps_frame, text="Sentence Case", value="sentence_case", variable=caps_mode_var
)
caps_sentence.grid(row=0, column=3, padx=5)

caps_lower = ctk.CTkRadioButton(
    caps_frame, text="Lower Case", value="lowercase", variable=caps_mode_var
)
caps_lower.grid(row=0, column=4, padx=5)

# Ensure default selection
caps_as_is.select()

# Start and stop buttons
start_button = ctk.CTkButton(app, text="Start Typing", command=start_typing, fg_color="green")
start_button.pack(pady=10)
stop_button = ctk.CTkButton(app, text="Stop Typing", command=stop_typing, fg_color="red")
stop_button.pack(pady=10)

# Dark/light mode button
mode_button = ctk.CTkButton(app, text="Switch to Light Mode", command=toggle_mode)
mode_button.pack(pady=10)

# Update timer
update_timer()

# Setup key listener
setup_key_listener()
app.mainloop()
