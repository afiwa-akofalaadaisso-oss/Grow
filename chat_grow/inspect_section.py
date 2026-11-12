# -*- coding: utf-8 -*-
with open("chat_grow/templates/dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's inspect line 3155 to 3300
lines = html.splitlines()
print(f"Total lines: {len(lines)}")

for i in range(3150, 3290):
    if i < len(lines):
        print(f"{i+1}: {lines[i]}")

