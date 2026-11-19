# PyOS — Python Operating System

A lightweight, sandboxed **Terminal & Desktop Operating System** built entirely in Python with both a **macOS-inspired Tkinter GUI** (`gui.py`), a **Linux-style Desktop Environment** (`startx`), and a **CLI mode** (`main.py`), featuring salted PBKDF2 authentication, a virtual `~/` filesystem with `~/usr/bin`, command chaining (`&&`), a universal package manager (`pypm`), and a modular plugin SDK (`tsdk`).

---

## Features

- **Dual Interface + Desktop Mode (`gui.py`, `main.py`, & `startx`):** Launch a dark-mode macOS-style Tkinter terminal window with arrow-key history and masked password input, run in native CLI mode, or type `startx` to switch into a graphical Linux-style desktop with draggable windows.
- **Universal Package Manager (`pypm`) & `PATH`:** Install PyOS plugins from `registry.json`, pull prebuilt binaries directly from GitHub Releases (`pypm install owner/repo`), install Python CLI tools from PyPI (`pypm install --pip <pkg>`), or link host system commands (`pypm link git`) into `~/usr/bin`.
- **Cryptographic Authentication:** Uses `PBKDF2-HMAC-SHA256` with unique 16-byte random salts (`secrets.token_hex`) and randomized iteration counts (`90,000–120,000`) stored in `iterations:salt:hash` format.
- **Sandboxed Virtual Filesystem (`~/`):** Automatically provisions and self-heals `Desktop/`, `Documents/`, `Downloads/`, `Projects/`, `usr/bin/`, and `usr/local/bin/` per user while blocking directory traversal outside `~/`.
- **Command Chaining (`&&`):** Chain multiple system commands and custom apps on a single line (e.g., `mkdir app && cd app && touch main.py utils.py && tree`).
- **Modular Plugin SDK (`tsdk`):** Drop any `.py` file with a `run(args, context)` function into `commands/` or `~/usr/bin/` to extend PyOS, or mark commands Out Of Service (`COOS`).

---

## Project Structure

```text
PyOS/
├── gui.py            # Dark-mode Tkinter macOS Terminal GUI
├── main.py           # CLI bootloader and shell loop
├── system_cmds.py    # Built-in OS commands (pypm, path, ls, tree, cd, mkdir, cat, rm, run, help)
├── utils.py          # PBKDF2 hashing, shlex parser, and cached PATH plugin loader
├── tsdk.py           # Terminal & Desktop SDK for building interactive CLI + GUI apps
├── registry.json     # Package store index for pypm
└── commands/         # Core pre-installed apps & plugins
    ├── startx.py     # Graphical Linux-style Desktop Environment
    ├── edit.py       # Full-screen modular text/code editor
    ├── example.py    # Developer showcase for tsdk primitives
    └── coos.py       # Out-Of-Service command manager
```

---

## Getting Started

### Prerequisites
- **Python 3.10+** (uses only the Python Standard Library—zero external `pip` installs required!)

### Installation & Setup
1. Clone PyOS and open the folder:
   ```bash
   cd ~ && git clone https://github.com && cd PyOS
   ```
2. Launch PyOS to run first-time setup (creates your user account and `~/` folders):
   ```bash
   python3 gui.py
   ```
   *Or run in CLI mode:*
   ```bash
   python3 main.py
   ```
3. Enter a new username and password when prompted, then type `help` or `startx` to explore!

---

## Built-in Commands

| Command | Description |
| :--- | :--- |
| `help` | List all built-in system commands and installed `PATH` apps |
| `pypm` | Install, search, link, inspect, or remove packages (`pypm install <name\|owner/repo>`) |
| `path` | View or add/remove directories in your virtual `PATH` |
| `startx` | Launch the graphical Linux-style Desktop Environment |
| `ls` / `tree` | List files or display a visual directory tree |
| `cd <path>` | Change directory (`~`, `..`, or relative paths inside `~/`) |
| `pwd` | Print current virtual path |
| `mkdir` / `touch` | Create one or more folders or empty files |
| `cat` / `rm` | Read or delete one or more files or folders |
| `run <file>` | Execute a `.py`, `.pyc`, or native executable |
| `sysinfo` | Display user, Python version, and `PATH` status |
| `repass <old> <new>` | Update your password (re-salted with new random iterations) |
| `clear` | Clear the terminal screen |
| `logout` / `exit` | Lock session or exit PyOS |

---

## Building Custom Commands (`tsdk`)

Create any `.py` file inside `commands/` or `~/usr/bin/` with a `run(args, context)` function. Use `tsdk` so your app works seamlessly in both `gui.py` and `main.py`:

```python
import tsdk

DESCRIPTION = "Greets the user and saves a note."

def run(args, context):
    name = tsdk.ask("What is your name? ")
    tsdk.write_file("greeting.txt", f"Hello, {name}!\n", context)
    tsdk.out(f"Saved greeting for {name} in {context['cwd']}!")
```

---

## License

This project is open source under the [MIT License](LICENSE).
