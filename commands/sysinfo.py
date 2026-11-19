def run(args, context):
  parts = []

  # 1. Add all key-value pairs from context["data"]
  for key, value in context["data"].items():
    if key == "password":
      if value in args:
        parts.append(f"{key}: {value}")
      else:
        masked = value[0] + "*" * (len(value) - 1) if value else ""
        parts.append(f"{key}: {masked}")
    else:
      parts.append(f"{key}: {value}")

  # 2. Add the remaining items from context (skipping "data")
  for key, value in context.items():
    if key != "data":
      parts.append(f"{key}: {value}")

  return ",\n".join(parts) + "."
