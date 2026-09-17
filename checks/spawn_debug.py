import asyncio, os, shutil, sys

exe = shutil.which("prime-agent")
print("which:", exe)

ALLOW = {k: os.environ[k] for k in
         ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME",
          "APPDATA") if k in os.environ}

async def try_spawn(name, argv, env):
    try:
        p = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env=env)
        out, _ = await asyncio.wait_for(p.communicate(), timeout=20)
        print(f"{name}: OK ->", out.decode(errors='replace').strip()[:80])
    except Exception as e:
        print(f"{name}: FAIL {e.__class__.__name__}: {str(e)[:120]}")

async def main():
    await try_spawn("fullpath-inherit", [exe, "--version"], None)
    await try_spawn("fullpath-allow", [exe, "--version"], ALLOW)
    await try_spawn("cmd-wrap-allow", ["cmd", "/c", exe, "--version"], ALLOW)
    comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    await try_spawn("comspec-wrap-allow", [comspec, "/c", exe, "--version"], ALLOW)
    node = shutil.which("node")
    cli = os.path.join(os.path.dirname(exe), "node_modules", "@earendil-works", "pi-coding-agent", "dist", "bundle", "cli.js")
    print("cli.js exists:", os.path.exists(cli), cli)
    if node and os.path.exists(cli):
        await try_spawn("node-cli-allow", [node, cli, "--version"], ALLOW)

async def main2():
    exe = shutil.which("prime-agent")
    ALLOW = {k: os.environ[k] for k in
             ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME",
              "APPDATA") if k in os.environ}
    out_dir = r"C:\Users\wmywb\PycharmProjects\CyberScientist\workspace\runs\prime-probe"
    os.makedirs(out_dir, exist_ok=True)
    try:
        p = await asyncio.create_subprocess_exec(
            "cmd", "/c", exe, "--mode", "rpc", "--no-session",
            "--session-dir", out_dir + "\\session",
            "--provider", "openrouter", "--model", "GLM-5.2-Free-OR",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, env=ALLOW, cwd=out_dir)
        out, _ = await asyncio.wait_for(p.communicate(), timeout=15)
        print("full-args-cwd:", "OK ->", out.decode(errors='replace').strip()[:200])
    except Exception as e:
        print("full-args-cwd: FAIL", e.__class__.__name__, str(e)[:150])

asyncio.run(main())
asyncio.run(main2())
