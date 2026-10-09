"""End-to-end check of the project page in Chromium, WebKit (Safari) and Firefox.

Usage:
  python3 -m playwright install chromium webkit firefox   # once
  python3 tools/test_page.py                              # all engines
  python3 tools/test_page.py --engines chromium --quick

Starts its own static server and checks the world-model figure, the carousels (tabs, buttons,
swipe, one height per carousel, images at one size), the Generation showcase, the charts and
their tooltips, the visual Turing test (whose canvases must contain image data) and the
site-config switches. Exit code 1 if anything fails.
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
        check(f"{tag}: result charts drawn", charts == 16, f"{charts} charts")
        km = await pg.evaluate("() => [...document.querySelectorAll('figure.km')].map((f) => f.querySelectorAll('.km-plot path').length)")
        check(f"{tag}: Kaplan-Meier curves drawn for both cohorts", km == [2, 2], str(km))
        tones = await pg.evaluate("""() => [...document.querySelectorAll('.hbar .fill, .v-bar, .lolli .dot')].map((m) => getComputedStyle(m).backgroundColor)
          .concat([...document.querySelectorAll('.l-line')].map((m) => getComputedStyle(m).stroke))""")
        paper = {"rgb(180, 192, 228)", "rgb(120, 132, 180)", "rgb(72, 72, 120)", "rgb(240, 192, 204)"}
        check(f"{tag}: bars, lollipops and lines use the paper's figure colours", tones and set(tones) <= paper, str(sorted(set(tones))))
        groups = await pg.locator(".v-group").count()
        # FID 8, organ Dice 16, abnormality AUC 13, tumor Dice 8, report metrics by region 12, translation by
        # method 4 x 3 panels, reader study 4, T1CE Dice 3, C-index 2
        check(f"{tag}: grouped bars and lollipops drawn", groups == 8 + 16 + 13 + 8 + 12 + 12 + 4 + 3 + 2, f"{groups} groups")
        credits = await pg.locator("#data-credits li").count()
        licenses = await pg.locator('#data-credits a[href^="https://creativecommons.org/licenses/"]').count()
        check(f"{tag}: image credits list the source datasets with license links", credits >= 10 and licenses >= credits - 1,
              f"{credits} datasets, {licenses} license links")
        labels = await pg.locator(".v-val, .m-val, .hbar .val").count()
        check(f"{tag}: charts carry no value labels", labels == 0, f"{labels} labels")
        check(f"{tag}: no table toggle on charts", await pg.locator(".chart-toggle").count() == 0)
        # line charts keep one layout at every width, the bar charts switch on phones
        narrow = await pg.evaluate("() => [...document.querySelectorAll('figure.chart.has-bars:not(.lines)')].map((f) => f.classList.contains('is-narrow'))")
        if mobile:
            check(f"{tag}: every bar chart uses the phone layout", narrow and all(narrow), str(narrow))
            target = pg.locator("figure.chart.is-narrow .m-group").first
            await target.scroll_into_view_if_needed()
            await pg.wait_for_timeout(800)  # smooth scrolling ends first, its scroll events hide the tooltip
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
            edges = await pg.evaluate("""() => [...document.querySelectorAll('.strip, .wm, .section-head, .carousel, .evidence, .results-grid, #turing-app, .cite-grid')]
              .map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right)]; })""")
            check(f"{tag}: all blocks share the same left and right edges", len({tuple(e) for e in edges}) == 1, str(edges[:2]))

        # hero: title, then the world-model figure, then the strip of generated scans
        first = await pg.locator(".strip-item img").first.get_attribute("src")
        check(f"{tag}: the hero strip opens with a generated scan", "gen_abdomen_0" in first and "render3d" not in first, first)
        await pg.locator("figure.wm").scroll_into_view_if_needed()
        try:  # the figure's images load lazily
            await pg.wait_for_function("[...document.querySelectorAll('figure.wm img')].every((i) => i.complete && i.naturalWidth > 0)", timeout=15000)
        except Exception:
            pass  # reported by the check below
        wm = await pg.evaluate("""() => { const f = document.querySelector('figure.wm');
          const r = f.getBoundingClientRect(); const w = f.querySelector('.wm-wires'); const band = f.querySelector('.wm-ridges');
          return { ins: f.querySelectorAll('.wm-inputs .wm-cell').length, outs: f.querySelectorAll('.wm-outputs .wm-cell').length,
                   values: [...f.querySelectorAll('.wm-value')].map((a) => a.getAttribute('href')),
                   ridges: band.querySelectorAll('polyline.ridge').length, picks: band.querySelectorAll('circle.pick').length,
                   wires: getComputedStyle(w).display === 'none' ? -1 : w.querySelectorAll('line.wire').length,
                   fits: r.right <= document.documentElement.clientWidth + 0.5,
                   thumbs: [...f.querySelectorAll('img')].every((i) => i.complete && i.naturalWidth > 0),
                   order: [document.querySelector('.hero h1'), f, document.querySelector('.strip')].map((e) => e.getBoundingClientRect().top),
                   layout: (() => {  // where the band, the inputs, the scans, the points and the label sit
                     const box = (e) => e.getBoundingClientRect(); const b = box(f.querySelector('.wm-model'));
                     const imgs = [...f.querySelectorAll('.wm-inputs .wm-in')].map((e) => box(e.querySelector('img') || e));
                     const outs = [...f.querySelectorAll('.wm-outputs .wm-out')].map(box);
                     const sx = b.width / band.viewBox.baseVal.width, sy = b.height / band.viewBox.baseVal.height;
                     const picks = [...band.querySelectorAll('circle.pick')].map((c) => [b.left + c.cx.baseVal.value * sx, b.top + c.cy.baseVal.value * sy]);
                     const chip = box(f.querySelector('.wm-chip')), pre = imgs[4];
                     const down = b.height > b.width;
                     return { down,
                       between: down ? imgs.every((i) => i.right < b.left) && outs.every((o) => o.left > b.right) && b.top <= outs[0].top && b.bottom >= outs[4].bottom
                         : imgs.every((i) => i.bottom < b.top) && outs.every((o) => o.top > b.bottom) && b.left <= outs[0].left && b.right >= outs[4].right,
                       rows: down ? outs.map((o, i) => Math.round(Math.abs(o.top - imgs[i].top))) : imgs.map((i) => Math.round(Math.abs(i.bottom - imgs[0].bottom))),
                       picks: picks.map(([x, y], i) => Math.round(down ? Math.abs(y - (outs[i].top + outs[i].height / 2)) : Math.abs(x - (outs[i].left + outs[i].width / 2)))),
                       same: imgs.slice(1).every((i) => Math.abs(i.width - pre.width) < 0.5 && Math.abs(i.height - pre.height) < 0.5),
                       chip: down ? chip.top >= pre.bottom : chip.top >= pre.bottom && chip.bottom <= b.top };
                   })() }; }""")
        check(f"{tag}: the world-model figure sits between the title and the strip", wm["order"] == sorted(wm["order"]), str(wm["order"]))
        check(f"{tag}: world-model figure pairs five inputs with five generated scans", wm["ins"] == 5 and wm["outs"] == 5 and wm["thumbs"], str(wm))
        check(f"{tag}: world-model values link to their sections", wm["values"] == ["#synthetic", "#translation", "#treatment"], str(wm["values"]))
        lay = wm["layout"]
        check(f"{tag}: RadWorld band drawn, with one point per input, next to its scan", wm["ridges"] == 9 and wm["picks"] == 5 and max(lay["picks"]) <= 1, str(lay["picks"]))
        check(f"{tag}: world-model arrows join each input to the band and the band to each scan", wm["wires"] == 10 and wm["fits"], str(wm["wires"]))
        check(f"{tag}: RadWorld sits between the inputs and the scans, " + ("down the middle on phones" if mobile else "across the page"),
              lay["down"] == mobile and lay["between"], str(lay))
        check(f"{tag}: inputs line up " + ("with their scans" if mobile else "in one row"), max(lay["rows"]) <= 1, str(lay["rows"]))
        check(f"{tag}: the pre-treatment CT is as large as the other inputs, with the procedural variables under it", lay["same"] and lay["chip"], str(lay))

        # carousels: one slide per tab, each task slide carries its own charts, only the slide in view is reachable
        cars = await pg.evaluate("""() => [...document.querySelectorAll('[data-carousel]')].map((c) => ({
          id: c.id, tabs: c.querySelectorAll('.carousel-tabs [role=tab]').length, slides: c.querySelectorAll('.carousel-track > .slide').length,
          charts: [...c.querySelectorAll('.carousel-track > .slide')].map((s) => [...s.querySelectorAll('figure.chart')].map((f) => f.dataset.src).join('+')),
          inert: [...c.querySelectorAll('.carousel-track > .slide')].map((s) => s.inert) }))""")
        want = {"gen-carousel": ["fid", "report-recall", "organ-dice"],
                "tr-carousel": ["tr-cbct+hu-cbct", "tr-mr2ct+hu-mr2ct", "tr-phase+lesion", "tr-t1ce+t1ce"], "tace-carousel": ["", ""]}
        check(f"{tag}: carousels pair every task with its charts", {c["id"]: c["charts"] for c in cars} == want and all(c["tabs"] == c["slides"] for c in cars),
              str([(c["id"], c["charts"]) for c in cars]))
        check(f"{tag}: only the first slide of each carousel is reachable", all(c["inert"] == [False] + [True] * (c["slides"] - 1) for c in cars),
              str([c["inert"] for c in cars]))
        # every slide of a carousel shows its images at one size
        sizes = await pg.evaluate("""() => ({
          gen: [...document.querySelectorAll('#gen-carousel .slide')].map((s) => [...s.querySelectorAll('.show-view')].map((v) => Math.round(v.getBoundingClientRect().width)).join(',')),
          tr: [...document.querySelectorAll('#tr-carousel .slide')].map((s) => [...s.querySelectorAll('.tr-frame')].map((v) => Math.round(v.getBoundingClientRect().width)).join(',')) })""")
        check(f"{tag}: generation slides show their views at one size", len(set(sizes["gen"])) == 1 and sizes["gen"][0], str(sizes["gen"]))
        check(f"{tag}: translation slides show their images at one size", len(set(sizes["tr"])) == 1 and sizes["tr"][0], str(sizes["tr"]))

        car = "#tr-carousel"
        heights = []
        nxt = pg.locator(f"{car} .carousel-side[data-step='1']") if not mobile else pg.locator(f"{car} .carousel-pager [data-step='1']")
        await nxt.scroll_into_view_if_needed()
        heights.append(await pg.evaluate(f"() => document.querySelector('{car} .carousel-viewport').getBoundingClientRect().height"))
        await press(pg, nxt, mobile)
        await pg.wait_for_timeout(700)
        state = await pg.evaluate(f"""() => {{ const c = document.querySelector('{car}'); const v = c.querySelector('.carousel-viewport');
          const s = [...c.querySelectorAll('.carousel-track > .slide')]; const i = s.findIndex((x) => !x.inert);
          const vr = v.getBoundingClientRect(), sr = s[i].getBoundingClientRect();
          return {{ i, sel: [...c.querySelectorAll('.carousel-tabs [role=tab]')].map((t) => t.getAttribute('aria-selected')),
                   inView: Math.abs(sr.left - vr.left) < 2, height: Math.abs(vr.height - sr.height - 2) < 3,
                   prevDisabled: c.querySelector('[data-step="-1"]').disabled, h: vr.height }}; }}""")
        heights.append(state["h"])
        check(f"{tag}: the next button moves to the next translation setting", state["i"] == 1 and state["sel"][1] == "true"
              and state["inView"] and state["height"] and not state["prevDisabled"], str(state))
        hu = await pg.evaluate(f"""() => [...document.querySelectorAll('{car} figure[data-src^="hu-"]')].map((f) => f.querySelectorAll('polyline.l-line').length)""")
        check(f"{tag}: Hounsfield-unit profiles drawn with three lines each", hu == [3, 3], str(hu))
        if not mobile:
            await pg.locator(f"{car} .carousel-tabs [role=tab]").nth(1).focus()
            await pg.keyboard.press("ArrowRight")
            await pg.wait_for_timeout(700)
            i = await pg.evaluate(f"() => [...document.querySelectorAll('{car} .carousel-track > .slide')].findIndex((x) => !x.inert)")
            heights.append(await pg.evaluate(f"() => document.querySelector('{car} .carousel-viewport').getBoundingClientRect().height"))
            check(f"{tag}: arrow keys on the tabs change the slide", i == 2, str(i))
            check(f"{tag}: the slides keep one height, so the page does not jump", max(heights) - min(heights) < 1, str(heights))
            side = await pg.evaluate("""() => { const c = document.querySelector('#gen-carousel'); const b = c.querySelector('.carousel-side').getBoundingClientRect();
              const m = c.querySelector('.carousel-track > .slide:not([inert]) .slide-media').getBoundingClientRect();
              return Math.round((b.top + b.height / 2) - (m.top + m.height / 2)); }""")
            check(f"{tag}: side buttons sit level with the images", abs(side) <= 2, f"{side}px off")
            # the two charts of a translation slide start their plots on one line
            tops = await pg.evaluate(f"""() => [...document.querySelectorAll('{car} .slide:not([inert]) .slide-charts > figure')]
              .map((f) => Math.round(f.querySelector('.v-area').getBoundingClientRect().top))""")
            check(f"{tag}: side-by-side charts line up", len(tops) == 2 and abs(tops[0] - tops[1]) <= 1, str(tops))
            area = pg.locator(f"{car} figure[data-src='hu-cbct'] .l-area")
            await press(pg, pg.locator(f'{car} .carousel-tabs [role=tab]').first, mobile)
            await pg.wait_for_timeout(700)
            await area.scroll_into_view_if_needed()
            await area.hover()
            await pg.wait_for_timeout(150)
            fig = await area.evaluate_handle("(a) => a.closest('figure')")
            ok, lines = await tip_shows_one_method_per_line(pg, fig)
            check(f"{tag}: line-chart tooltip lists one method per line", ok, str(lines))
            await pg.mouse.move(1, 1)
        else:
            box = await pg.locator(f"{car} .carousel-viewport").bounding_box()
            y = box["y"] + 60
            await pg.evaluate("""([x0, x1, y]) => { const v = document.querySelector('#tr-carousel .slide:not([inert]) .slide-head');
              const ev = (type, x) => v.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerType: 'touch', clientX: x, clientY: y }));
              ev('pointerdown', x0); ev('pointerup', x1); }""", [box["x"] + box["width"] * 0.8, box["x"] + box["width"] * 0.2, y])
            await pg.wait_for_timeout(700)
            i = await pg.evaluate(f"() => [...document.querySelectorAll('{car} .carousel-track > .slide')].findIndex((x) => !x.inert)")
            check(f"{tag}: swiping the slide moves to the next setting", i == 2, str(i))
        await press(pg, pg.locator(f'{car} .carousel-tabs [role=tab]').first, mobile)
        await pg.wait_for_timeout(700)
        frames = await pg.evaluate(f"""async () => {{ const imgs = [...document.querySelectorAll('{car} .slide:not([inert]) .tr-frame img')];
          await Promise.all(imgs.map((i) => i.decode().catch(() => null))); return imgs.map((i) => i.naturalWidth > 0); }}""")
        check(f"{tag}: translation images load", frames and all(frames), str(frames))

        # generation: each slide's input and three views. A view opens on one slice and steps through the
        # sprite as the pointer moves across it, case chips switch the views, report cases carry the
        # arrows of Figure 2e, and on the organ-mask slide the mask appears on the CT and in the input card
        gc = "#gen-carousel"
        await pg.locator(gc).scroll_into_view_if_needed()
        chips = await pg.evaluate(f"() => [...document.querySelectorAll('{gc} .slide')].map((s) => s.querySelectorAll('.show-cases .chip').length)")
        check(f"{tag}: generation slides list their cases", chips == [5, 4, 2], str(chips))
        slices = f"{gc} .slide:not([inert]) .show-view .slice:not(.overlay)"
        loaded = """(sel) => Promise.all([...document.querySelectorAll(sel)].map((e) => {
          const m = /url\("?([^")]+)"?\)/.exec(getComputedStyle(e).backgroundImage); if (!m) return false;
          const i = new Image(); i.src = m[1]; return i.decode().then(() => i.naturalWidth > 0, () => false); }))"""
        await pg.wait_for_function(f"[...document.querySelectorAll('{slices}')].every((e) => getComputedStyle(e).backgroundImage.includes('views/'))", timeout=30000)
        ok = await pg.evaluate(loaded, slices)
        check(f"{tag}: the three views of the first case load", ok == [True, True, True], str(ok))
        bg = lambda: pg.evaluate(f"() => getComputedStyle(document.querySelector('{slices}')).backgroundImage")  # noqa: E731
        before = await bg()
        await press(pg, pg.locator(f"{gc} .slide:not([inert]) .show-cases .chip").nth(1), mobile)
        await pg.wait_for_function(f"getComputedStyle(document.querySelector('{slices}')).backgroundImage.includes('gen_abdomen')", timeout=30000)
        after = await bg()
        check(f"{tag}: a case chip switches the three views", before != after and "gen_abdomen" in after, f"{before[-40:]} -> {after[-40:]}")
        if not mobile:
            axial = pg.locator(f"{gc} .slide:not([inert]) .show-view[data-plane=axial]")
            box = await axial.bounding_box()
            pos = lambda: axial.evaluate("(v) => v.querySelector('.slice').style.backgroundPosition")  # noqa: E731
            start = await pos()
            await pg.mouse.move(box["x"] + box["width"] * 0.1, box["y"] + box["height"] / 2)
            await pg.mouse.move(box["x"] + box["width"] * 0.9, box["y"] + box["height"] / 2, steps=4)
            moved = await pos()
            await pg.mouse.move(1, 1)
            await pg.wait_for_timeout(100)
            back = await pos()
            check(f"{tag}: moving across a view scrolls through the slices and leaving returns", moved != start and back == start, f"{start} -> {moved} -> {back}")
        kinds = await pg.evaluate(f"() => [...document.querySelectorAll('{gc} .slide .show-input')].map((c) => c.dataset.kind)")
        check(f"{tag}: each generation slide shows its input", kinds == ["request", "report", "mask"], str(kinds))
        notes = await pg.locator(f"{gc} .show-input").first.inner_text()
        check(f"{tag}: the request card lists only the request", "No image" not in notes, notes.replace(chr(10), ' ')[:60])

        await press(pg, pg.locator(f'{gc} .carousel-tabs [role=tab]').nth(1), mobile)
        await pg.wait_for_timeout(700)
        rep_slices = f"{gc} .slide:not([inert]) .show-view .slice"
        await pg.wait_for_function(f"[...document.querySelectorAll('{rep_slices}')].every((e) => getComputedStyle(e).backgroundImage.includes('views/rep_'))", timeout=30000)
        arrows = await pg.evaluate(f"""() => [...document.querySelectorAll('{gc} .slide:not([inert]) .show-view')].map((v) =>
          v.querySelectorAll('.arrows line').length + (v.querySelector('.arrows.off') ? 100 : 0))""")
        check(f"{tag}: the report case opens on the slice of Figure 2e with its arrow", arrows == [1, 0, 0], str(arrows))
        quote = await pg.evaluate(f"() => document.querySelector('{gc} .slide:not([inert]) .show-input blockquote').textContent")
        check(f"{tag}: the report card shows a full sentence as an excerpt, between ellipses",
              quote.startswith("“… ") and quote.endswith(". …”") and quote[3:4].isupper(), quote)
        rec = pg.locator(f"{gc} figure[data-src='report-recall']")
        await rec.scroll_into_view_if_needed()
        vis = lambda: rec.evaluate("(f) => [...f.querySelectorAll('.l-plot')].map((b) => !b.hidden)")  # noqa: E731
        startv = await vis()
        await press(pg, rec.locator(".chart-variants button").nth(1), mobile)
        await pg.wait_for_timeout(150)
        switched = await vis()
        lines16 = await rec.evaluate("(f) => [...f.querySelectorAll('.l-plot')].filter((b) => !b.hidden)[0].querySelectorAll('polyline.l-line').length")
        check(f"{tag}: Recall@8 and Recall@16 switch, four panels of three lines", startv == [True, False] and switched == [False, True] and lines16 == 12,
              f"{startv} -> {switched}, {lines16} lines")
        titles = await rec.evaluate("(f) => [...f.querySelectorAll('.l-plot:not([hidden]) .v-panel-title')].map((t) => t.textContent)")
        check(f"{tag}: retrieval panels use the paper's terms", titles == ["Chest, Image → Report", "Chest, Image → Image", "Abdomen, Image → Report", "Abdomen, Image → Image"], str(titles))

        await press(pg, pg.locator(f'{gc} .carousel-tabs [role=tab]').nth(2), mobile)
        await pg.wait_for_timeout(700)
        mask_slices = f"{gc} .slide:not([inert]) .slice"
        await pg.wait_for_function(f"[...document.querySelectorAll('{mask_slices}')].every((e) => getComputedStyle(e).backgroundImage.includes('views/m2i_'))", timeout=30000)
        axial = pg.locator(f"{gc} .slide:not([inert]) .show-view[data-plane=axial]")
        await axial.scroll_into_view_if_needed()
        card = lambda: pg.evaluate(f"() => document.querySelector('{gc} .slide:not([inert]) .show-input .slice.mask').style.backgroundPosition")  # noqa: E731
        first_card = await card()
        if mobile:
            await axial.tap()
        else:
            box = await axial.bounding_box()
            await pg.mouse.move(box["x"] + box["width"] * 0.85, box["y"] + box["height"] / 2)
        await pg.wait_for_timeout(300)
        shown = await axial.evaluate("(v) => getComputedStyle(v.querySelector('.overlay')).opacity")
        check(f"{tag}: pointing at a view (or a tap) shows the mask on the CT", shown == "1", shown)
        if not mobile:
            moved_card = await card()
            check(f"{tag}: the input mask follows the axial slice", moved_card != first_card, f"{first_card} -> {moved_card}")
            await pg.mouse.move(1, 1)
        await press(pg, pg.locator(f'{gc} .carousel-tabs [role=tab]').first, mobile)
        await pg.wait_for_timeout(700)

        # treatment: both patients show the input, the treatment details, the virtual and the real CT
        tace = await pg.evaluate("""() => [...document.querySelectorAll('#tace-carousel .slide')].map((s) =>
          [s.querySelectorAll('.tace-img img').length, s.querySelectorAll('.tace-rx dd').length, !!s.querySelector('.tace-img.ours img')])""")
        check(f"{tag}: each TACE patient shows pre, virtual and real CT with the treatment details", tace == [[3, 3, True], [3, 3, True]], str(tace))

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
