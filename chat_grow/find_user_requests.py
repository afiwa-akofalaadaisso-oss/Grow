with open("chat_grow/templates/dashboard.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("--- 1. Webhook occurrences in HTML body ---")
for i, l in enumerate(lines):
    if i > 2500 and "webhook" in l.lower() and "<" in l:
        print(f"L{i+1}: {l.strip()[:100]}")

print("\n--- 2. Compte badge in JS ---")
for i, l in enumerate(lines):
    if "compteBadgeHtml" in l or "compte-badge" in l:
        print(f"L{i+1}: {l.strip()[:100]}")

print("\n--- 3. Mobile card creation in JS ---")
for i, l in enumerate(lines):
    if "mobile-tx-card" in l or "mobile-tx-icon-bubble" in l:
        print(f"L{i+1}: {l.strip()[:100]}")

print("\n--- 4. Amounts in JS ---")
for i, l in enumerate(lines):
    if "mobile-tx-amount" in l:
        print(f"L{i+1}: {l.strip()[:100]}")

