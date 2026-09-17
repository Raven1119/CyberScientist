import asyncio, json, sys, io
sys.path.insert(0, r"C:\Users\wmywb\PycharmProjects\CyberScientist")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from src.cyberscientist.brains.kimi import KimiBrain

async def main():
    b = KimiBrain(model="kimi-code/k3")
    s = await b.open({"working_directory": None})
    print("session:", s.session_id)
    rpc = b.rpc
    msgs = []

    async def watch():
        async for m in rpc.notifications():
            msgs.append(m)

    w = asyncio.create_task(watch())
    reqs = []
    async def collect_reqs():
        async for r in rpc.server_requests():
            reqs.append(r)
    rq = asyncio.create_task(collect_reqs())

    resp = await rpc.request("session/prompt",
        {"sessionId": s.session_id,
         "prompt": [{"type": "text", "text": "只回复两个字：收到。不要调用任何工具。"}]},
        timeout=300)
    print("prompt response:", json.dumps(resp, ensure_ascii=False)[:200])
    w.cancel(); rq.cancel()
    print("--- notifications:", len(msgs))
    for m in msgs[:12]:
        print(json.dumps(m, ensure_ascii=False)[:280])
    print("--- server requests:", len(reqs))
    for r in reqs[:4]:
        print(json.dumps(r, ensure_ascii=False)[:280])
    await b.close(s)

asyncio.run(main())
