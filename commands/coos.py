import os
import re

DESCRIPTION = "Lists all commands currently Out Of Service (COOS)."


def run(args, context):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    raw_coos = []
    clean_names = []

    for f in os.listdir(script_dir):
        if f.endswith(".py") and not f.startswith("_") and os.path.isfile(os.path.join(script_dir, f)):
            cmd_name = f.removesuffix(".py")

            if cmd_name.lower() == "coos":
                continue

            if (
                "coos" in cmd_name.lower()
                or len(cmd_name.split()) > 1
                or not re.match(r"^[a-z0-9_-]+$", cmd_name)
            ):
                raw_coos.append(cmd_name)
                cleaned = re.sub(r"coos", "", cmd_name, flags=re.IGNORECASE).strip(" _-")
                clean_names.append(cleaned if cleaned else cmd_name)

    context["COOS"] = sorted(raw_coos)

    if not clean_names:
        return "No commands are currently Out Of Service."

    return "Commands Out Of Service (COOS): " + ", ".join(sorted(clean_names))
