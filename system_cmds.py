import importlib.util
import os
import shutil
import subprocess
import sys
import utils

SYSTEM_DESCRIPTIONS = {
    "help": "Show all built-in system commands and custom apps.",
    "ls": "List files and folders in your current directory.",
    "cd": "Change directory. Usage: cd <folder | .. | ~>",
    "pwd": "Print your current virtual directory path.",
    "mkdir": "Create one or more folders. Usage: mkdir <dir1> [dir2 ...]",
    "touch": "Create one or more files. Usage: touch <file1> [file2 ...]",
    "cat": "Read one or more files. Usage: cat <file1> [file2 ...]",
    "rm": "Delete one or more files/folders. Usage: rm <item1> [item2 ...]",
    "run": "Execute a compiled binary, script, or Python file. Usage: run <file> [args...]",
    "clear": "Clear the terminal screen.",
    "repass": "Change your password. Usage: repass <old_pass> <new_pass>",
    "logout": "Log out of your current user session.",
    "exit": "Shut down the terminal OS.",
}


def _safe_path(target, context):
    home_dir = context["home_dir"]
    current_dir = context["cwd"]

    if target == "~" or target == "":
        return home_dir
    if target.startswith("~/"):
        resolved = os.path.abspath(os.path.join(home_dir, target[2:]))
    else:
        resolved = os.path.abspath(os.path.join(current_dir, target))

    if os.path.commonpath([home_dir, resolved]) != home_dir:
        return None
    return resolved


def handle_system_command(cmd, args, context):
    if cmd == "help":
        print("\n=== SYSTEM COMMANDS ===")
        for name, desc in SYSTEM_DESCRIPTIONS.items():
            print(f"  {name:<10} - {desc}")

        custom_cmds = context["utils"]["scan_commands"](context["commands_dir"], context)
        print("\n=== CUSTOM APPS & PLUGINS ===")
        if not custom_cmds:
            print("  (No custom commands installed in commands/)")
        else:
            for name in custom_cmds:
                print(f"  {name}")
        print()
        return True

    elif cmd == "clear":
        os.system("cls" if os.name == "nt" else "clear")
        return True

    elif cmd == "pwd":
        rel = os.path.relpath(context["cwd"], context["home_dir"])
        print("~" if rel == "." else f"~/{rel}")
        return True

    elif cmd == "ls":
        items = sorted(os.listdir(context["cwd"]))
        if not items:
            print("(empty directory)")
        else:
            for item in items:
                full = os.path.join(context["cwd"], item)
                print(f"[DIR]  {item}/" if os.path.isdir(full) else f"[FILE] {item}")
        return True

    elif cmd == "cd":
        target = next(iter(args), "~")
        if target == "~":
            utils.ensure_user_dirs(context["home_dir"])
        new_path = _safe_path(target, context)
        if new_path is None:
            print("Access denied: Cannot navigate outside ~/")
        elif not os.path.isdir(new_path):
            print(f"cd: no such directory: {target}")
        else:
            context["cwd"] = new_path
        return True

    elif cmd == "mkdir":
        if not args:
            print("Usage: mkdir <folder1> [folder2 ...]")
            return True
        for folder in args:
            target_path = _safe_path(folder, context)
            if target_path is None:
                print(f"Access denied: Invalid path '{folder}'.")
            else:
                os.makedirs(target_path, exist_ok=True)
                print(f"Created folder: {folder}/")
        return True

    elif cmd == "touch":
        if not args:
            print("Usage: touch <file1> [file2 ...]")
            return True
        for filename in args:
            target_path = _safe_path(filename, context)
            if target_path is None:
                print(f"Access denied: Invalid path '{filename}'.")
            else:
                with open(target_path, "a", encoding="utf-8"):
                    pass
                print(f"Created file: {filename}")
        return True

    elif cmd == "cat":
        if not args:
            print("Usage: cat <file1> [file2 ...]")
            return True
        for filename in args:
            target_path = _safe_path(filename, context)
            if target_path is None or not os.path.isfile(target_path):
                print(f"cat: file not found: {filename}")
            else:
                if len(args) > 1:
                    print(f"--- {filename} ---")
                with open(target_path, "r", encoding="utf-8") as f:
                    print(f.read())
        return True

    elif cmd == "rm":
        if not args:
            print("Usage: rm <item1> [item2 ...]")
            return True
        for target in args:
            target_path = _safe_path(target, context)
            if target_path is None or target_path == context["home_dir"]:
                print(f"Access denied: Cannot delete '{target}'.")
            elif os.path.isfile(target_path):
                os.remove(target_path)
                print(f"Deleted file: {target}")
            elif os.path.isdir(target_path):
                shutil.rmtree(target_path)
                print(f"Deleted folder: {target}/")
            else:
                print(f"rm: not found: {target}")
        return True

    elif cmd == "run":
        if not args:
            print("Usage: run <executable_or_script> [args...]")
            return True

        target_name = next(iter(args))
        target_path = _safe_path(target_name, context)
        if target_path is None or not os.path.isfile(target_path):
            print(f"run: file not found: {target_name}")
            return True

        if target_path.endswith(".pyc"):
            old_argv = sys.argv
            sys.argv = [target_path] + args[1:]
            try:
                spec = importlib.util.spec_from_file_location("__tos_app__", target_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception as e:
                print(f"Runtime error in '{target_name}': {e}")
            finally:
                sys.argv = old_argv
            return True

        try:
            if target_path.endswith(".py"):
                cmd_list = [sys.executable, target_path] + args[1:]
            else:
                os.chmod(target_path, 0o755)
                cmd_list = [target_path] + args[1:]

            res = subprocess.run(
                cmd_list, cwd=context["cwd"], capture_output=True, text=True, timeout=10
            )
            output = (res.stdout + "\n" + res.stderr).strip()
            if output:
                print(output)
        except subprocess.TimeoutExpired:
            print("run: process timed out (10s limit).")
        except OSError as e:
            print(f"run: cannot execute '{target_name}': {e}")
        return True

    elif cmd == "repass":
        if len(args) != 2:
            print("Usage: repass <current_password> <new_password>")
            return True
        old_pass, new_pass = args
        success, message = context["change_password"](old_pass, new_pass)
        print(message)
        return True

    return False
