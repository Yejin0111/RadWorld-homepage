"""End-to-end check of the project page in Chromium, WebKit (Safari) and Firefox.

Usage:
  python3 -m playwright install chromium webkit firefox   # once
  python3 tools/test_page.py                              # all engines
  python3 tools/test_page.py --engines chromium --quick

Starts its own static server, exercises every explorer setting, the 3D dialog, the visual
Turing test, the charts and the site-config switches, and checks that canvases actually
contain image data. Exit code 1 if anything fails.
"""
import argparse
import asyncio
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "assets/js/site-config.js").read_text()
results = []


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


CANVAS_MEAN = """(sel) => {
  const cs = [...document.querySelectorAll(sel)].filter((c) => !c.hidden && c.width > 0);
  return cs.map((c) => {
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let s = 0, n = 0;
    for (let i = 0; i < d.length; i += 4 * 97) { s += d[i]; n++; }
    return n ? s / n : 0;
  });
}"""


async def wait_loaded(pg, scope, timeout=60000):
    await pg.wait_for_function(
        f"(() => {{ const r = document.querySelector('{scope}'); return r && !r.querySelector('.load-cover') && r.querySelector('.pane canvas:not([hidden])'); }})()",
        timeout=timeout)
    await pg.wait_for_timeout(400)


async def canvases_have_image(pg, scope):
    means = await pg.evaluate(CANVAS_MEAN, f"{scope} .pane canvas")
    return bool(means) and all(m > 3 for m in means), means


# The visible tooltip as text per rendered line (text nodes grouped by their line box), so the test
# sees what the reader sees: "HA-GAN 199.0MAISI 86.6" on one line fails.
TIP_LINES = """() => {
  const t = document.querySelector('.chart-tip');
  if (!t || t.hidden) return null;
  const lines = new Map();
  const walker = document.createTreeWalker(t, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!n.textContent.trim()) continue;
    const r = document.createRange();
    r.selectNodeContents(n);
    for (const rc of r.getClientRects()) {
      const k = Math.round(rc.top + rc.height / 2);
      const near = [...lines.keys()].find((y) => Math.abs(y - k) < 4);
      const key = near === undefined ? k : near;
      lines.set(key, [...(lines.get(key) || []), n.textContent.trim()]);
    }
  }
  return [...lines.entries()].sort((a, b) => a[0] - b[0]).map(([, parts]) => parts.join(' | '));
}"""


async def tip_shows_one_method_per_line(pg, figure):
    """Every method of the chart sits on its own tooltip line, together with its value."""
    names = await pg.evaluate("(f) => [...f.querySelectorAll('.chart-legend .key')].map((k) => k.textContent.trim())", figure)
    lines = await pg.evaluate(TIP_LINES) or []
    per_line = [[n for n in names if n in line] for line in lines]
    ok = (len(names) >= 2 and all(len(p) <= 1 for p in per_line)
          and sorted(n for p in per_line for n in p) == sorted(names)
          and all(any(ch.isdigit() for ch in line) for line, p in zip(lines, per_line) if p))
    return ok, lines


async def new_page(browser, url, mobile=False, config=None):
    ctx = await browser.new_context(
        viewport={"width": 390, "height": 844} if mobile else {"width": 1280, "height": 900},
        device_scale_factor=2 if mobile else 1, has_touch=mobile, is_mobile=mobile and browser.browser_type.name != "firefox")
    pg = await ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    pg.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url} {r.failure}"))
    pg.on("response", lambda r: errors.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None)
    if config is not None:
        await pg.route("**/assets/js/site-config.js",
                       lambda r: r.fulfill(status=200, content_type="application/javascript", body=config))
    await pg.goto(url, wait_until="networkidle")
    return pg, errors


async def press(pg, locator, mobile):
    if mobile:
        await locator.tap()
    else:
        await locator.click()


async def open_cap(pg, cap, mobile):
    """Show a capability: click its tab if the section has tabs, otherwise just scroll to its viewer.
    Returns the stage selector."""
    tab = pg.locator(f'.cap-tabs [data-cap="{cap}"]')
    if await tab.count():
        await tab.scroll_into_view_if_needed()
        await press(pg, tab, mobile)
        await pg.wait_for_timeout(150)
    stage = f'.explorer-stage[data-group="{cap}"]'
    await pg.locator(stage).scroll_into_view_if_needed()
    return stage


async def load_stage(pg, stage, mobile):
    """Each section's viewer waits for a click before it downloads volumes."""
    btn = pg.locator(f"{stage} .load-btn")
    if await btn.count():
        await press(pg, btn, mobile)
    await wait_loaded(pg, stage)


async def run_engine(p, name, url, quick):
    print(f"\n== {name}")
    browser = await getattr(p, name).launch()
    for mobile in ([False] if quick or name == "firefox" else [False, True]):
        tag = f"{name}{' mobile' if mobile else ''}"
        pg, errors = await new_page(browser, url, mobile)
        overflow = await pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(f"{tag}: no horizontal overflow", overflow <= 0, f"{overflow}px")
        check(f"{tag}: 16 authors listed", await pg.locator(".authors > span").count() == 16)
        charts = await pg.locator("figure.chart.has-bars").count()
        check(f"{tag}: result charts drawn", charts == 10, f"{charts} charts")
        km = await pg.evaluate("() => [...document.querySelectorAll('figure.km')].map((f) => f.querySelectorAll('.km-plot path').length)")
        check(f"{tag}: Kaplan-Meier curves drawn for both cohorts", km == [2, 2], str(km))
        tones = await pg.evaluate("""() => [...document.querySelectorAll('.hbar .fill, .v-bar, .lolli .dot')].map((m) => getComputedStyle(m).backgroundColor)""")
        paper = {"rgb(180, 192, 228)", "rgb(120, 132, 180)", "rgb(72, 72, 120)", "rgb(240, 192, 204)"}
        check(f"{tag}: bars and lollipops use the paper's figure colours", tones and set(tones) <= paper, str(sorted(set(tones))))
        groups = await pg.locator(".v-group").count()
        # FID 8, organ Dice 16, abnormality AUC 13, tumor Dice 8, report metrics by region 12, PSNR 5, T1CE 3,
        # reader study 4, C-index 2
        check(f"{tag}: grouped bars and lollipops drawn", groups == 8 + 16 + 13 + 8 + 12 + 5 + 3 + 4 + 2, f"{groups} groups")
        credits = await pg.locator("#data-credits li").count()
        licenses = await pg.locator('#data-credits a[href^="https://creativecommons.org/licenses/"]').count()
        check(f"{tag}: image credits list the source datasets with license links", credits >= 10 and licenses >= credits - 1,
              f"{credits} datasets, {licenses} license links")
        labels = await pg.locator(".v-val, .m-val, .hbar .val").count()
        check(f"{tag}: charts carry no value labels", labels == 0, f"{labels} labels")
        check(f"{tag}: no table toggle on charts", await pg.locator(".chart-toggle").count() == 0)
        narrow = await pg.evaluate("() => [...document.querySelectorAll('figure.chart.has-bars')].map((f) => f.classList.contains('is-narrow'))")
        if mobile:
            check(f"{tag}: every chart uses the phone layout", narrow and all(narrow), str(narrow))
            target = pg.locator("figure.chart.is-narrow .m-group").first
            await target.scroll_into_view_if_needed()
            await press(pg, target, mobile)
            await pg.wait_for_timeout(200)
            tip = await pg.evaluate("() => { const t = document.querySelector('.chart-tip'); return t && !t.hidden ? t.textContent : ''; }")
            check(f"{tag}: tapping a chart shows its values", "RadWorld" in tip, tip[:80])
            fig = await target.evaluate_handle("(g) => g.closest('figure')")
            ok, lines = await tip_shows_one_method_per_line(pg, fig)
            check(f"{tag}: tooltip lists one method per line", ok, str(lines))
        else:
            check(f"{tag}: desktop charts keep the full layout", narrow and not any(narrow), str(narrow))
            widths = await pg.evaluate("() => [...document.querySelectorAll('#synthetic .v-bar')].map((b) => b.getBoundingClientRect().width)")
            check(f"{tag}: the synthetic-data charts share one bar width", widths and max(widths) - min(widths) <= 1,
                  f"{min(widths):.1f} to {max(widths):.1f}px" if widths else "no bars")
            target = pg.locator("figure.chart .v-group").first
            await target.scroll_into_view_if_needed()
            await target.hover()
            await pg.wait_for_timeout(150)
            fig = await target.evaluate_handle("(g) => g.closest('figure')")
            ok, lines = await tip_shows_one_method_per_line(pg, fig)
            check(f"{tag}: tooltip lists one method per line", ok, str(lines))
            await pg.mouse.move(1, 1)
        if not mobile:
            edges = await pg.evaluate("""() => [...document.querySelectorAll('.strip, .section-head, .story, .para, .explorer, .evidence, .feature, #turing-app, .cite-grid')]
              .map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right)]; })""")
            check(f"{tag}: all blocks share the same left and right edges", len({tuple(e) for e in edges}) == 1, str(edges[:2]))

        # explorer: generation (first capability, loaded by clicking)
        gp = '.explorer-stage[data-group="generation"]'
        await pg.locator(gp).scroll_into_view_if_needed()
        await press(pg, pg.locator(f"{gp} .load-btn"), mobile)
        await wait_loaded(pg, gp)
        ok, means = await canvases_have_image(pg, gp)
        check(f"{tag}: generated CT draws three planes", ok and len(means) == 3, str([round(m) for m in means]))
        await press(pg, pg.locator(f"{gp} .tab", has_text="Brain MRI (T1CE)"), mobile)
        await wait_loaded(pg, gp)
        ok, means = await canvases_have_image(pg, gp)
        check(f"{tag}: generated MRI draws three planes", ok and len(means) == 3)

        # explorer: report to CT (loads automatically after the first load)
        rp = await open_cap(pg, "report", mobile)
        await wait_loaded(pg, rp)
        ok, means = await canvases_have_image(pg, rp)
        check(f"{tag}: report case loads automatically and draws three planes", ok and len(means) == 3)
        check(f"{tag}: report findings are shown", "ground-glass" in await pg.locator(f"{rp} .case-text").inner_text())
        before = await pg.locator(f"{rp} [data-role=slice-label]").inner_text()
        await pg.locator(f"{rp} [data-role=slice]").evaluate("(el) => { el.value = String(Number(el.max) - 5); el.dispatchEvent(new Event('input', { bubbles: true })); }")
        await pg.wait_for_timeout(200)
        after = await pg.locator(f"{rp} [data-role=slice-label]").inner_text()
        check(f"{tag}: slice slider moves the axial slice", before != after, f"{before} -> {after}")
        if not mobile:
            box = await pg.locator(f"{rp} .pane canvas").nth(1).bounding_box()
            await pg.mouse.click(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3)
            await pg.wait_for_timeout(150)
            clicked = await pg.locator(f"{rp} [data-role=slice-label]").inner_text()
            check(f"{tag}: clicking the coronal plane moves the crosshair", clicked != after, f"{after} -> {clicked}")
            ab = await pg.locator(f"{rp} .pane canvas").nth(0).bounding_box()
            await pg.mouse.move(ab["x"] + ab["width"] / 2, ab["y"] + ab["height"] / 2)
            await pg.mouse.wheel(0, 300)
            await pg.wait_for_timeout(200)
            wheeled = await pg.locator(f"{rp} [data-role=slice-label]").inner_text()
            check(f"{tag}: mouse wheel changes the slice", wheeled != clicked, f"{clicked} -> {wheeled}")
        await press(pg, pg.locator(f"{rp} [data-window=lung]"), mobile)
        check(f"{tag}: window preset toggles", await pg.locator(f"{rp} [data-window=lung]").get_attribute("aria-pressed") == "true")
        await press(pg, pg.locator(f"{rp} .tab").last, mobile)
        await wait_loaded(pg, rp)
        ok, _ = await canvases_have_image(pg, rp)
        check(f"{tag}: switching cases loads the next case", ok)

        # explorer: CT from an organ label map (loads directly, a volume was already loaded)
        mp = await open_cap(pg, "mask", mobile)
        await wait_loaded(pg, mp)
        ok, means = await canvases_have_image(pg, mp)
        colored = await pg.evaluate("""(sel) => { const c = document.querySelector(sel + ' .pane canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
          let n = 0; for (let i = 0; i < d.length; i += 4 * 13) { const mx = Math.max(d[i], d[i + 1], d[i + 2]), mn = Math.min(d[i], d[i + 1], d[i + 2]); if (mx - mn > 60) n++; } return n; }""", mp)
        check(f"{tag}: organ mask pane in colour next to the generated CT", ok and len(means) == 2 and colored > 200, f"{colored} coloured samples")

        # explorer: translation and 3D rendering
        tr = await open_cap(pg, "translation", mobile)
        await load_stage(pg, tr, mobile)
        ok, means = await canvases_have_image(pg, tr)
        check(f"{tag}: translation draws three panes", ok and len(means) == 3)
        shown = await pg.locator(tr).inner_text()
        check(f"{tag}: viewer captions name no datasets", "SynthRAD" not in shown and "CC BY" not in shown, shown[:80])
        if mobile:
            xs = await pg.evaluate(f"""() => {{ const c = document.querySelector('{tr} .controls'); const x0 = c.getBoundingClientRect().left;
              return [...c.querySelectorAll('.group')].map((g) => {{ const k = g.classList.contains('opts') ? g.firstElementChild : g.querySelector('.chip, input[type=range]');
                return Math.round(k.getBoundingClientRect().left - x0); }}); }}""")
            check(f"{tag}: viewer control rows line up", len(xs) >= 4 and len(set(xs)) == 1, str(xs))
        await press(pg, pg.locator(f"{tr} [data-zoom=in]"), mobile)
        await press(pg, pg.locator(f"{tr} [data-plane=coronal]"), mobile)
        await pg.wait_for_timeout(250)
        ok, _ = await canvases_have_image(pg, tr)
        lbl = await pg.locator(f"{tr} [data-role=slice-label]").inner_text()
        check(f"{tag}: zoom and coronal plane", ok and lbl.startswith("Coronal"), lbl)
        await press(pg, pg.locator(f"{tr} [data-plane=sagittal]"), mobile)
        await pg.wait_for_timeout(200)
        ok, _ = await canvases_have_image(pg, tr)
        check(f"{tag}: sagittal plane in compare view", ok)
        if not mobile:
            await pg.locator(f"{tr} [data-role='3d']").click()
            try:
                await pg.wait_for_function("document.querySelector('#render3d .render3d-status').hidden === true", timeout=60000)
                presets = await pg.locator("#render3d [data-role=presets] button").all_inner_texts()
                check(f"{tag}: 3D rendering opens, bone preset only for head and neck", presets == ["Bone"], str(presets))
                cb = await pg.locator("#render3d canvas").bounding_box()
                db = await pg.locator("#render3d").bounding_box()
                await pg.mouse.move(cb["x"] + cb["width"] / 2, cb["y"] + cb["height"] / 2)
                await pg.mouse.down()
                await pg.mouse.move(db["x"] + db["width"] + 40, cb["y"] + cb["height"] / 2, steps=8)
                await pg.mouse.up()
                await pg.wait_for_timeout(250)
                check(f"{tag}: a rotate-drag ending outside the 3D dialog keeps it open", await pg.evaluate("document.getElementById('render3d').open"))
            except Exception:
                msg = await pg.locator("#render3d .render3d-status").inner_text()
                check(f"{tag}: 3D rendering opens or explains why not", "WebGL2" in msg, msg)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(200)
            check(f"{tag}: 3D dialog closes", not await pg.evaluate("document.getElementById('render3d').open"))
            if name == "chromium":  # opening 3D for two cases in a row must leave one volume
                await pg.evaluate("""() => { const P = window.niivue.Niivue.prototype; const add = P.addVolume;
                  P.addVolume = function (v) { window.__nv = this; return add.call(this, v); }; }""")
                gp2 = await open_cap(pg, "generation", mobile)
                await wait_loaded(pg, gp2)
                await pg.locator(f"{gp2} [data-role='3d']").click()
                await pg.keyboard.press("Escape")
                await pg.locator(f"{gp2} .tab").nth(1).click()
                await wait_loaded(pg, gp2)
                await pg.locator(f"{gp2} [data-role='3d']").click()
                await pg.wait_for_function("document.querySelector('#render3d .render3d-status').hidden === true", timeout=60000)
                await pg.wait_for_timeout(1500)
                names = await pg.evaluate("() => window.__nv ? window.__nv.volumes.map((v) => v.name) : null")
                check(f"{tag}: quick 3D re-open keeps a single volume", names is not None and len(names) == 1, str(names))
                await pg.keyboard.press("Escape")

        # visual Turing test
        await pg.locator("#turing").scroll_into_view_if_needed()
        await press(pg, pg.locator("#turing [data-role=start]"), mobile)
        enabled = "(() => { const b = document.querySelector('#turing-app [data-answer=real]'); return b && !b.disabled; })()"
        title = lambda: pg.locator("#turing-app .turing-head .title").inner_text()
        await pg.wait_for_function(enabled, timeout=60000)
        ok, _ = await canvases_have_image(pg, "#turing-app")
        check(f"{tag}: quiz case is drawn", ok)
        check(f"{tag}: quiz case has the tumor outline toggle", await pg.locator("#turing-app [data-role=mask]").count() == 1)
        if not mobile:
            await pg.locator("#turing-app [data-answer=real]").click()
            await pg.wait_for_timeout(150)  # a quick second click lands on the next case
            await pg.locator("#turing-app [data-answer=real]").click(force=True)
            await pg.wait_for_timeout(300)
            t = await title()
            check(f"{tag}: a quick second click does not answer the next case", t == "Case 2 of 10", t)
            await pg.wait_for_function(enabled, timeout=60000)
            await pg.evaluate("() => { for (let i = 0; i < 10; i++) document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', repeat: true, bubbles: true })); }")
            await pg.wait_for_timeout(300)
            t = await title()
            check(f"{tag}: a held key does not answer repeatedly", t == "Case 2 of 10", t)
        for _ in range(12):
            if await pg.locator("#turing-app .result-score").count():
                break
            await pg.wait_for_function(enabled, timeout=60000)
            await press(pg, pg.locator("#turing-app [data-answer=synthetic]"), mobile)
            await pg.wait_for_timeout(100)
        await pg.wait_for_selector("#turing-app .result-score", timeout=10000)
        review = await pg.locator("#turing-app .review").inner_text()
        check(f"{tag}: quiz review names no datasets", not any(k in review for k in ("TCIA", "MSD", "KiTS", "FedBCa", "PANORAMA")), review[:80])
        thumbs = await pg.locator("#turing-app .review img").count()
        bars = await pg.locator("#turing-app .hbar").count()
        check(f"{tag}: quiz finishes with 10 reviewed cases and a comparison chart", thumbs == 10 and bars == 4,
              await pg.locator("#turing-app .result-score").inner_text())

        noise = [e for e in errors if "GL Driver Message" not in e and "WebGL" not in e]
        check(f"{tag}: no console errors, failed requests or HTTP errors", not noise, "; ".join(noise[:4]))
        await pg.context.close()
    await browser.close()


async def run_configs(p, url):
    print("\n== site-config variants (chromium)")
    browser = await p.chromium.launch()
    published = (CONFIG.replace("status: 'preprint'", "status: 'published'")
                 .replace("paper: ''", "paper: 'https://example.org/paper'").replace("journal: { name: ''", "journal: { name: 'Nature'"))
    pg, errors = await new_page(browser, url, config=published)
    check("published: paper button shown", await pg.locator(".links [data-link=paper]").is_visible())
    check("published: BibTeX uses the journal", "journal = {Nature}" in await pg.locator("#bibtex-text").inner_text())
    await pg.context.close()
    ctx = await browser.new_context()
    pg = await ctx.new_page()
    await pg.goto((ROOT / "index.html").as_uri())
    await pg.wait_for_timeout(1500)
    txts = await pg.locator(".explorer-stage").all_inner_texts()
    check("file:// shows the web-server notice in every viewer", len(txts) == 2 and all("web server" in t for t in txts), str([t[:30] for t in txts]))
    txt = await pg.locator("#turing-app").inner_text()
    check("file:// notice in the Turing test", "web server" in txt)
    await browser.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="chromium,webkit,firefox")
    ap.add_argument("--quick", action="store_true", help="desktop only")
    args = ap.parse_args()
    httpd, url = serve()
    async with async_playwright() as p:
        for name in args.engines.split(","):
            await run_engine(p, name, url, args.quick)
        await run_configs(p, url)
    httpd.shutdown()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
