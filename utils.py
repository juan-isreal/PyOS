import getpass
import hashlib
import importlib.util
import inspect
import json
import os
import re
import secrets
import shlex

DEFAULT_USER_FOLDERS = (
    "Desktop",
    "Documents",
    "Downloads",
    "Projects",
    os.path.join("usr", "bin"),
    os.path.join("usr", "local", "bin"),
)



def _format_filename(filename):
    filename = str(filename)
    if not filename.endswith(".json"):
        filename += ".json"
    return filename


def hash_password(password):
    iterations = secrets.randbelow(30_001) + 90_000
    salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return f"{iterations}:{salt}:{pw_hash}"


def verify_password(attempt, stored_value):
    try:
        iterations_str, salt, original_hash = stored_value.split(":")
        iterations = int(iterations_str)
    except ValueError:
        return False

    attempt_hash = hashlib.pbkdf2_hmac(
        "sha256", attempt.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return secrets.compare_digest(attempt_hash, original_hash)


def ensure_user_dirs(user_home, dirs=DEFAULT_USER_FOLDERS):
    if not os.path.isdir(user_home):
        os.makedirs(user_home)
    for folder in dirs:
        folder_path = os.path.join(user_home, folder)
        if not os.path.isdir(folder_path):
            os.makedirs(folder_path)


def split_chained_commands(raw_input):
    try:
        lexer = shlex.shlex(raw_input, posix=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = raw_input.split()

    commands = []
    current = []
    for token in tokens:
        if token == "&&":
            if current:
                commands.append(current)
                current = []
        else:
            current.append(token)
    if current:
        commands.append(current)
    return commands


def checkforfile(file, default_data=None):
    filepath = _format_filename(file)

    if os.path.exists(filepath):
        return True
    else:
        if default_data is None:
            default_data = []

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4)
        return False


def load_json(filename, default_data=None):
    filepath = _format_filename(filename)
    if default_data is None:
        default_data = {}

    if not os.path.exists(filepath):
        save_json(filepath, default_data)
        return default_data

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    filepath = _format_filename(filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def append_data(new_data, file):
    filepath = _format_filename(file)

    if not checkforfile(filepath, default_data=[new_data]):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        existing_data = json.load(f)

    existing_data.append(new_data)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=4)


def update(value, new_value, filename, data):
    filename = _format_filename(filename)
    data[f"{value}"] = new_value
    save_json(filename, data)


def valid_input(prompt, length=1, error="Invalid Input.\nPlease try again.", secret=False):
    while True:
        raw = getpass.getpass(prompt) if secret else input(prompt)
        value = raw.strip()
        if len(value) > int(length):
            return value
        print(str(error))


def scan_commands(commands_dir, context):
    valid_cmds = []
    coos_cmds = []

    if not os.path.isdir(commands_dir):
        context["COOS"] = []
        return valid_cmds

    for f in sorted(os.listdir(commands_dir)):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        if not os.path.isfile(os.path.join(commands_dir, f)):
            continue

        cmd_name = f.removesuffix(".py")

        if cmd_name.lower() == "coos":
            valid_cmds.append(cmd_name)
            continue

        if (
            "coos" in cmd_name.lower()
            or len(cmd_name.split()) > 1
            or not re.match(r"^[a-z0-9_-]+$", cmd_name)
        ):
            coos_cmds.append(cmd_name)
        else:
            valid_cmds.append(cmd_name)

    context["COOS"] = coos_cmds
    return valid_cmds


def run_command(raw_input, commands_dir, context):
    try:
        parts = shlex.split(raw_input.strip())
    except ValueError:
        parts = raw_input.strip().split()

    if not parts:
        return

    cmd_name = parts[0].lower()

    args = parts[1:]

    scan_commands(commands_dir, context)

    for coos_name in context.get("COOS", []):
        clean_coos = re.sub(r"coos", "", coos_name, flags=re.IGNORECASE).strip(" _-")
        if cmd_name == coos_name.lower() or (clean_coos and cmd_name == clean_coos.lower()):
            print(f"Command '{cmd_name}' is currently Out Of Service (COOS).")
            return

    if not re.match(r"^[a-z0-9_-]+$", cmd_name):
        print("Invalid command name.")
        return

    cmd_path = os.path.join(commands_dir, f"{cmd_name}.py")
    if not os.path.isfile(cmd_path):
        print(f"Command '{cmd_name}' not found. Type 'help' for a list of commands.")
        return

    try:
        spec = importlib.util.spec_from_file_location(cmd_name, cmd_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "run"):
            sig = inspect.signature(module.run)
            if len(sig.parameters) >= 2:
                result = module.run(args, context)
            else:
                result = module.run(args)

            if result is not None:
                print(result)
        else:
            print(f"Error: '{cmd_name}.py' is missing a run() function.")
    except Exception as e:
        print(f"Command '{cmd_name}' crashed: {e}")
