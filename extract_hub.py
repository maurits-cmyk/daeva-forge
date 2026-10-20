import json, sys

src = open(sys.argv[1], encoding='utf8').read()
start = src.find("JSON.parse('") + len("JSON.parse('")
j = start
while True:
    j = src.find("')", j)
    k, bs = j - 1, 0
    while src[k] == chr(92):
        bs += 1
        k -= 1
    if bs % 2 == 0:
        break
    j += 1
raw = src[start:j]
# JS single-quoted string -> python: handle \' \\ \n \uXXXX \xXX
out, i = [], 0
while i < len(raw):
    c = raw[i]
    if c == chr(92):
        n = raw[i + 1]
        if n == 'u':
            out.append(chr(int(raw[i + 2:i + 6], 16))); i += 6; continue
        if n == 'x':
            out.append(chr(int(raw[i + 2:i + 4], 16))); i += 4; continue
        out.append({'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f'}.get(n, n)); i += 2; continue
    out.append(c); i += 1
d = json.loads(''.join(out))
json.dump(d, open(sys.argv[2], 'w', encoding='utf8'), ensure_ascii=False)
print(list(d.keys()))
