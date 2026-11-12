with open('chat_grow/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(4890, 4920):
    print(f'{i+1}: {lines[i]}', end='')

