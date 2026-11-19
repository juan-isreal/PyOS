import fcntl
import io
import os
import pty
import re
import select
import shlex
import signal
import struct
import subprocess
import sys
import termios
import threading
import tkinter as tk
import system_cmds
import tsdk
import utils

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_NAME = os.path.join(BASE_DIR, "data.json")
COMMANDS_DIR = os.path.join(BASE_DIR, "commands")
FILES_ROOT = os.path.join(BASE_DIR, "files", "users")
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")

os.makedirs(COMMANDS_DIR, exist_ok=True)
os.makedirs(FILES_ROOT, exist_ok=True)

ANSI_RE = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")
OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

ANSI_COLORS = {
    "30": "#4E4E4E", "31": "#FF5F56", "32": "#27C93F", "33": "#FFBD2E",
    "34": "#57A6FF", "35": "#D28BFF", "36": "#56D4DD", "37": "#F2F2F2",
    "90": "#808080", "91": "#FF6E67", "92": "#5AF78E", "93": "#F4F99D",
    "94": "#CAA9FA", "95": "#FF92D0", "96": "#9AEDFE", "97": "#FFFFFF",
}


def _read_version():
    if os.path.isfile(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            ver = f.read().strip()
            if ver:
                return f"v{ver}" if not ver.startswith("v") else ver
    return "v0.1.0-beta.1"


class MacOSTerminalApp:
    def __init__(self, root):
        self.root = root
        self.version = _read_version()
        self.root.title(f"PyOS Terminal ({self.version})")
        self.root.geometry("820x520")
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

        self.active_fg_tag = None
        self.active_bold = False
        self.text.tag_configure("ansi_bold", font=("Menlo", 13, "bold"))
        for code, hex_col in ANSI_COLORS.items():
            self.text.tag_configure(f"ansi_{code}", foreground=hex_col)

        self.input_start = "1.0"
        self.secret_mode = False
        self.secret_buffer = ""
        self.history = []
        self.history_index = 0

        self.waiting_for_sdk_input = False
        self.sdk_input_event = threading.Event()
        self.sdk_input_value = ""
        self.command_running = False

        self.pty_master_fd = None
        self.pty_proc = None

        self.state = "SHELL"
        self.temp_username = ""
        self.login_attempts = 0
        self.data = utils.load_json(FILE_NAME, default_data={})
        self.safe_context = None

        tsdk._gui_print = lambda text: self.root.after(0, lambda t=text: self.write_ansi(t))
        tsdk._gui_ask = self.gui_ask_from_thread
        tsdk._gui_clear = lambda: self.root.after(0, self.clear_screen)
        tsdk._gui_run_on_ui = lambda fn: self.root.after(0, fn)
        tsdk._gui_get_root = lambda: self.root
        tsdk._gui_hide_term = self.text.pack_forget
        tsdk._gui_show_term = lambda: (
            self.text.pack(fill="both", expand=True),
            self.text.focus_set(),
        )

        self.text.bind("<Return>", self.on_enter)
        self.text.bind("<BackSpace>", self.on_backspace)
        self.text.bind("<Left>", self.on_left)
        self.text.bind("<Right>", self.on_right)
        self.text.bind("<Home>", self.on_home)
        self.text.bind("<Up>", self.on_history_up)
        self.text.bind("<Down>", self.on_history_down)
        self.text.bind("<Control-c>", self.on_ctrl_c)
        self.text.bind("<Control-d>", self.on_ctrl_d)
        self.text.bind("<Key>", self.on_key)
        self.text.bind("<Button-1>", self.on_click)

        self.boot()

    def write(self, msg=""):
        self.text.insert("end", str(msg))
        self.text.see("end")
        self.input_start = self.text.index("end-1c")

    def write_ansi(self, raw_text):
        cleaned = OSC_RE.sub("", str(raw_text)).replace("\r\n", "\n")
        pos = 0
        for match in ANSI_RE.finditer(cleaned):
            chunk = cleaned[pos:match.start()]
            if chunk:
                self._insert_styled_chunk(chunk)
            params, cmd_char = match.group(1), match.group(2)
            if cmd_char == "m":
                for p in (params.split(";") if params else ["0"]):
                    if p == "0" or p == "":
                        self.active_fg_tag = None
                        self.active_bold = False
                    elif p == "1":
                        self.active_bold = True
                    elif p in ANSI_COLORS:
                        self.active_fg_tag = f"ansi_{p}"
            elif cmd_char == "J" and params in ("2", "3"):
                self.clear_screen()
            pos = match.end()

        tail = cleaned[pos:]
        if tail:
            self._insert_styled_chunk(tail)

        self.text.see("end")
        self.input_start = self.text.index("end-1c")

    def _insert_styled_chunk(self, chunk):
        for ch in chunk:
            if ch == "\b":
                if self.text.compare("end-1c", ">", "1.0"):
                    self.text.delete("end-2c", "end-1c")
            elif ch == "\r":
                line_start = self.text.index("end-1c linestart")
                self.text.delete(line_start, "end-1c")
            else:
                tags = []
                if self.active_fg_tag:
                    tags.append(self.active_fg_tag)
                if self.active_bold:
                    tags.append("ansi_bold")
                self.text.insert("end", ch, tuple(tags))

    def clear_screen(self):
        self.text.delete("1.0", "end")
        self.input_start = "1.0"

    def gui_ask_from_thread(self, prompt="", secret=False):
        self.sdk_input_event.clear()

        def _setup_prompt():
            self.waiting_for_sdk_input = True
            self.prompt_user(prompt, secret=secret)

        self.root.after(0, _setup_prompt)
        self.sdk_input_event.wait()
        return self.sdk_input_value

    def boot(self):
        self.write(f"PyOS {self.version} — Ready on ttys000\n")
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

        usr_local_bin = os.path.join(user_home, "usr", "local", "bin")
        usr_bin = os.path.join(user_home, "usr", "bin")
        os.makedirs(usr_local_bin, exist_ok=True)
        os.makedirs(usr_bin, exist_ok=True)

        saved_path = utils.load_json(
            os.path.join(usr_bin, ".path.json"),
            default_data=[usr_local_bin, usr_bin, COMMANDS_DIR],
        )

        def change_password(old_pass, new_pass):
            if not utils.verify_password(old_pass, self.data["password_hash"]):
                return False, "Error: Current password is incorrect."
            if len(new_pass.strip()) <= 1:
                return False, "Error: New password must be more than 1 character."
            utils.update("password_hash", utils.hash_password(new_pass), FILE_NAME, self.data)
            return True, "Password successfully updated!"

        self.safe_context = {
            "username": self.data["username"],
            "version": self.version,
            "commands_dir": COMMANDS_DIR,
            "home_dir": user_home,
            "cwd": user_home,
            "PATH": saved_path,
            "COOS": [],
            "pty_exec": self.run_in_pty,
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
        utils.scan_commands(self.safe_context["PATH"], self.safe_context)
        self.show_shell_prompt()

    def show_shell_prompt(self):
        rel_path = os.path.relpath(self.safe_context["cwd"], self.safe_context["home_dir"])
        prompt_path = "~" if rel_path == "." else f"~/{rel_path}"
        self.root.title(f"{self.data['username']} - {prompt_path} - PyOS {self.version}")
        self.prompt_user(f"{self.data['username']}:{prompt_path} $ ", secret=False)
    def run_in_pty(self, cmd_list, cwd=None):
        """Execute any command inside a real POSIX PTY with live streaming & keyboard input."""
        master_fd, slave_fd = pty.openpty()
        winsize = struct.pack("HHHH", 28, 96, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"

        proc = subprocess.Popen(
            cmd_list,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd or self.safe_context["cwd"],
            env=env,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)
        self.pty_master_fd = master_fd
        self.pty_proc = proc

        try:
            while True:
                rlist, _, _ = select.select([master_fd], [], [], 0.05)
                if master_fd in rlist:
                    try:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        text_out = data.decode("utf-8", errors="replace")
                        self.root.after(0, lambda t=text_out: self.write_ansi(t))
                    except OSError:
                        break
                if proc.poll() is not None:
                    while True:
                        r2, _, _ = select.select([master_fd], [], [], 0.01)
                        if master_fd not in r2:
                            break
                        try:
                            rem = os.read(master_fd, 4096)
                            if not rem:
                                break
                            text_out = rem.decode("utf-8", errors="replace")
                            self.root.after(0, lambda t=text_out: self.write_ansi(t))
                        except OSError:
                            break
                    break
        finally:
            self.pty_master_fd = None
            self.pty_proc = None
            try:
                os.close(master_fd)
            except OSError:
                pass

    def _send_pty(self, raw_bytes):
        if self.pty_master_fd is not None:
            try:
                os.write(self.pty_master_fd, raw_bytes)
            except OSError:
                pass

    def on_ctrl_c(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\x03")
            return "break"

    def on_ctrl_d(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\x04")
            return "break"

    def on_click(self, event):
        self.root.after(1, lambda: self.text.mark_set("insert", "end"))

    def on_left(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\x1b[D")
            return "break"
        if self.text.compare("insert", "<=", self.input_start):
            return "break"

    def on_right(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\x1b[C")
            return "break"

    def on_home(self, event):
        self.text.mark_set("insert", self.input_start)
        return "break"

    def on_backspace(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\x7f")
            return "break"
        if self.text.compare("insert", "<=", self.input_start):
            return "break"
        if self.secret_mode and self.secret_buffer:
            self.secret_buffer = self.secret_buffer[:-1]

    def on_key(self, event):
        if self.pty_master_fd is not None:
            if event.char:
                self._send_pty(event.char.encode("utf-8"))
            return "break"

        if event.state & 0x4 or event.state & 0x8:
            return
        if self.text.compare("insert", "<", self.input_start):
            self.text.mark_set("insert", "end")
        if self.secret_mode and event.char and event.char.isprintable():
            self.secret_buffer += event.char
            self.text.insert("end", "*")
            return "break"

    def on_history_up(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\x1b[A")
            return "break"
        if self.state != "SHELL" or self.command_running or not self.history:
            return "break"
        self.history_index = max(0, self.history_index - 1)
        self.text.delete(self.input_start, "end")
        self.text.insert("end", self.history[self.history_index])
        return "break"

    def on_history_down(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\x1b[B")
            return "break"
        if self.state != "SHELL" or self.command_running or not self.history:
            return "break"
        self.history_index = min(len(self.history), self.history_index + 1)
        self.text.delete(self.input_start, "end")
        if self.history_index < len(self.history):
            self.text.insert("end", self.history[self.history_index])
        return "break"

    def on_enter(self, event):
        if self.pty_master_fd is not None:
            self._send_pty(b"\r")
            return "break"

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
            cmd = next(iter(parts)).lower()
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

            # Allow direct interactive PTY execution with 'pty <cmd> [args...]'
            if cmd == "pty" and args:
                self.run_in_pty(args, cwd=self.safe_context["cwd"])
                continue

            buffer = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buffer
            try:
                if not system_cmds.handle_system_command(cmd, args, self.safe_context):
                    rebuilt_cmd = " ".join(shlex.quote(p) for p in parts)
                    utils.run_command(rebuilt_cmd, self.safe_context["PATH"], self.safe_context)
            finally:
                sys.stdout = old_stdout

            output = buffer.getvalue()
            if output:
                text_to_write = output if output.endswith("\n") else output + "\n"
                self.root.after(0, lambda t=text_to_write: self.write_ansi(t))

        self.command_running = False
        self.root.after(0, self.show_shell_prompt)


if __name__ == "__main__":
    root = tk.Tk()
    app = MacOSTerminalApp(root)
    root.mainloop()