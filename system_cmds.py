import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import tsdk
import utils

REGISTRY_URL = "https://githubusercontent.com"

SYSTEM_DESCRIPTIONS = {
    "help": "Show all built-in system commands and installed apps.",
    "ls": "List files and folders in your current directory.",
    "tree": "Display a visual folder tree of your current directory.",
    "cd": "Change directory. Usage: cd <folder | .. | ~>",
    "pwd": "Print your current virtual directory path.",
    "mkdir": "Create one or more folders. Usage: mkdir <dir1> [dir2 ...]",
    "touch": "Create one or more files. Usage: touch <file1> [file2 ...]",
    "cat": "Read one or more files. Usage: cat <file1> [file2 ...]",
    "rm": "Delete one or more files/folders. Usage: rm <item1> [item2 ...]",
    "run": "Execute a .py, .pyc, or binary file. Usage: run <file> [args...]",
    "pypm": "Built-in package manager. Usage: pypm <install|search|list|info|remove>",
    "path": "View or edit PATH dirs. Usage: path [add <dir> | remove <dir>]",
    "sysinfo": "Show PyOS system, user, and PATH status.",
    "clear": "Clear the terminal screen.",
    "repass": "Change your password. Usage: repass <old_pass> <new_pass>",
    "logout": "Log out of your current user session.",
    "exit": "Shut down PyOS.",
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


def _usr_bin_dir(context):
    bin_dir = os.path.join(context["home_dir"], "usr", "bin")
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir


def _fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "PyOS-pypm/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8")


def _print_tree(directory, prefix=""):
    entries = sorted(e for e in os.listdir(directory) if not e.startswith("."))
    for idx, entry in enumerate(entries):
        full = os.path.join(directory, entry)
        is_last = idx == len(entries) - 1
        connector = "└── " if is_last else "├── "
        if os.path.isdir(full):
            print(f"{prefix}{connector}{entry}/")
            _print_tree(full, prefix + ("    " if is_last else "│   "))
        else:
            print(f"{prefix}{connector}{entry}")
def _handle_pypm(args, context):
    if not args:
        print(
            "PyOS Built-in Package Manager (pypm)\n"
            "Usage:\n"
            "  pypm install <url_or_name> [custom_name]\n"
            "  pypm search\n"
            "  pypm list\n"
            "  pypm info <package_name>\n"
            "  pypm remove <package_name>"
        )
        return

    sub = next(iter(args)).lower()
    arg1 = next(iter(args[1:2]), "")
    arg2 = next(iter(args[2:3]), "")

    bin_dir = _usr_bin_dir(context)
    manifest_path = os.path.join(bin_dir, ".installed.json")
    manifest = utils.load_json(manifest_path, default_data={})

    if sub == "search":
        print("Fetching PyOS package registry...")
        try:
            registry = json.loads(_fetch_text(REGISTRY_URL))
            if not registry:
                print("Registry is empty.")
                return
            print("Available packages in PyOS registry:")
            for name in sorted(registry.keys()):
                tag = " [installed]" if name in manifest else ""
                print(f"  - {name:<14}{tag}")
        except Exception as e:
            print(f"Could not reach registry ({e}).")

    elif sub == "list":
        installed = [
            f.removesuffix(".py")
            for f in sorted(os.listdir(bin_dir))
            if f.endswith(".py") and not f.startswith("_")
        ]
        if not installed:
            print("No packages installed in ~/usr/bin yet.")
            return
        print("Installed packages (~/usr/bin):")
        for name in installed:
            meta = manifest.get(name, {})
            print(f"  - {name:<14} ({meta.get('installed_at', 'local')})")

    elif sub == "info":
        if not arg1:
            print("Usage: pypm info <package_name>")
            return
        pkg_name = arg1.removesuffix(".py").lower()
        target = os.path.join(bin_dir, f"{pkg_name}.py")
        if not os.path.isfile(target):
            print(f"Package '{pkg_name}' is not installed.")
            return
        meta = manifest.get(pkg_name, {})
        print(
            f"Package   : {pkg_name}\n"
            f"Location  : ~/usr/bin/{pkg_name}.py\n"
            f"Source    : {meta.get('source', 'Unknown / Local')}\n"
            f"Installed : {meta.get('installed_at', 'Unknown')}\n"
            f"SHA-256   : {meta.get('sha256', 'N/A')}"
        )

    elif sub == "remove":
        if not arg1:
            print("Usage: pypm remove <package_name>")
            return
        pkg_name = arg1.removesuffix(".py").lower()
        target = os.path.join(bin_dir, f"{pkg_name}.py")
        if not os.path.isfile(target):
            print(f"Package '{pkg_name}' is not installed in ~/usr/bin.")
            return
        os.remove(target)
        manifest.pop(pkg_name, None)
        utils.save_json(manifest_path, manifest)
        print(f"Removed package '{pkg_name}'.")

    elif sub == "install":
        if not arg1:
            print("Usage: pypm install <url_or_package_name> [custom_name]")
            return

        custom_name = arg2.removesuffix(".py").lower() if arg2 else None

        if not arg1.startswith(("http://", "https://")):
            pkg_key = arg1.lower()
            print(f"Looking up '{pkg_key}' in PyOS registry...")
            try:
                registry = json.loads(_fetch_text(REGISTRY_URL))
                if pkg_key not in registry:
                    print(f"Package '{pkg_key}' not found. Run 'pypm search' to see packages.")
                    return
                url = registry[pkg_key]
                pkg_name = custom_name or pkg_key
            except Exception as e:
                print(f"Registry lookup failed ({e}). Pass a direct raw URL instead.")
                return
        else:
            url = arg1
            raw_file = url.rstrip("/").split("/")[-1].removesuffix(".py").lower()
            pkg_name = custom_name or raw_file

        if not re.match(r"^[a-z0-9_-]+$", pkg_name):
            print(f"Invalid package name '{pkg_name}'. Use lowercase letters, numbers, _ or -.")
            return

        print(f"Package : {pkg_name}\nSource  : {url}")
        if not tsdk.confirm("Download and install to ~/usr/bin? (y/n): "):
            print("Installation cancelled.")
            return

        try:
            code = _fetch_text(url)
        except urllib.error.URLError as e:
            print(f"Download failed: {e}")
            return

        if "def run(" not in code:
            print("Error: Downloaded script is missing a 'def run(...)' entry point.")
            return

        try:
            compile(code, f"{pkg_name}.py", "exec")
        except SyntaxError as e:
            print(f"Error: Syntax error on line {e.lineno}: {e.msg}")
            return

        dest_path = os.path.join(bin_dir, f"{pkg_name}.py")
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(code)

        manifest[pkg_name] = {
            "source": url,
            "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest()[:16],
        }
        utils.save_json(manifest_path, manifest)
        print(f"Installed '{pkg_name}' into ~/usr/bin! Run it anytime by typing: {pkg_name}")
    else:
        print(f"Unknown pypm subcommand '{sub}'. Use: install, search, list, info, remove")
def handle_system_command(cmd, args, context):
    if cmd == "help":
        print("\n=== BUILT-IN SYSTEM COMMANDS ===")
        for name, desc in SYSTEM_DESCRIPTIONS.items():
            print(f"  {name:<10} - {desc}")

        search_paths = context.get("PATH", [context["commands_dir"]])
        custom_cmds = context["utils"]["scan_commands"](search_paths, context)
        print("\n=== INSTALLED APPS & PACKAGES (PATH) ===")
        if not custom_cmds:
            print("  (No apps or packages installed yet)")
        else:
            for name in custom_cmds:
                print(f"  {name}")
        print()
        return True

    elif cmd == "pypm":
        _handle_pypm(args, context)
        return True

    elif cmd == "path":
        bin_dir = _usr_bin_dir(context)
        local_bin = os.path.join(context["home_dir"], "usr", "local", "bin")
        paths = context.setdefault("PATH", [local_bin, bin_dir, context["commands_dir"]])
        path_cfg = os.path.join(bin_dir, ".path.json")

        if len(args) >= 2:
            action = next(iter(args)).lower()
            raw_dir = next(iter(args[1:2]), "")
            target_dir = _safe_path(raw_dir, context)
            if action == "add":
                if not target_dir or not os.path.isdir(target_dir):
                    print(f"path: invalid directory: {raw_dir}")
                    return True
                if target_dir not in paths:
                    paths.insert(0, target_dir)
                    utils.save_json(path_cfg, paths)
                print(f"Added to PATH: {raw_dir}")
                return True
            elif action == "remove":
                if target_dir in (local_bin, bin_dir, context["commands_dir"]):
                    print("path: cannot remove core system PATH directories.")
                    return True
                if target_dir in paths:
                    paths.remove(target_dir)
                    utils.save_json(path_cfg, paths)
                    print(f"Removed from PATH: {raw_dir}")
                else:
                    print("path: directory not found in PATH.")
                return True

        print("Active PyOS PATH (searched in priority order):")
        for i, p in enumerate(paths, start=1):
            if os.path.commonpath([context["home_dir"], p]) == context["home_dir"]:
                rel = os.path.relpath(p, context["home_dir"])
                disp = "~" if rel == "." else f"~/{rel}"
            else:
                disp = f"<system>/{os.path.basename(p)}"
            print(f"  {i}. {disp}")
        return True

    elif cmd == "sysinfo":
        rel = os.path.relpath(context["cwd"], context["home_dir"])
        disp = "~" if rel == "." else f"~/{rel}"
        py_ver = next(iter(sys.version.split()))
        print(
            f"\n=== PyOS SYSTEM INFO ===\n"
            f"  User      : {context['username']}\n"
            f"  Location  : {disp}\n"
            f"  Python    : {py_ver}\n"
            f"  PATH Dirs : {len(context.get('PATH', []))}\n"
        )
        return True

    elif cmd == "tree":
        rel = os.path.relpath(context["cwd"], context["home_dir"])
        print("~" if rel == "." else f"~/{rel}")
        _print_tree(context["cwd"])
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
                spec = importlib.util.spec_from_file_location("__pyos_app__", target_path)
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
