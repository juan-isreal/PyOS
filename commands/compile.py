import os
import py_compile
import shutil
import subprocess
import sys
import tsdk

DESCRIPTION = "Compile a Python script into bytecode (.pyc) or native binary (--bin)."


def run(args, context):
    if not args:
        return "Usage: compile <script.py> [--bin]"

    parts = args.strip().split() if isinstance(args, str) else args
    filename = next(iter(parts))
    use_binary = "--bin" in parts

    filepath = tsdk.resolve_path(filename, context)
    if filepath is None:
        return "Access denied: Cannot access files outside ~/"
    if not os.path.isfile(filepath):
        return f"Error: File '{filename}' not found."

    work_dir = os.path.dirname(filepath)
    base_name, _ = os.path.splitext(os.path.basename(filepath))

    # Fast bytecode compilation (.pyc) by default
    if not use_binary:
        try:
            out_pyc = os.path.join(work_dir, f"{base_name}.pyc")
            py_compile.compile(filepath, cfile=out_pyc, doraise=True)
            return f"Compiled bytecode: {base_name}.pyc\nRun it using: run {base_name}.pyc"
        except py_compile.PyCompileError as e:
            return f"Syntax Error during compilation:\n{e.msg}"

    # Optional native machine-code binary via PyInstaller (--bin)
    binary_name = base_name + (".exe" if os.name == "nt" else "")
    tsdk.out(f"Building native binary '{binary_name}' (this takes ~15s)...")

    try:
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--distpath",
            work_dir,
            filepath,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir, timeout=45)

        if result.returncode != 0:
            return f"PyInstaller failed (is it installed?):\n{result.stderr.strip()}"

        for cleanup_item in (f"{base_name}.spec", "build"):
            cleanup_path = os.path.join(work_dir, cleanup_item)
            if os.path.isdir(cleanup_path):
                shutil.rmtree(cleanup_path)
            elif os.path.isfile(cleanup_path):
                os.remove(cleanup_path)

        return f"Compiled native binary: {binary_name}\nRun it using: run {binary_name}"

    except subprocess.TimeoutExpired:
        return "Error: Binary compilation timed out."
    except Exception as e:
        return f"Compilation error: {e}"
