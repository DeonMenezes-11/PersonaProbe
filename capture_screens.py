"""
Capture dashboard screenshots for the PDF guide (out/screens/*.png).

Needs the dashboard running first:   streamlit run app.py --server.port 8577
Then:                                python capture_screens.py

Drives a headless Chrome (throwaway profile) over the DevTools protocol: opens
each tab, waits for Streamlit to finish rendering, and clips sections by the
headings on screen.
"""

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = Path(__file__).parent / "out" / "screens"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8577"
PORT = 9333
W, H, SCALE = 1280, 6000, 2

profile = tempfile.mkdtemp(prefix="pp-chrome-")
proc = subprocess.Popen([
    CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
    f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
    f"--window-size={W},1000", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
mid = 0

try:
    page = None
    for _ in range(60):
        try:
            targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
            page = next(t for t in targets if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.25)
    if page is None:
        sys.exit("could not reach headless Chrome")
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=90,
                                     suppress_origin=True)

    def cdp(method, **params):
        global mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(expr):
        r = cdp("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def settle(extra=3.0, timeout=45):
        time.sleep(1.5)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not js("!!document.querySelector('[data-testid=\"stStatusWidget\"]')"):
                break
            time.sleep(0.5)
        time.sleep(extra)          # let Vega finish drawing

    VISIBLE = "(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })"

    def top_of(text, tags="h1,h2,h3,h4,p,label,span,div,summary,strong"):
        """Page y of the first VISIBLE element whose text starts with `text`
        (hidden tabs are in the DOM too, so visibility matters)."""
        return js(f"""(() => {{
            const vis = {VISIBLE};
            const heading = e => /^H[1-6]$/.test(e.tagName);
            const el = [...document.querySelectorAll('{tags}')].find(e =>
                vis(e) && (heading(e) || e.childElementCount === 0 ||
                           e.classList.contains('pp-lede')) &&
                e.textContent.trim().startsWith({json.dumps(text)}));
            if (!el) return null;
            return el.getBoundingClientRect().top + window.scrollY;
        }})()""")

    def panel_bottom():
        return js(f"""(() => {{
            const p = [...document.querySelectorAll('[role="tabpanel"]')].find({VISIBLE});
            const r = p.getBoundingClientRect();
            return r.bottom + window.scrollY;
        }})()""")

    def click_at(expr, what):
        pos = js(f"""(() => {{
            const el = {expr};
            if (!el) return null;
            el.scrollIntoView({{block: 'center'}});
            const r = el.getBoundingClientRect();
            return [r.left + r.width / 2, r.top + r.height / 2];
        }})()""")
        if not pos:
            raise RuntimeError(f"not found: {what}")
        for t in ("mousePressed", "mouseReleased"):
            cdp("Input.dispatchMouseEvent", type=t, x=pos[0], y=pos[1],
                button="left", clickCount=1)

    def open_tab(label):
        click_at(f"[...document.querySelectorAll('[role=\"tab\"]')]"
                 f".find(e => e.textContent.trim() === {json.dumps(label)})", label)
        settle()

    def pick_radio(group, option):
        click_at(f"""(() => {{
            const g = [...document.querySelectorAll('[role="radiogroup"]')]
              .find(e => (e.getAttribute('aria-label') || '') === {json.dumps(group)} && {VISIBLE}(e));
            if (!g) return null;
            return [...g.querySelectorAll('p, div, span')].find(e =>
              e.childElementCount === 0 && e.textContent.trim() === {json.dumps(option)});
        }})()""", f"{group} / {option}")
        settle()

    def content_x():
        return js("""(() => {
            const r = document.querySelector('.block-container').getBoundingClientRect();
            return [Math.max(r.left + 40, 0), r.right - 40];
        })()""")

    def shoot(name, y0, y1):
        if y0 is None or y1 is None or y1 <= y0:
            raise RuntimeError(f"{name}: bad anchors {y0}..{y1}")
        js("window.scrollTo(0, 0)")
        time.sleep(0.3)
        x0, x1 = content_x()
        r = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0, "scale": 1})
        (OUT / f"{name}.png").write_bytes(base64.b64decode(r["data"]))
        print(f"saved {name}.png")

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    cdp("Page.enable")
    cdp("Runtime.enable")
    cdp("Emulation.setDeviceMetricsOverride", width=W, height=H,
        deviceScaleFactor=SCALE, mobile=False)
    cdp("Page.navigate", url=URL)
    settle(extra=5)

    # ① Overview
    shoot("01_overview", top_of("PersonaProbe", "div") - 16,
          top_of("Lab experiments in this project", "h3,h2") - 12)
    shoot("02_exp_map", top_of("Lab experiments in this project", "h3,h2") - 12,
          top_of("Words used on this dashboard", "p,div,span,summary") - 10)

    # ② The test
    open_tab("② The test")
    shoot("03_prompt_compare", top_of("See it for yourself", "h3,h2") - 12,
          top_of("Exp 1 · Why these situations", "p,div,span,summary") - 10)

    # ③ Decisions (opens on borderline applicants)
    open_tab("③ Decisions")
    shoot("04_decisions", top_of("Yes/no decisions - loan", "p") - 12,
          top_of("Which detail moved the score?", "h3,h2") - 12)
    shoot("05_explain", top_of("Which detail moved the score?", "h3,h2") - 12,
          top_of("Two identities at once", "p,div,span,summary") - 10)

    # ④ Recommendations
    open_tab("④ Recommendations")
    shoot("06_rec_laptop", top_of("'What should I get?'", "p") - 12,
          top_of("In its own words", "h3,h2") - 12)
    shoot("07_rec_quotes", top_of("In its own words", "h3,h2") - 12,
          top_of("Across all", "h3,h2") - 12)
    shoot("08_rec_consistency", top_of("Across all", "h3,h2") - 12,
          top_of("What the AI said", "h3,h2") - 12)
    shoot("09_rec_language", top_of("What the AI said", "h3,h2") - 12,
          top_of("Every product at a glance", "h3,h2") - 12)
    shoot("10_rec_glance", top_of("Every product at a glance", "h3,h2") - 12,
          panel_bottom() + 8)

    # ⑤ Guardrails
    open_tab("⑤ Guardrails")
    shoot("11_guard_said_did", top_of("Did the guardrails change", "h3,h2") - 12,
          top_of("Overall: were recommendations fairer", "h3,h2") - 12)
    shoot("12_guard_table", top_of("Overall: were recommendations fairer", "h3,h2") - 12,
          top_of("Follow each person across", "h3,h2") - 12)
    shoot("13_follow_persist", top_of("Follow each person across", "h3,h2") - 12,
          top_of("Why two measures?", "p,div,span,summary") - 10)

    # ⑥ Ethics & law
    open_tab("⑥ Ethics & law")
    shoot("14_ethics", top_of("What the findings mean", "p") - 12,
          top_of("Downloads", "h3,h2") - 12)

    # ⑦ Reliability
    open_tab("⑦ Reliability")
    shoot("15_reliability", top_of("Can these results be trusted", "p") - 12,
          top_of("The model changed under us", "h3,h2") - 12)
    ws.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(profile, ignore_errors=True)
