with open("chat_grow/templates/dashboard.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "setMobileView" in l:
        print(f"L{i+1}: {l.strip()}")
        for j in range(max(0, i-5), min(len(lines), i+35)):
            print(f"  {j+1}: {lines[j].rstrip()}")
        break

