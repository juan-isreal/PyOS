import getpass
import json
import os
import time

_gui_ask = None
_gui_print = None
_gui_clear = None


# --- Input & Output ---
def out(msg="", end="\n"):
    """Print output safely to both main.py and gui.py."""
    text = f"{msg}{end}"
    if _gui_print:
        _gui_print(text)
    else:
        print(msg, end=end)


def ask(prompt="", secret=False):
    """Prompt for user input safely in both main.py and gui.py."""
    if _gui_ask:
        return _gui_ask(prompt, secret=secret)
    if secret:
        return getpass.getpass(prompt)
    return input(prompt)


def confirm(prompt="Are you sure? (y/n): "):
    """Ask a quick yes/no question and return True or False."""
    ans = ask(prompt).strip().lower()
    return ans in ("y", "yes")


def clear():
    """Clear the terminal screen in both main.py and gui.py."""
    if _gui_clear:
        _gui_clear()
    else:
        os.system("cls" if os.name == "nt" else "clear")


def banner(title):
    """Print a clean formatted header box for apps."""
    line = "=" * (len(title) + 8)
    out(f"\n{line}\n=== {title} ===\n{line}")


def pause(seconds=1):
    """Pause execution cleanly."""
    time.sleep(seconds)


# --- Sandboxed File & Path Helpers ---
def resolve_path(target, context):
    """Safely resolve a path inside the user's ~/ sandbox. Returns None if outside ~/."""
    home_dir = context["home_dir"]
    current_dir = context["cwd"]

    if not target or target == "~":
        return home_dir
    if target.startswith("~/"):
        resolved = os.path.abspath(os.path.join(home_dir, target[2:]))
    else:
        resolved = os.path.abspath(os.path.join(current_dir, target))

    if os.path.commonpath([home_dir, resolved]) != home_dir:
        return None
    return resolved


def read_file(target, context):
    """Read and return text from a sandboxed file, or None if missing/invalid."""
    path = resolve_path(target, context)
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(target, content, context):
    """Write text to a sandboxed file. Returns True on success, False if invalid path."""
    path = resolve_path(target, context)
    if not path:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def list_dir(target, context):
    """Return a sorted list of items inside a sandboxed folder."""
    path = resolve_path(target, context)
    if not path or not os.path.isdir(path):
        return []
    return sorted(os.listdir(path))


# --- App Data & Security Helpers ---
def app_data_path(app_name, context):
    """Get a dedicated JSON file path inside ~/.appdata/ for saving app settings/saves."""
    app_dir = os.path.join(context["home_dir"], ".appdata")
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, f"{app_name}.json")


def load_app_data(app_name, context, default=None):
    """Load saved JSON data for a specific command/app."""
    if default is None:
        default = {}
    path = app_data_path(app_name, context)
    if not os.path.isfile(path):
        save_app_data(app_name, context, default)
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_app_data(app_name, context, data):
    """Save JSON data for a specific command/app."""
    path = app_data_path(app_name, context)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def verify_user(context, prompt="Confirm password: "):
    """Prompt for the user's password and verify it against their PBKDF2 hash."""
    pw = ask(prompt, secret=True)
    return context["verify_password"](pw)
