"""Debug runner: run a filtered subset of acceptance suites against one browser."""

import asyncio
import os
import signal
import sys
import time
import traceback

from playwright.async_api import Browser, BrowserContext, async_playwright

from tests.runner import ALL_SUITES, free_port, start_server, wait_for_server

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
    filters = [arg for arg in sys.argv[1:] if arg != "-f"]

    browser_type = DEFAULT_BROWSER
    if "-b" in sys.argv:
        index = sys.argv.index("-b")
        try:
            browser_type = sys.argv[index + 1]
        except IndexError:
            raise SystemExit("-b requires a browser name")

    if "-f" in sys.argv:
        index = sys.argv.index("-f")
        filters = sys.argv[index + 1:]

    wanted = [
        (name, fn)
        for name, fn in ALL_SUITES
        if any(f in name for f in filters)
    ]

    if not wanted:
        wanted = ALL_SUITES

    port = free_port()
    proc = start_server(port)

    try:
        await wait_for_server(port)

        async with async_playwright() as pw:
            browser: Browser | None = None

            try:
                browser = await pw[browser_type].launch()

                context: BrowserContext | None = None

                try:
                    context = await browser.new_context(
                        service_workers="block",
                        accept_downloads=True,
                    )

                    page = await context.new_page()

                    msgs: list[str] = []
                    page.on(
                        "console",
                        lambda message: (
                            msgs.append(message.text)
                            if message.type == "error"
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

                    for name, fn in wanted:
                        msgs.clear()

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
                            print(f"PASS  {name}")
                        except Exception as exc:
                            print(
                                f"FAIL  {name}  -- "
                                f"{type(exc).__name__}: {exc}"
                            )
                            traceback.print_exc()

                    print("\nconsole errors:", msgs)

                finally:
                    if context is not None:
                        try:
                            await context.close()
                        except Exception:
                            traceback.print_exc()

            finally:
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        traceback.print_exc()

        return 0

    finally:
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

        _kill_orphan_test_browsers()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
