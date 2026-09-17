import json, io, sys
d = json.load(io.open(sys.argv[1], encoding="utf-8"))
out = []
def walk(n, depth=0):
    role = n.get("role", "")
    name = (n.get("name") or "")[:60]
    ref = n.get("ref", "")
    if role in ("button", "textbox", "checkbox", "tab", "dialog"):
        out.append(f"{ref:6} {role:10} {name}")
    for c in n.get("children", []):
        walk(c, depth + 1)
walk({"children": d["data"]["tree"]})
io.open(sys.argv[2], "w", encoding="utf-8").write("\n".join(out))
