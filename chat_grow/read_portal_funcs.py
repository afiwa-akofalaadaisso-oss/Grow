content = open('chat_grow/templates/dashboard.html', encoding='utf-8').read()
idx = content.find('function openPortalView()')
print(content[idx:idx+1500])

