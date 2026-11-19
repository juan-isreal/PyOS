import getpass
import os
import shlex
import system_cmds
import utils

try:
    import readline
except ImportError:
    readline = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_NAME = os.path.join(BASE_DIR, "data.json")
COMMANDS_DIR = os.path.join(BASE_DIR, "commands")
FILES_ROOT = os.path.join(BASE_DIR, "files", "users")

os.makedirs(COMMANDS_DIR, exist_ok=True)
os.makedirs(FILES_ROOT, exist_ok=True)

data = utils.load_json(FILE_NAME, default_data={})

if len(data.get("username") or "") <= 1 or not data.get("password_hash"):
    username = utils.valid_input(
        "Create Username: ", 1, "Invalid Username. Must be more than 1 character."
    )
    password = utils.valid_input(
        "Create Password: ",
        1,
        "Invalid Password. Must be more than 1 character.",
        secret=True,
    )
    data = {
        "username": username,
        "password_hash": utils.hash_password(password),
        "is_logged_in": True,
    }
    utils.save_json(FILE_NAME, data)

if not data.get("is_logged_in", False):
    for _ in range(3):
        utry = input("Username: ")
        ptry = getpass.getpass("Password: ")
        if utry == data["username"] and utils.verify_password(ptry, data["password_hash"]):
            utils.update("is_logged_in", True, FILE_NAME, data)
            print("Login successful!")
            break
        print("Invalid credentials. Try again.")
    else:
        print("Too many failed attempts.")
        exit()

USER_HOME = os.path.join(FILES_ROOT, data["username"])
utils.ensure_user_dirs(USER_HOME)

USR_LOCAL_BIN = os.path.join(USER_HOME, "usr", "local", "bin")
USR_BIN = os.path.join(USER_HOME, "usr", "bin")
os.makedirs(USR_LOCAL_BIN, exist_ok=True)
os.makedirs(USR_BIN, exist_ok=True)

saved_path = utils.load_json(
    os.path.join(USR_BIN, ".path.json"),
    default_data=[USR_LOCAL_BIN, USR_BIN, COMMANDS_DIR],
)


def change_password(old_pass, new_pass):
    if not utils.verify_password(old_pass, data["password_hash"]):
        return False, "Error: Current password is incorrect."
    if len(new_pass.strip()) <= 1:
        return False, "Error: New password must be more than 1 character."
    utils.update("password_hash", utils.hash_password(new_pass), FILE_NAME, data)
    return True, "Password successfully updated!"


safe_context = {
    "username": data["username"],
    "commands_dir": COMMANDS_DIR,
    "home_dir": USER_HOME,
    "cwd": USER_HOME,
    "PATH": saved_path,
    "COOS": [],
    "verify_password": lambda attempt: utils.verify_password(attempt, data["password_hash"]),
    "change_password": change_password,
    "utils": {
        "scan_commands": utils.scan_commands,
        "valid_input": utils.valid_input,
        "ensure_user_dirs": utils.ensure_user_dirs,
    },
}
utils.scan_commands(safe_context["PATH"], safe_context)

if readline:
    readline.clear_history()

running = True
while running:
    rel_path = os.path.relpath(safe_context["cwd"], USER_HOME)
    prompt_path = "~" if rel_path == "." else f"~/{rel_path}"
    raw = input(f"{data['username']}:{prompt_path} $ ").strip()
    if not raw:
        continue

    chained = utils.split_chained_commands(raw)
    for parts in chained:
        cmd = next(iter(parts)).lower()
        args = parts[1:]

        if cmd in ("quit", "exit"):
            running = False
            break

        elif cmd == "logout":
            utils.update("is_logged_in", False, FILE_NAME, data)
            print("Logged out. Restart the terminal to log back in.")
            running = False
            break

        elif not system_cmds.handle_system_command(cmd, args, safe_context):
            rebuilt_cmd = " ".join(shlex.quote(p) for p in parts)
            utils.run_command(rebuilt_cmd, safe_context["PATH"], safe_context)
