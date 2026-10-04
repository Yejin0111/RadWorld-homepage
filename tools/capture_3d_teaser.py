"""Capture a rotating 3D rendering of a generated volume for the teaser row.

The volume is fully synthetic, so surface or bone renderings show no real person.
Serves the page itself on a free local port. Needs Playwright with Chromium.
Usage: python3 tools/capture_3d_teaser.py [tab index] [preset: bone|soft|surface] [output .webp] [group]
Current teaser: python3 tools/capture_3d_teaser.py 1 bone assets/img/teaser/render3d_abdomen_bone.webp generation
"""
import asyncio, functools, http.server, io, sys, threading
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright
from serve import NoCacheHandler
CASE_TAB = int(sys.argv[1]) if len(sys.argv) > 1 else 0
PRESET = sys.argv[2] if len(sys.argv) > 2 else "bone"
OUT = sys.argv[3] if len(sys.argv) > 3 else "assets/img/teaser/render3d_chest_bone.webp"
GROUP = sys.argv[4] if len(sys.argv) > 4 else "report"


class QuietHandler(NoCacheHandler):
    def log_message(self, *args):
        pass


async def main():
    root = Path(__file__).resolve().parents[1]
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width": 1100, "height": 1000}, device_scale_factor=1)
        await pg.goto(f"http://127.0.0.1:{httpd.server_address[1]}/", wait_until="networkidle")
        rp = f'[data-group="{GROUP}"]'
        await pg.locator(rp).scroll_into_view_if_needed()
        await pg.locator(f"{rp} .tab").nth(CASE_TAB).click()
        await pg.locator(f"{rp} .load-btn").click()
        await pg.wait_for_function(f"!document.querySelector('{rp} .load-cover')", timeout=60000)
        await pg.locator(f"{rp} [data-role='3d']").click()
        await pg.wait_for_function("document.querySelector('#render3d .render3d-status').hidden === true", timeout=90000)
        await pg.keyboard.press("Escape")
        await pg.evaluate("""() => { const P = window.niivue.Niivue.prototype; const add = P.addVolume; P.addVolume = function (v) { window.__nv = this; return add.call(this, v); }; }""")
        await pg.locator(f"{rp} [data-role='3d']").click()
        await pg.wait_for_function("document.querySelector('#render3d .render3d-status').hidden === true && window.__nv", timeout=90000)
        await pg.locator(f"#render3d [data-key={PRESET}]").click()
        await pg.wait_for_timeout(800)
        box = await pg.locator("#render3d canvas").bounding_box()
        frames = []
        for az in range(0, 360, 10):
            await pg.evaluate(f"() => {{ window.__nv.setRenderAzimuthElevation({az + 90}, 10); window.__nv.drawScene(); }}")
            await pg.wait_for_timeout(120)
            png = await pg.screenshot(clip=box)
            frames.append(Image.open(io.BytesIO(png)).convert("RGB"))
        # crop to the rendered content (non-black area over all frames)
        import numpy as np
        acc = np.zeros((frames[0].height, frames[0].width), bool)
        for f in frames: acc |= np.asarray(f).max(2) > 12
        ys, xs = np.where(acc)
        pad = 12
        x0, x1, y0, y1 = max(0, xs.min() - pad), min(frames[0].width, xs.max() + pad), max(0, ys.min() - pad), min(frames[0].height, ys.max() + pad)
        side = max(x1 - x0, y1 - y0); cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        crop = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
        frames = [f.crop(crop).resize((420, 420), Image.LANCZOS) for f in frames]
        frames[0].save(OUT, "WEBP", save_all=True, append_images=frames[1:], duration=90, loop=0, quality=80, method=6)
        frames[3].save(OUT.replace(".webp", "_still.webp"), "WEBP", quality=85)
        print(OUT, len(frames), "frames")
        await b.close()
asyncio.run(main())
