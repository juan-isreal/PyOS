import datetime
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
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
    "pypm": "Universal package manager. Usage: pypm <install|link|search|list|info|remove>",
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


def _fetch_bytes(url):
    """Fetch raw bytes from URL using urllib, falling back to system curl if available."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PyOS-pypm/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except Exception:
        if shutil.which("curl"):
            res = subprocess.run(
                ["curl", "-fsSL", url], capture_output=True, timeout=25
            )
            if res.returncode == 0:
                return res.stdout
            raise RuntimeError(res.stderr.decode("utf-8", errors="replace").strip() or "curl failed")
        raise


def _fetch_text(url):
    return _fetch_bytes(url).decode("utf-8")


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


def _install_github_repo(repo_slug, custom_name, bin_dir, manifest, manifest_path):
    repo_slug = repo_slug.replace("https://github.com", "").strip("/")
    if repo_slug.endswith(".git"):
        repo_slug = repo_slug[:-4]

    api_url = f"https://github.com{repo_slug}/releases/latest"
    print(f"Checking GitHub Releases for '{repo_slug}'...")

    try:
        release = json.loads(_fetch_text(api_url))
    except Exception as e:
        print(f"Could not find a GitHub release for '{repo_slug}': {e}")
        return

    assets = release.get("assets", [])
    if not assets:
        print(f"No compiled release assets found in '{repo_slug}'.")
        return

    os_name = platform.system().lower()
    arch_raw = platform.machine().lower()
    os_aliases = ["darwin", "mac", "apple", "osx"] if os_name == "darwin" else [os_name]
    arch_aliases = (
        ["arm64", "aarch64"] if arch_raw in ("arm64", "aarch64") else ["x86_64", "amd64", "x64"]
    )

    best_asset = None
    best_score = -1
    for asset in assets:
        name_low = asset["name"].lower()
        if any(bad in name_low for bad in (".sha256", ".sig", ".asc", ".txt", ".deb", ".rpm")):
            continue
        score = 0
        if any(k in name_low for k in os_aliases):
            score += 10
        if any(k in name_low for k in arch_aliases):
            score += 5
        if score > best_score:
            best_score = score
            best_asset = asset

    if not best_asset or best_score < 10:
        print(f"No matching {os_name}/{arch_raw} release binary found in '{repo_slug}'.")
        return

    asset_name = best_asset["name"]
    download_url = best_asset["browser_download_url"]
    pkg_name = (custom_name or repo_slug.split("/")[-1]).lower()

    print(f"Found Release : {release.get('tag_name', 'latest')} ({asset_name})")
    if not tsdk.confirm(f"Download and install '{pkg_name}' into ~/usr/bin? (y/n): "):
        print("Installation cancelled.")
        return

    try:
        archive_bytes = _fetch_bytes(download_url)
    except Exception as e:
        print(f"Download failed: {e}")
        return

    dest_bin = os.path.join(bin_dir, pkg_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = os.path.join(tmpdir, asset_name)
        with open(archive_path, "wb") as f:
            f.write(archive_bytes)

        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        if asset_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_dir)
        elif asset_name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(extract_dir)
        else:
            shutil.copy2(archive_path, dest_bin)

        if not os.path.isfile(dest_bin):
            candidates = []
            for r, _, files in os.walk(extract_dir):
                for fn in files:
                    if not fn.endswith((".md", ".txt", ".json", ".license")):
                        candidates.append(os.path.join(r, fn))
            if not candidates:
                print("Error: Archive contained no executable binary.")
                return
            picked = next(
                (c for c in candidates if os.path.basename(c).lower().startswith(pkg_name)),
                max(candidates, key=os.path.getsize),
            )
            shutil.copy2(picked, dest_bin)

    os.chmod(dest_bin, 0o755)

    wrapper_code = (
        "import subprocess\n"
        "def run(args, context):\n"
        f"    res = subprocess.run([{repr(dest_bin)}] + list(args), cwd=context['cwd'], capture_output=True, text=True)\n"
        "    return (res.stdout + '\\n' + res.stderr).strip() or None\n"
    )
    with open(os.path.join(bin_dir, f"{pkg_name}.py"), "w", encoding="utf-8") as f:
        f.write(wrapper_code)

    manifest[pkg_name] = {
        "type": "github-release",
        "source": f"github:{repo_slug} ({asset_name})",
        "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sha256": hashlib.sha256(archive_bytes).hexdigest()[:16],
    }
    utils.save_json(manifest_path, manifest)
    print(f"Installed '{pkg_name}' from GitHub Releases! Run it anytime with: {pkg_name}")
def _handle_pypm(args, context):
    if not args:
        print(
            "PyOS Universal Package Manager (pypm)\n"
            "Usage:\n"
            "  pypm install <name | owner/repo | url> [as_name]\n"
            "  pypm install --pip <pypi_package>\n"
            "  pypm install --bin <binary_url> <name>\n"
            "  pypm link <host_command> [as_name]\n"
            "  pypm search\n"
            "  pypm list\n"
            "  pypm info <package_name>\n"
            "  pypm remove <package_name>"
        )
        return

    sub = next(iter(args)).lower()
    arg1 = next(iter(args[1:2]), "")
    arg2 = next(iter(args[2:3]), "")
    arg3 = next(iter(args[3:4]), "")

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
            for name, entry in sorted(registry.items()):
                pkg_type = entry.get("type", "pyos") if isinstance(entry, dict) else "pyos"
                tag = " [installed]" if name in manifest else ""
                print(f"  - {name:<14} ({pkg_type}){tag}")
        except Exception as e:
            print(f"Could not reach registry ({e}).")

    elif sub == "list":
        if not manifest:
            installed = [
                f.removesuffix(".py")
                for f in sorted(os.listdir(bin_dir))
                if not f.startswith(".")
            ]
            if not installed:
                print("No packages installed in ~/usr/bin yet.")
                return
            print("Installed packages (~/usr/bin):")
            for name in installed:
                print(f"  - {name}")
            return

        print("Installed packages (~/usr/bin):")
        for name, meta in sorted(manifest.items()):
            ptype = meta.get("type", "pyos")
            print(f"  - {name:<14} [{ptype}] ({meta.get('installed_at', 'local')})")

    elif sub == "info":
        if not arg1:
            print("Usage: pypm info <package_name>")
            return
        pkg_name = arg1.removesuffix(".py").lower()
        meta = manifest.get(pkg_name)
        if not meta:
            print(f"Package '{pkg_name}' is not installed.")
            return
        print(
            f"Package   : {pkg_name}\n"
            f"Type      : {meta.get('type', 'pyos')}\n"
            f"Source    : {meta.get('source', 'Unknown')}\n"
            f"Installed : {meta.get('installed_at', 'Unknown')}\n"
            f"SHA-256   : {meta.get('sha256', 'N/A')}"
        )

    elif sub == "remove":
        if not arg1:
            print("Usage: pypm remove <package_name>")
            return
        pkg_name = arg1.removesuffix(".py").lower()
        removed = False
        for candidate in (os.path.join(bin_dir, f"{pkg_name}.py"), os.path.join(bin_dir, pkg_name)):
            if os.path.isfile(candidate):
                os.remove(candidate)
                removed = True
        if not removed and pkg_name not in manifest:
            print(f"Package '{pkg_name}' is not installed.")
            return
        manifest.pop(pkg_name, None)
        utils.save_json(manifest_path, manifest)
        print(f"Removed package '{pkg_name}'.")

    elif sub == "link":
        if not arg1:
            print("Usage: pypm link <host_command> [custom_name]")
            return
        host_cmd = arg1.lower()
        pkg_name = (arg2 or host_cmd).lower()
        resolved_bin = shutil.which(host_cmd)

        if not resolved_bin:
            sys_os = platform.system()
            if sys_os == "Darwin" and host_cmd in ("git", "make", "clang", "gcc"):
                if not tsdk.confirm(
                    f"'{host_cmd}' requires Apple Command Line Tools. Trigger installer? (y/n): "
                ):
                    print("Installation cancelled.")
                    return
                subprocess.run(["xcode-select", "--install"], capture_output=True, text=True)
                print("macOS Command Line Tools installer opened! Run 'pypm link git' once finished.")
                return
            elif sys_os == "Darwin" and shutil.which("brew"):
                installer = ["brew", "install", host_cmd]
                mgr_name = "Homebrew"
            elif sys_os == "Linux" and shutil.which("apt"):
                installer = ["sudo", "apt", "install", "-y", host_cmd]
                mgr_name = "apt"
            elif sys_os == "Windows" and shutil.which("winget"):
                installer = ["winget", "install", "-e", "--id", host_cmd]
                mgr_name = "winget"
            else:
                print(
                    f"pypm: '{host_cmd}' is not installed on this {sys_os} system.\n"
                    f"Tip: Try 'pypm install owner/repo' or 'pypm install --pip {host_cmd}'."
                )
                return

            if not tsdk.confirm(f"'{host_cmd}' is not installed on your OS. Install via {mgr_name}? (y/n): "):
                print("Installation cancelled.")
                return

            print(f"Running {' '.join(installer)}...")
            res = subprocess.run(installer, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"System install failed:\n{res.stderr.strip()}")
                return

            resolved_bin = shutil.which(host_cmd)
            if not resolved_bin:
                print(f"Installed via {mgr_name}, but '{host_cmd}' was not found on PATH.")
                return

        wrapper_code = (
            "import subprocess\n"
            "def run(args, context):\n"
            f"    res = subprocess.run([{repr(resolved_bin)}] + list(args), cwd=context['cwd'], capture_output=True, text=True)\n"
            "    return (res.stdout + '\\n' + res.stderr).strip() or None\n"
        )
        with open(os.path.join(bin_dir, f"{pkg_name}.py"), "w", encoding="utf-8") as f:
            f.write(wrapper_code)

        manifest[pkg_name] = {
            "type": "host",
            "source": f"host:{resolved_bin}",
            "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sha256": "host-link",
        }
        utils.save_json(manifest_path, manifest)
        print(f"Linked '{host_cmd}' into ~/usr/bin as '{pkg_name}'! Run it anytime with: {pkg_name}")
    elif sub == "install":
        if not arg1:
            print("Usage: pypm install <name | owner/repo | url> [as_name]")
            return

        if arg1 == "--pip":
            if not arg2:
                print("Usage: pypm install --pip <pypi_package_name>")
                return
            pip_pkg = arg2.lower()
            if not tsdk.confirm(f"Install '{pip_pkg}' from PyPI into ~/usr/bin? (y/n): "):
                print("Installation cancelled.")
                return
            print(f"Installing '{pip_pkg}' via pip...")
            res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--target", bin_dir, pip_pkg],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                print(f"pip install failed:\n{res.stderr.strip()}")
                return

            wrapper_code = (
                "import os, subprocess, sys\n"
                "def run(args, context):\n"
                "    env = os.environ.copy()\n"
                f"    env['PYTHONPATH'] = {repr(bin_dir)} + os.pathsep + env.get('PYTHONPATH', '')\n"
                f"    res = subprocess.run([sys.executable, '-m', {repr(pip_pkg)}] + list(args), cwd=context['cwd'], env=env, capture_output=True, text=True)\n"
                "    return (res.stdout + '\\n' + res.stderr).strip() or None\n"
            )
            with open(os.path.join(bin_dir, f"{pip_pkg}.py"), "w", encoding="utf-8") as f:
                f.write(wrapper_code)

            manifest[pip_pkg] = {
                "type": "pip",
                "source": f"pypi:{pip_pkg}",
                "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sha256": "pypi",
            }
            utils.save_json(manifest_path, manifest)
            print(f"Installed '{pip_pkg}' from PyPI! Run it anytime with: {pip_pkg}")
            return

        if arg1 == "--bin":
            if not arg2 or not arg3:
                print("Usage: pypm install --bin <binary_url> <command_name>")
                return
            url = arg2
            pkg_name = arg3.lower()
            if not re.match(r"^[a-z0-9_-]+$", pkg_name):
                print("Invalid command name.")
                return
            if not tsdk.confirm(f"Download binary '{pkg_name}' from {url}? (y/n): "):
                print("Installation cancelled.")
                return
            try:
                raw_bytes = _fetch_bytes(url)
            except Exception as e:
                print(f"Binary download failed: {e}")
                return

            bin_path = os.path.join(bin_dir, pkg_name)
            with open(bin_path, "wb") as f:
                f.write(raw_bytes)
            os.chmod(bin_path, 0o755)

            wrapper_code = (
                "import subprocess\n"
                "def run(args, context):\n"
                f"    res = subprocess.run([{repr(bin_path)}] + list(args), cwd=context['cwd'], capture_output=True, text=True)\n"
                "    return (res.stdout + '\\n' + res.stderr).strip() or None\n"
            )
            with open(os.path.join(bin_dir, f"{pkg_name}.py"), "w", encoding="utf-8") as f:
                f.write(wrapper_code)

            manifest[pkg_name] = {
                "type": "binary",
                "source": url,
                "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sha256": hashlib.sha256(raw_bytes).hexdigest()[:16],
            }
            utils.save_json(manifest_path, manifest)
            print(f"Installed binary '{pkg_name}' into ~/usr/bin! Run it with: {pkg_name}")
            return

        if (
            arg1.startswith("https://github.com")
            or ("/" in arg1 and not arg1.startswith(("http://", "https://")))
        ):
            custom = arg2.removesuffix(".py").lower() if arg2 else None
            _install_github_repo(arg1, custom, bin_dir, manifest, manifest_path)
            return

        custom_name = arg2.removesuffix(".py").lower() if arg2 else None
        pkg_type = "pyos"
        entry = None

        if not arg1.startswith(("http://", "https://")):
            pkg_key = arg1.lower()
            print(f"Checking PyOS registry for '{pkg_key}'...")
            try:
                registry = json.loads(_fetch_text(REGISTRY_URL))
            except Exception as e:
                print(f"Registry lookup failed ({e}).")
                registry = {}

            if pkg_key in registry:
                entry = registry[pkg_key]
                if isinstance(entry, dict):
                    pkg_type = entry.get("type", "pyos")
                    url = entry.get("url", "")
                else:
                    url = entry
                pkg_name = custom_name or pkg_key
            else:
                # Not in registry.json -> check if it's a host command (with curl/xcode/brew fallback)
                print(f"'{pkg_key}' not in registry.json — checking host system / curl...")
                _handle_pypm(["link", pkg_key, custom_name or pkg_key], context)
                return
        else:
            url = arg1
            raw_file = url.rstrip("/").split("/")[-1].removesuffix(".py").lower()
            pkg_name = custom_name or raw_file

        if pkg_type == "host":
            host_cmd = entry.get("cmd", pkg_name) if isinstance(entry, dict) else pkg_name
            _handle_pypm(["link", host_cmd, pkg_name], context)
            return
        if pkg_type == "github":
            _install_github_repo(url, pkg_name, bin_dir, manifest, manifest_path)
            return
        if pkg_type == "binary":
            _handle_pypm(["install", "--bin", url, pkg_name], context)
            return

        if not re.match(r"^[a-z0-9_-]+$", pkg_name):
            print(f"Invalid package name '{pkg_name}'. Use lowercase letters, numbers, _ or -.")
            return

        print(f"Package : {pkg_name}\nSource  : {url}")
        if not tsdk.confirm("Download and install to ~/usr/bin? (y/n): "):
            print("Installation cancelled.")
            return

        try:
            code = _fetch_text(url)
        except Exception as e:
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
            "type": "pyos",
            "source": url,
            "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest()[:16],
        }
        utils.save_json(manifest_path, manifest)
        print(f"Installed '{pkg_name}' into ~/usr/bin! Run it anytime by typing: {pkg_name}")
    else:
        print(f"Unknown pypm subcommand '{sub}'.")


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
