import re

file_path = r'c:\Users\Shivam kumar\OneDrive\Desktop\Talkly\backend\server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'allow_origins=\[.*?\]', 'allow_origins=["*"]', content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("CORS updated!")
