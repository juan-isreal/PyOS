# PyOS — Python Terminal Operating System

A lightweight, sandboxed **Terminal Operating System** built entirely in Python with both a **macOS-inspired Tkinter GUI** (`gui.py`) and a **CLI mode** (`main.py`), featuring salted PBKDF2 authentication, a virtual `~/` filesystem, command chaining (`&&`), and a modular plugin SDK (`tsdk`).

---

## Features

- **Dual Interface (`gui.py` & `main.py`):** Launch a dark-mode macOS-style Tkinter terminal window with arrow-key history and masked password input, or run directly in your native terminal.
- **Cryptographic Authentication:** Uses `PBKDF2-HMAC-SHA256` with unique 16-byte random salts (`secrets.token_hex`) and randomized iteration counts (`90,000–120,000`) stored in `iterations:salt:hash` format.
- **Sandboxed Virtual Filesystem (`~/`):** Automatically provisions and self-heals `Desktop/`, `Documents/`, `Downloads/`, and `Projects/` per user while blocking directory traversal outside `~/`.
- **Command Chaining (`&&`):** Chain multiple system commands and custom plugins on a single line (e.g., `mkdir app && cd app && touch main.py utils.py && ls`).
- **Built-in Transpiler & Bytecode Runner (`compile` & `run`):** Uses Python's `ast` module to rewrite `input()` and `print()` into `tsdk.ask()` and `tsdk.out()`, compiling scripts into `.pyc` bytecode that runs live inside the GUI.
- **Modular Plugin Architecture (`commands/` + `tsdk`):** Drop any `.py` file with a `run(args, context)` function into `commands/` to extend PyOS, or mark commands Out Of Service (`COOS`).

---

## Project Structure

```text
PyOS/
├── gui.py            # Dark-mode Tkinter macOS Terminal GUI
├── main.py           # CLI bootloader and shell loop
├── system_cmds.py    # Built-in OS commands (ls, cd, mkdir, touch, cat, rm, run, repass, help)
├── utils.py          # PBKDF2 hashing, shlex parser, and dynamic plugin loader
├── tsdk.py           # Terminal SDK for building interactive CLI + GUI apps
└── commands/         # Custom user plugins & apps
    ├── compile.py    # AST transpiler & .pyc bytecode compiler
    ├── edit.py       # Full-screen modular text/code editor
    ├── example.py    # Developer showcase for tsdk primitives
    └── git.py        # Git & GitHub CLI wrapper
```

---

## Getting Started

### Prerequisites
- **Python 3.10+** (uses only the Python Standard Library—zero external `pip` installs required!)

### Installation & Setup
1. Download PyOS and open the folder:
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
3. Enter a new username and password when prompted, and you're ready to start using PyOS!

---

## Built-in Commands

| Command | Description |
| :--- | :--- |
| `help` | List all built-in system commands and installed custom plugins |
| `ls` | List files and folders in the current directory |
| `cd <path>` | Change directory (`~`, `..`, or relative paths inside `~/`) |
| `pwd` | Print current virtual path |
| `mkdir <dirs...>` | Create one or more folders |
| `touch <files...>` | Create one or more empty files |
| `cat <files...>` | Display the contents of one or more files |
| `rm <items...>` | Delete one or more files or folders |
| `run <file>` | Execute a `.py`, `.pyc`, or native executable |
| `repass <old> <new>` | Update your password (re-salted with new random iterations) |
| `clear` | Clear the terminal screen |
| `logout` / `exit` | Lock session or exit PyOS |

---

## Building Custom Commands (`tsdk`)

Create any `.py` file inside `commands/` with a `run(args, context)` function. Use `tsdk` so your app works seamlessly in both `gui.py` and `main.py`:

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
