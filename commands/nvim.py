import os
import tsdk

DESCRIPTION = "Neovim (NVIM) - Faithful modal text editor port for TOS."

def run(args, context):
    if not args:
        filename = "untitled.txt"
    else:
        filename = args[0] if isinstance(args, list) else args.strip().split()[0]
    
    filepath = os.path.join(context["cwd"], filename)
    
    # Load existing file lines or initialize empty buffer
    lines = []
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception as e:
            return f"Error reading file: {e}"
            
    if not lines:
        lines = [""]
        
    cursor_y = 0
    mode = "NORMAL"
    modified = False
    status_msg = f'"{filename}" {len(lines)}L, {sum(len(l) for l in lines)}B'
    
    while True:
        tsdk.clear()
        
        # Neovim Tabline / Top Banner
        tsdk.out("=" * 65)
        tsdk.out(f" NVIM v0.10.0-dev │ File: {filename} {'[+]' if modified else ''}")
        tsdk.out("=" * 65)
        
        # Viewport rendering (14 lines visible around cursor)
        max_display = 14
        start_idx = max(0, cursor_y - max_display // 2)
        end_idx = min(len(lines), start_idx + max_display)
        
        for i in range(start_idx, end_idx):
            pointer = " >" if i == cursor_y else "  "
            tsdk.out(f"{pointer} {i + 1:4d} │ {lines[i]}")
            
        # Pad empty viewport space
        for _ in range(max_display - (end_idx - start_idx)):
            tsdk.out("       │ ~")
            
        # Neovim Statusline
        tsdk.out("-" * 65)
        tsdk.out(f" -- {mode} -- Line {cursor_y + 1}/{len(lines)} │ {status_msg}")
        tsdk.out("-" * 65)
        
        # Prompt based on active mode
        prompt = ":" if mode == "COMMAND" else ("i> " if mode == "INSERT" else "NORMAL> ")
        
        try:
            user_input = tsdk.ask(prompt)
        except (KeyboardInterrupt, EOFError):
            break
            
        status_msg = "" # Reset status message per loop iteration
        
        if mode == "NORMAL":
            cmd = user_input.strip()
            
            if cmd == "i":
                mode = "INSERT"
            elif cmd == "o":
                lines.insert(cursor_y + 1, "")
                cursor_y += 1
                mode = "INSERT"
                modified = True
            elif cmd == "j":
                if cursor_y < len(lines) - 1:
                    cursor_y += 1
            elif cmd == "k":
                if cursor_y > 0:
                    cursor_y -= 1
            elif cmd == "dd":
                if len(lines) > 1:
                    lines.pop(cursor_y)
                    cursor_y = min(cursor_y, len(lines) - 1)
                    modified = True
                    status_msg = "1 line less"
                else:
                    lines[0] = ""
                    modified = True
                    status_msg = "Buffer cleared"
            elif cmd.isdigit():
                target = int(cmd) - 1
                if 0 <= target < len(lines):
                    cursor_y = target
                else:
                    status_msg = "E42: Line number out of range"
            elif cmd.startswith(":"):
                ex_cmd = cmd[1:].strip().lower()
                if ex_cmd == "w":
                    try:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write("\n".join(lines) + "\n")
                        modified = False
                        status_msg = f'"{filename}" written'
                    except Exception as e:
                        status_msg = f"E212: Can't open file for writing: {e}"
                elif ex_cmd == "q":
                    if modified:
                        status_msg = "E37: No write since last change (use :q! or :wq)"
                    else:
                        break
                elif ex_cmd == "q!":
                    break
                elif ex_cmd == "wq":
                    try:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write("\n".join(lines) + "\n")
                        break
                    except Exception as e:
                        status_msg = f"Error: {e}"
                else:
                    status_msg = f"E492: Not an editor command: {ex_cmd}"
            else:
                if cmd:
                    status_msg = f'E492: Not an editor command: {cmd}'
                    
        elif mode == "INSERT":
            lines[cursor_y] = user_input
            modified = True
            mode = "NORMAL"
            status_msg = "Line updated"
            
    return f"Closed nvim session for '{filename}'."