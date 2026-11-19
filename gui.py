import io
import os
import shlex
import sys
import threading
import tkinter as tk
import system_cmds
import tsdk
import utils

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_NAME = os.path.join(BASE_DIR, "data.json")
COMMANDS_DIR = os.path.join(BASE_DIR, "commands")
FILES_ROOT = os.path.join(BASE_DIR, "files", "users")

if not os.path.isdir(COMMANDS_DIR):
    os.makedirs(COMMANDS_DIR)
if not os.path.isdir(FILES_ROOT):
    os.makedirs(FILES_ROOT)


class MacOSTerminalApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Terminal — bash — 80x24")
        self.root.geometry("760x480")
        self.root.configure(bg="#1E1E1E")

        self.text = tk.Text(
            root,
            bg="#1E1E1E",
            fg="#F2F2F2",
            insertbackground="#FFFFFF",
            selectbackground="#4A4A4A",
            font=("Menlo", 13),
            borderwidth=0,
            highlightthickness=0,
            padx=12,
            pady=10,
            wrap="word",
        )
        self.text.pack(fill="both", expand=True)

        self.input_start = "1.0"
        self.secret_mode = False
        self.secret_buffer = ""
        self.history = []
        self.history_index = 0

        self.waiting_for_sdk_input = False
        self.sdk_input_event = threading.Event()
        self.sdk_input_value = ""
        self.command_running = False

        self.state = "SHELL"
        self.temp_username = ""
        self.login_attempts = 0
        self.data = utils.load_json(FILE_NAME, default_data={})
        self.safe_context = None

        tsdk._gui_print = lambda text: self.root.after(0, lambda: self.write(text))
        tsdk._gui_ask = self.gui_ask_from_thread
        tsdk._gui_clear = lambda: self.root.after(0, self.clear_screen)

        self.text.bind("<Return>", self.on_enter)
        self.text.bind("<BackSpace>", self.on_backspace)
        self.text.bind("<Left>", self.on_left)
        self.text.bind("<Home>", self.on_home)
        self.text.bind("<Up>", self.on_history_up)
        self.text.bind("<Down>", self.on_history_down)
        self.text.bind("<Key>", self.on_key)
        self.text.bind("<Button-1>", self.on_click)

        self.boot()

    def gui_ask_from_thread(self, prompt="", secret=False):
        self.sdk_input_event.clear()

        def _setup_prompt():
            self.waiting_for_sdk_input = True
            self.prompt_user(prompt, secret=secret)

        self.root.after(0, _setup_prompt)
        self.sdk_input_event.wait()
        return self.sdk_input_value

    def write(self, msg=""):
        self.text.insert("end", str(msg))
        self.text.see("end")
        self.input_start = self.text.index("end-1c")

    def clear_screen(self):
        self.text.delete("1.0", "end")
        self.input_start = "1.0"

    def boot(self):
        self.write("Last login: Today on ttys000\n")
        if len(self.data.get("username") or "") <= 1 or not self.data.get("password_hash"):
            self.state = "SETUP_USER"
            self.prompt_user("Create Username: ", secret=False)
        elif not self.data.get("is_logged_in", False):
            self.state = "LOGIN_USER"
            self.prompt_user("Username: ", secret=False)
        else:
            self.start_shell()

    def prompt_user(self, label, secret=False):
        self.secret_mode = secret
        self.secret_buffer = ""
        self.write(label)
        self.text.focus_set()

    def start_shell(self):
        self.state = "SHELL"
        self.secret_mode = False
        user_home = os.path.join(FILES_ROOT, self.data["username"])
        utils.ensure_user_dirs(user_home)

        def change_password(old_pass, new_pass):
            if not utils.verify_password(old_pass, self.data["password_hash"]):
                return False, "Error: Current password is incorrect."
            if len(new_pass.strip()) <= 1:
                return False, "Error: New password must be more than 1 character."
            utils.update("password_hash", utils.hash_password(new_pass), FILE_NAME, self.data)
            return True, "Password successfully updated!"

        self.safe_context = {
            "username": self.data["username"],
            "commands_dir": COMMANDS_DIR,
            "home_dir": user_home,
            "cwd": user_home,
            "COOS": [],
            "verify_password": lambda attempt: utils.verify_password(
                attempt, self.data["password_hash"]
            ),
            "change_password": change_password,
            "utils": {
                "scan_commands": utils.scan_commands,
                "valid_input": utils.valid_input,
                "ensure_user_dirs": utils.ensure_user_dirs,
            },
        }
        utils.scan_commands(COMMANDS_DIR, self.safe_context)
        self.show_shell_prompt()

    def show_shell_prompt(self):
        rel_path = os.path.relpath(self.safe_context["cwd"], self.safe_context["home_dir"])
        prompt_path = "~" if rel_path == "." else f"~/{rel_path}"
        self.root.title(f"{self.data['username']} — {prompt_path} — TOS")
        self.prompt_user(f"{self.data['username']}:{prompt_path} $ ", secret=False)
    def on_click(self, event):
        self.root.after(1, lambda: self.text.mark_set("insert", "end"))

    def on_left(self, event):
        if self.text.compare("insert", "<=", self.input_start):
            return "break"

    def on_home(self, event):
        self.text.mark_set("insert", self.input_start)
        return "break"

    def on_backspace(self, event):
        if self.text.compare("insert", "<=", self.input_start):
            return "break"
        if self.secret_mode and self.secret_buffer:
            self.secret_buffer = self.secret_buffer[:-1]

    def on_key(self, event):
        if event.state & 0x4 or event.state & 0x8:
            return
        if self.text.compare("insert", "<", self.input_start):
            self.text.mark_set("insert", "end")
        if self.secret_mode and event.char and event.char.isprintable():
            self.secret_buffer += event.char
            self.text.insert("end", "*")
            return "break"

    def on_history_up(self, event):
        if self.state != "SHELL" or self.command_running or not self.history:
            return "break"
        self.history_index = max(0, self.history_index - 1)
        self.text.delete(self.input_start, "end")
        self.text.insert("end", self.history[self.history_index])
        return "break"

    def on_history_down(self, event):
        if self.state != "SHELL" or self.command_running or not self.history:
            return "break"
        self.history_index = min(len(self.history), self.history_index + 1)
        self.text.delete(self.input_start, "end")
        if self.history_index < len(self.history):
            self.text.insert("end", self.history[self.history_index])
        return "break"

    def on_enter(self, event):
        if self.secret_mode:
            raw = self.secret_buffer
        else:
            raw = self.text.get(self.input_start, "end-1c")

        self.text.insert("end", "\n")
        self.text.see("end")
        self.secret_mode = False
        self.secret_buffer = ""

        if self.waiting_for_sdk_input:
            self.waiting_for_sdk_input = False
            self.sdk_input_value = raw
            self.sdk_input_event.set()
            return "break"

        if not self.command_running:
            self.handle_input(raw.strip())
        return "break"

    def handle_input(self, raw):
        if self.state == "SETUP_USER":
            if len(raw) <= 1:
                self.write("Invalid Username. Must be more than 1 character.\n")
                self.prompt_user("Create Username: ")
            else:
                self.temp_username = raw
                self.state = "SETUP_PASS"
                self.prompt_user("Create Password: ", secret=True)

        elif self.state == "SETUP_PASS":
            if len(raw) <= 1:
                self.write("Invalid Password. Must be more than 1 character.\n")
                self.prompt_user("Create Password: ", secret=True)
            else:
                self.data = {
                    "username": self.temp_username,
                    "password_hash": utils.hash_password(raw),
                    "is_logged_in": True,
                }
                utils.save_json(FILE_NAME, self.data)
                self.start_shell()

        elif self.state == "LOGIN_USER":
            self.temp_username = raw
            self.state = "LOGIN_PASS"
            self.prompt_user("Password: ", secret=True)

        elif self.state == "LOGIN_PASS":
            if self.temp_username == self.data["username"] and utils.verify_password(
                raw, self.data["password_hash"]
            ):
                utils.update("is_logged_in", True, FILE_NAME, self.data)
                self.write("Login successful!\n")
                self.start_shell()
            else:
                self.login_attempts += 1
                if self.login_attempts >= 3:
                    self.write("Too many failed attempts. Closing...\n")
                    self.root.after(1000, self.root.destroy)
                else:
                    self.write("Invalid credentials. Try again.\n")
                    self.state = "LOGIN_USER"
                    self.prompt_user("Username: ")

        elif self.state == "SHELL":
            if not raw:
                self.show_shell_prompt()
                return

            self.history.append(raw)
            self.history_index = len(self.history)
            self.command_running = True

            threading.Thread(
                target=self._run_chained_worker, args=(raw,), daemon=True
            ).start()

    def _run_chained_worker(self, raw):
        chained = utils.split_chained_commands(raw)
        for parts in chained:
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit"):
                self.root.after(0, self.root.destroy)
                return

            elif cmd == "logout":
                utils.update("is_logged_in", False, FILE_NAME, self.data)
                self.root.after(0, lambda: self.write("Logged out.\n"))
                self.login_attempts = 0
                self.state = "LOGIN_USER"
                self.command_running = False
                self.root.after(0, lambda: self.prompt_user("Username: "))
                return

            elif cmd == "clear":
                self.root.after(0, self.clear_screen)
                continue

            buffer = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buffer
            try:
                if not system_cmds.handle_system_command(cmd, args, self.safe_context):
                    rebuilt_cmd = " ".join(shlex.quote(p) for p in parts)
                    utils.run_command(rebuilt_cmd, COMMANDS_DIR, self.safe_context)
            finally:
                sys.stdout = old_stdout

            output = buffer.getvalue()
            if output:
                text_to_write = output if output.endswith("\n") else output + "\n"
                self.root.after(0, lambda t=text_to_write: self.write(t))

        self.command_running = False
        self.root.after(0, self.show_shell_prompt)


if __name__ == "__main__":
    root = tk.Tk()
    app = MacOSTerminalApp(root)
    root.mainloop()
