"""Browser acceptance test runner for Myslyx.

Spawns its own app subprocess on a free port (single process, quiet logging),
then runs every suite in the configured browsers. Requires the Playwright
Python package and its browsers:

    pip install -r dev-requirements.txt
    playwright install chromium firefox webkit
    python -m tests.runner            # defaults: chromium + firefox
    python -m tests.runner -b webkit  # explicit third browser

WebKit is NOT in the default set: Playwright's prebuilt WebKit targets older
Debian/Ubuntu libs (ICU 74, libjpeg 8, libbacktrace 0) that Fedora 44 does not
ship (ICU 77, libjpeg-turbo 62), so it cannot launch there. Pass `-b webkit`
only on a host that provides those libraries.
"""

import argparse
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

import tests.helpers  # noqa: F401  (keeps per-suite `from tests import ...` importable)
from tests.test_header import HEADER_SUITES
from tests.test_multiedit import MULTIEDIT_SUITES
from tests.test_plugins import PLUGIN_SUITES, prepare_user_plugin_layout
from tests.test_smoke import SMOKE_SUITES

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'main.py'
ARTIFACTS = ROOT / 'tests' / 'artifacts'
DEFAULT_BROWSERS = ['chromium', 'firefox']
ALL_SUITES = MULTIEDIT_SUITES + HEADER_SUITES + SMOKE_SUITES + PLUGIN_SUITES


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


async def wait_for_server(port: int, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/editor', timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(0.3)
    raise RuntimeError(f'app did not become ready on port {port}')


def start_server(port: int) -> subprocess.Popen:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, WB_TESTING='1')
    cfg_dir = prepare_user_plugin_layout()
    # Point the user plugins directory at the throwaway layout (Linux uses
    # XDG_CONFIG_HOME, Windows APPDATA; macOS is HOME-based and not covered).
    env['XDG_CONFIG_HOME'] = str(cfg_dir)
    env['APPDATA'] = str(cfg_dir)
    log = open(ARTIFACTS / 'server.log', 'wb')
    proc = subprocess.Popen(
        [sys.executable, str(SERVER), '-p', str(port), '--no-reload'],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    # Keep the file handle alive so the child's output is not lost.
    proc._log = log  # type: ignore[attr-defined]
    proc._cfg_dir = cfg_dir  # type: ignore[attr-defined]
    return proc


async def run_suite(browser, page, suite_name, fn, port):
    """Run a single suite body against a freshly loaded page."""
    msgs = []
    page.on('console', lambda m: msgs.append(m.text) if m.type == 'error' else None)
    await page.goto(f'http://127.0.0.1:{port}/editor?reset=1', wait_until='load')
    await page.wait_for_timeout(6000)
    await page.wait_for_selector('.wb-file-tab', timeout=20000)
    try:
        await fn(page, msgs)
        return (browser, suite_name, 'PASS', '')
    except Exception as exc:  # pragma: no cover - failure path
        return (browser, suite_name, 'FAIL', f'{type(exc).__name__}: {exc}')


async def run_browser(browser_type: str, port: int) -> list:
    results = []
    async with async_playwright() as pw:
        browser = await pw[browser_type].launch()
        try:
            for suite_name, fn in ALL_SUITES:
                context = await browser.new_context(service_workers='block')
                page = await context.new_page()
                try:
                    results.append(await run_suite(browser_type, page, suite_name, fn, port))
                finally:
                    await context.close()
        finally:
            await browser.close()
    return results


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--browsers', nargs='*', default=DEFAULT_BROWSERS)
    parser.add_argument('-p', '--port', type=int, default=0)
    args = parser.parse_args()

    port = args.port or free_port()
    proc = start_server(port)
    try:
        await wait_for_server(port)
        all_results = []
        for browser_type in args.browsers:
            try:
                all_results += await run_browser(browser_type, port)
            except Exception as exc:  # pragma: no cover - launch failure path
                reason = f'{type(exc).__name__}: {exc}'.replace('\n', ' ')[:160]
                all_results += [(browser_type, f'{dep}', 'SKIP', reason)
                                for dep in ('all suites (browser unavailable)',)]
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        try:
            proc._log.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        shutil.rmtree(proc._cfg_dir, ignore_errors=True)  # type: ignore[attr-defined]

    width = max(len(name) for _, name, _, _ in all_results)
    for browser, name, status, detail in all_results:
        line = f'[{browser:9}] {name:<{width}}  {status}'
        if detail:
            line += f'  --  {detail}'
        print(line)

    failed = [r for r in all_results if r[2] == 'FAIL']
    print(f'\n{len(all_results) - len(failed)}/{len(all_results)} suites passed')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))