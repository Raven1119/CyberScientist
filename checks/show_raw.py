import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
s = io.open(r'C:\Users\wmywb\AppData\Local\Temp\kimi-raw.txt', encoding='utf-8', errors='replace').read()
i = s.find('[kimi-brain raw')
print(s[i:i + 1600])
