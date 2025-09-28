import customtkinter as ctk
import pyautogui
import threading
import time
from pynput import keyboard
from tkinter import messagebox

class AutoTyperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Initialize variables
        self.stop_typing_flag = False
        self.typing_thread = None
        self.current_hotkey = set()
        self.pressed_keys = set()
        self.registering_hotkey = False
        self.thread_lock = threading.Lock()
        self.time_lock = threading.Lock()
        self.dark_mode = True
        self.typing_start_time = None
        self.typing_total_time = 0

        # Configure appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Configure window
        self.title("Modern Auto Typer")
        self.geometry("600x700")
        self.caps_mode_var = ctk.StringVar(value="as_is")

        # Create widgets
        self.create_widgets()

        # Setup key listener
        self.setup_key_listener()

    def create_widgets(self):
        # Title
        title_label = ctk.CTkLabel(self, text="Auto Typer", font=("Arial", 24, "bold"))
        title_label.pack(pady=10)

        # Text input
        self.text_input = ctk.CTkTextbox(self, width=500, height=150, font=("Arial", 14))
        self.text_input.pack(pady=10)

        # Timer label
        self.timer_label = ctk.CTkLabel(self, text="Total Typing Time: 0.00 seconds", font=("Arial", 14))
        self.timer_label.pack(pady=5)

        # Speed and delay
        self.speed_entry = ctk.CTkEntry(self, placeholder_text="Typing Speed (ms/char)", width=200)
        self.speed_entry.pack(pady=5)
        self.delay_entry = ctk.CTkEntry(self, placeholder_text="Delay Between Words (ms)", width=200)
        self.delay_entry.pack(pady=5)

        # Hotkey display and registration
        self.hotkey_display = ctk.CTkLabel(self, text="Hotkey: Not Set", font=("Arial", 14))
        self.hotkey_display.pack(pady=5)
        register_button = ctk.CTkButton(self, text="Register Hotkey", command=self.register_hotkey)
        register_button.pack(pady=10)

        # Caps mode radio buttons
        caps_frame = ctk.CTkFrame(self)
        caps_frame.pack(pady=10, fill="x")
        caps_label = ctk.CTkLabel(caps_frame, text="Caps Lock Mode:", font=("Arial", 14))
        caps_label.grid(row=0, column=0, padx=5)

        caps_as_is = ctk.CTkRadioButton(caps_frame, text="Type As It Is", value="as_is", variable=self.caps_mode_var)
        caps_as_is.grid(row=0, column=1, padx=5)
        caps_upper = ctk.CTkRadioButton(caps_frame, text="Type All Capital", value="uppercase", variable=self.caps_mode_var)
        caps_upper.grid(row=0, column=2, padx=5)
        caps_sentence = ctk.CTkRadioButton(caps_frame, text="Sentence Case", value="sentence_case", variable=self.caps_mode_var)
        caps_sentence.grid(row=0, column=3, padx=5)
        caps_lower = ctk.CTkRadioButton(caps_frame, text="Lower Case", value="lowercase", variable=self.caps_mode_var)
        caps_lower.grid(row=0, column=4, padx=5)
        caps_as_is.select()

        # Start and stop buttons
        start_button = ctk.CTkButton(self, text="Start Typing", command=self.start_typing, fg_color="green")
        start_button.pack(pady=10)
        stop_button = ctk.CTkButton(self, text="Stop Typing", command=self.stop_typing, fg_color="red")
        stop_button.pack(pady=10)

        # Dark/light mode button
        self.mode_button = ctk.CTkButton(self, text="Switch to Light Mode", command=self.toggle_mode)
        self.mode_button.pack(pady=10)

    def parse_special_keys(self, text):
        return text.replace("{Enter}", "\n").replace("{Tab}", "\t")

    def apply_caps_mode(self, text, mode):
        if mode == "uppercase":
            return text.upper()
        elif mode == "lowercase":
            return text.lower()
        elif mode == "sentence_case":
            return text.capitalize()
        return text

    def auto_type(self, text, speed_ms, delay_ms):
        text = self.parse_special_keys(self.apply_caps_mode(text, self.caps_mode_var.get()))

        with self.time_lock:
            self.typing_start_time = time.time()
            self.typing_total_time = 0  # Reset total time

        for char in text:
            if self.stop_typing_flag:
                break
            pyautogui.write(char)
            time.sleep(speed_ms / 1000.0)

        if not self.stop_typing_flag:
            time.sleep(delay_ms / 1000.0)

        with self.time_lock:
            if self.typing_start_time:
                self.typing_total_time = time.time() - self.typing_start_time
            self.typing_start_time = None

        with self.thread_lock:
            self.typing_thread = None

        if not self.stop_typing_flag:
            self.after(0, self.show_completion_message)

    def start_typing(self):
        with self.thread_lock:
            if self.typing_thread is not None:
                return

            self.stop_typing_flag = False
            text = self.text_input.get("1.0", "end").strip()
            try:
                speed_ms = int(self.speed_entry.get())
                delay_ms = int(self.delay_entry.get())
            except ValueError:
                return
            if not text:
                return

            self.typing_thread = threading.Thread(target=self.auto_type, args=(text, speed_ms, delay_ms), daemon=True)
            self.typing_thread.start()
            self.update_timer()

    def stop_typing(self):
        self.stop_typing_flag = True
        with self.thread_lock:
            if self.typing_thread is not None:
                self.typing_thread.join(timeout=1)
                self.typing_thread = None

    def show_completion_message(self):
        messagebox.showinfo("Typing Complete", f"Typing session completed successfully.\nElapsed Time: {self.typing_total_time:.2f} seconds")

    def update_timer(self):
        if self.typing_start_time:
            elapsed = time.time() - self.typing_start_time + self.typing_total_time
            self.timer_label.configure(text=f"Total Typing Time: {elapsed:.2f} seconds")
            self.after(100, self.update_timer)  # Continue updating
        else:
            self.timer_label.configure(text=f"Total Typing Time: {self.typing_total_time:.2f} seconds")

    def register_hotkey(self):
        self.registering_hotkey = True
        self.current_hotkey.clear()
        self.hotkey_display.configure(text="Press keys for hotkey...")

    def on_press(self, key):
        if self.registering_hotkey:
            self.current_hotkey.add(key)
            self.hotkey_display.configure(text=f"Hotkey Registered: {self.hotkey_to_string(self.current_hotkey)}")
            self.registering_hotkey = False
            return

        self.pressed_keys.add(key)
        if self.pressed_keys == self.current_hotkey:
            self.start_typing()

    def on_release(self, key):
        if key in self.pressed_keys:
            self.pressed_keys.remove(key)
        if key == keyboard.Key.esc:
            self.stop_typing()

    def hotkey_to_string(self, hotkey):
        return "+".join([str(k).replace("Key.", "").capitalize() for k in hotkey])

    def setup_key_listener(self):
        listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        listener.daemon = True
        listener.start()

    def toggle_mode(self):
        self.dark_mode = not self.dark_mode
        mode = "dark" if self.dark_mode else "light"
        ctk.set_appearance_mode(mode)
        self.mode_button.configure(text=f"Switch to {'Light' if self.dark_mode else 'Dark'} Mode")

if __name__ == "__main__":
    app = AutoTyperApp()
    app.mainloop()