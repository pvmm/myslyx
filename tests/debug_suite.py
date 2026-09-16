"""Debug runner: run a filtered subset of acceptance suites against one browser.

Shares suite definitions with `tests/runner.py` but keeps the per-suite
isolation (fresh context/page), console-error capture, server management and
cleanup local so nothing lingers after a run.
"""

import asyncio
import os
import signal
import sys
import time
import traceback

from playwright.async_api import async_playwright

from tests.runner import (
    ALL_SUITES,
    env_satisfiable,
    free_port,
    neutralize_display_env,
    start_server,
    wait_for_server,
)

DEFAULT_BROWSER = "chromium"


def _kill_orphan_test_browsers() -> None:
    """Terminate any playwright-launched test browsers still lingering.

    Targets non-GUI browser processes whose command line contains a localhost
    test URL (``http://127.0.0.1:``). The user's regular browser is never
    affected because its argv never contains a localhost test URL.
    """
    try:
        import subprocess

        out = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,args"], text=True, timeout=5
        )
    except Exception:
        return

    lines = out.strip().splitlines()
    children: dict[int, list[int]] = {}
    browser_pids: set[int] = set()
    target_parents: set[int] = set()

    for line in lines[1:]:
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        args = parts[2]
        children.setdefault(ppid, []).append(pid)
        if "firefox" in args or "chrome" in args:
            browser_pids.add(pid)
        if (
            ("firefox" in args or "chrome" in args)
            and "http://127.0.0.1:" in args
            and "-contentproc" not in args
            and "crashhelper" not in args
        ):
            target_parents.add(pid)

    to_kill: set[int] = set()
    queue = list(target_parents)
    while queue:
        pid = queue.pop(0)
        if pid in to_kill:
            continue
        to_kill.add(pid)
        for child_pid in children.get(pid, []):
            if child_pid in browser_pids:
                queue.append(child_pid)

    if not to_kill:
        return

    for pid in to_kill:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    time.sleep(0.25)

    for pid in to_kill:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


async def main() -> int:
    neutralize_display_env()
    # CLI: [-b firefox|chromium] [-f filter...] — each -f consumes every
    # following token until the next option, so " -f a -f b" and " -f a b"
    # both work (the old "everything after the first -f" grab turned a second
    # "-f" into a filter that substring-matched every suite name containing
    # "-f", e.g. download-all-files).
    raw = sys.argv[1:]
    filters: list[str] = []
    browser_type = DEFAULT_BROWSER
    i = 0
    while i < len(raw):
        arg = raw[i]
        if arg == "-b" and i + 1 < len(raw):
            browser_type = raw[i + 1]
            i += 2
            continue
        if arg == "-f":
            i += 1
            while i < len(raw) and raw[i] not in ("-f", "-b"):
                filters.append(raw[i])
                i += 1
            continue
        filters.append(arg)
        i += 1

    wanted = [(name, fn, env) for name, fn, env in ALL_SUITES if not filters or any(f in name for f in filters)]

    # Group by the server environment they need (None = the default server).
    phases: list[tuple[dict | None, list]] = [(None, [])]
    phases_by_env: dict[tuple, tuple[dict, list]] = {}
    for name, fn, env in wanted:
        if not env:
            phases[0][1].append((name, fn))
        else:
            key = tuple(sorted(env.items()))
            if key not in phases_by_env:
                phases_by_env[key] = (env, [])
            phases_by_env[key][1].append((name, fn))
    for _key, (env, entries) in phases_by_env.items():
        phases.append((env, entries))

    ok_total = 0
    failed = 0
    procs = []

    try:
        for extra_env, suite_list in phases:
            if not suite_list:
                continue

            ok, reason = env_satisfiable(extra_env)
            if not ok:
                for name, _fn in suite_list:
                    print(f"SKIP  {name}  --  {reason}")
                continue

            port = free_port()
            procs.append(start_server(port, extra_env=extra_env))
            await wait_for_server(port)

            async with async_playwright() as pw:
                try:
                    browser = await pw[browser_type].launch(headless=True)
                except Exception:
                    traceback.print_exc()
                    for name, _fn in suite_list:
                        print(f"SKIP  {name}  --  browser unavailable")
                    continue
                try:
                    for name, fn in suite_list:
                        msgs: list[str] = []
                        try:
                            context = await browser.new_context(
                                service_workers="block",
                                accept_downloads=True,
                            )
                        except Exception:
                            traceback.print_exc()
                            failed += 1
                            print(f"FAIL  {name}  --  context creation failed")
                            continue
                        try:
                            page = await context.new_page()
                            page.on(
                                "console",
                                lambda m, msgs=msgs: (
                                    msgs.append(m.text)
                                    if m.type == "error"
                                    else None
                                ),
                            )
                            await page.goto(
                                f"http://127.0.0.1:{port}/editor?reset=1",
                                wait_until="load",
                            )
                            await page.wait_for_timeout(5000)
                            await page.wait_for_selector(
                                ".wb-file-tab",
                                timeout=30000,
                            )
                            try:
                                await fn(page, msgs)
                                ok_total += 1
                                print(f"PASS  {name}")
                            except Exception as exc:
                                failed += 1
                                print(
                                    f"FAIL  {name}  -- "
                                    f"{type(exc).__name__}: {exc}"
                                )
                                traceback.print_exc()
                        finally:
                            await context.close()
                        print(f"      console errors: {msgs}")
                finally:
                    await browser.close()

        print(f"\n{ok_total} passed, {failed} failed")
        return 0 if failed == 0 else 1
    finally:
        for proc in procs:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    traceback.print_exc()
            try:
                proc._log.close()
            except (AttributeError, OSError):
                pass
            try:
                import shutil

                shutil.rmtree(proc._cfg_dir, ignore_errors=True)
            except Exception:
                traceback.print_exc()

        _kill_orphan_test_browsers()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))