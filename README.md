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

### Quick Install (Latest Release — Recommended)
Download, extract, and launch the latest PyOS release automatically in one command:
```bash
curl -fsSL https://githubusercontent.com | bash
```
*(To launch in CLI mode instead of the GUI, run `curl -fsSL https://githubusercontent.com | bash -s -- --cli`.)*

### Manual Source Setup (Developers)
1. Clone PyOS and open the folder:
   ```bash
   cd ~ && git clone https://github.com && cd PyOS
   ```
2. Launch PyOS:
   ```bash
   python3 gui.py
   ```
