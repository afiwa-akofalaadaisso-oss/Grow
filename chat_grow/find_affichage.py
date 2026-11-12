with open("chat_grow/templates/dashboard.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "Affichage" in l or "paginationInfo" in l:
        print(f"L{i+1}: {l.strip()[:100]}")

