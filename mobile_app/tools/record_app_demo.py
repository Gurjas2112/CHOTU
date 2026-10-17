#!/usr/bin/env python3
"""Record the CHOTU Flutter app demo tour (demo data only - no robot needed).

    cd mobile_app/chotu_app
    flutter build web --release --web-renderer html --dart-define=TOUR=true
    cd ../..
    python mobile_app/tools/record_app_demo.py

Serves build/web locally, opens it in headless Chromium at a phone viewport,
saves a screenshot every time the tour announces a step in the page title
("CHOTU · 05_live_map_coverage") and records the whole session to
mobile_app/app_screenshot_screen_recording/chotu_app_full_demo.mp4.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WEB = os.path.join(ROOT, "mobile_app", "chotu_app", "build", "web")
OUT = os.path.join(ROOT, "mobile_app", "app_screenshot_screen_recording")
VIEW = {"width": 430, "height": 932}       # iPhone 15 Pro Max CSS viewport
PORT = 8765


def serve() -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=WEB)
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    if not os.path.exists(os.path.join(WEB, "index.html")):
        print("build/web missing - run flutter build web --dart-define=TOUR=true first")
        return 1
    os.makedirs(OUT, exist_ok=True)
    vid_dir = os.path.join(OUT, "_video_tmp")
    shutil.rmtree(vid_dir, ignore_errors=True)
    srv = serve()
    steps = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2, is_mobile=True, has_touch=True,
                                  record_video_dir=vid_dir, record_video_size=VIEW)
        # Playwright records at CSS-pixel size (it ignores device_scale_factor); a larger
        # record_video_size only pads the page into the top-left corner. Upscale in ffmpeg instead.
        page = ctx.new_page()
        t0 = time.time()
        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
        last = ""
        while time.time() - t0 < 300:
            title = page.title()
            if title != last and title.startswith("CHOTU · "):
                last = title
                step = title.split("· ", 1)[1].strip()
                if step == "END":
                    break
                time.sleep(0.35)          # let the frame settle (animations)
                path = os.path.join(OUT, f"{step}.png")
                page.screenshot(path=path)
                steps.append({"step": step, "t": round(time.time() - t0, 1)})
                print(f"{time.time() - t0:6.1f}s  {step}")
            time.sleep(0.1)
        video_path = page.video.path()
        ctx.close()
        browser.close()
    srv.shutdown()
    mp4 = os.path.join(OUT, "chotu_app_full_demo.mp4")
    # 2x Lanczos upscale to a phone-like 860x1864, constant 30 fps (the screencast is variable-rate)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
                    "-vf", f"scale={VIEW['width'] * 2}:{VIEW['height'] * 2}:flags=lanczos,fps=30",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", mp4], check=True)
    shutil.rmtree(vid_dir, ignore_errors=True)
    with open(os.path.join(OUT, "steps.json"), "w") as f:
        json.dump(steps, f, indent=2)
    print(f"{len(steps)} screenshots + {mp4}")
    return 0 if steps else 1


if __name__ == "__main__":
    sys.exit(main())
