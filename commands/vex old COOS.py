import tsdk

DESCRIPTION = "Vex: A secure, sandboxed file editor and viewer powered by TSDK."

def run(args, context):
    # Handle args whether passed as a string or list
    if isinstance(args, str):
        parts = args.strip().split(maxsplit=2)
        filename = parts[0] if len(parts) > 0 else None
        action = parts[1].lower() if len(parts) > 1 else "view"
        content = parts[2] if len(parts) > 2 else ""
    elif isinstance(args, list):
        filename = args[0] if len(args) > 0 else None
        action = args[1].lower() if len(args) > 1 else "view"
        content = " ".join(args[2:]) if len(args) > 2 else ""
    else:
        filename = str(args)
        action = "view"
        content = ""

    if not filename:
        return "Usage: vex <filename> [view|append|write|del|clear] [content/line_num]"

    # Read existing file content using TSDK's secure sandboxed reader
    raw_text = tsdk.read_file(filename, context)

    # 1. VIEW file contents with line numbers
    if action == "view" or not action:
        if raw_text is None:
            return f"File '{filename}' does not exist or is outside your virtual home (~/)."
        
        lines = raw_text.splitlines()
        if not lines:
            return f"--- {filename} (empty) ---"
        
        output = [f"\n--- {filename} ({len(lines)} lines) ---"]
        for idx, line in enumerate(lines, 1):
            output.append(f"{idx:3d} | {line}")
        output.append("-" * 30)
        return "\n".join(output)

    # 2. APPEND a new line using TSDK sandboxed path resolution
    elif action == "append":
        if not content:
            return f"Usage: vex {filename} append <text to add>"
        
        current_text = raw_text if raw_text is not None else ""
        separator = "\n" if current_text and not current_text.endswith("\n") else ""
        new_text = current_text + separator + content + "\n"
        
        success = tsdk.write_file(filename, new_text, context)
        if success:
            return f"Appended to '{filename}': {content}"
        return f"Error: Invalid or un-sandboxed path for '{filename}'."

    # 3. WRITE / OVERWRITE the file
    elif action == "write":
        success = tsdk.write_file(filename, content + ("\n" if content else ""), context)
        if success:
            return f"Successfully wrote to '{filename}'."
        return f"Error: Invalid or un-sandboxed path for '{filename}'."

    # 4. DELETE a specific line number
    elif action == "del":
        if not content.isdigit():
            return f"Usage: vex {filename} del <line_number>"
        
        if raw_text is None:
            return f"File '{filename}' does not exist."
            
        lines = raw_text.splitlines()
        line_num = int(content)
        
        if 1 <= line_num <= len(lines):
            removed = lines.pop(line_num - 1)
            new_text = "\n".join(lines) + ("\n" if lines else "")
            tsdk.write_file(filename, new_text, context)
            return f"Deleted line {line_num} ('{removed}') from '{filename}'."
        else:
            return f"Invalid line number {line_num}. File has {len(lines)} lines."

    # 5. CLEAR all contents
    elif action == "clear":
        success = tsdk.write_file(filename, "", context)
        if success:
            return f"Cleared all contents of '{filename}'."
        return f"Error clearing '{filename}'."

    else:
        return f"Unknown action '{action}'. Available: view, append, write, del, clear."