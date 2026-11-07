"""Regenerate every report screenshot on the product page from the renamed sample data.

Based on the handoff's shot5.py (Review) and shot6.py (Improve), plus the Define shots,
which now come from the same data as the rest of the page.
Writes images and meta.json to ./out.
"""

import json
import os

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "out") + "/"
os.makedirs(D, exist_ok=True)
REVIEW, IMPROVE = "http://localhost:8766/index.html", "http://localhost:8767/index.html"
EVALS = ["revenue_q4", "order_total_2026", "top_segment", "top_nations_last_year"]
meta = {}

JS_ROWCELL = """([label,col])=>{const td=[...document.querySelectorAll('td')].find(t=>t.innerText.trim().endsWith(label));
 const tr=td.parentElement; const d=tr.children[col].querySelector('div'); const r=d.getBoundingClientRect(); return [r.x,r.y+scrollY,r.width,r.height]}"""


def review(c):
    W, S = 1240, 1.5
    pg = c.new_page()

    def save(name, box=None, q=88):
        im = Image.open(D + "t.png").convert("RGB")
        if box:
            im = im.crop(tuple(int(v * S) for v in box))
        im.save(D + "review-" + name + ".webp", quality=q)

    def load(h):
        pg.set_viewport_size({"width": W, "height": 900})
        pg.goto(REVIEW + h)
        pg.wait_for_timeout(1300)
        H = pg.evaluate("document.documentElement.scrollHeight")
        pg.set_viewport_size({"width": W, "height": H})
        pg.mouse.move(W - 20, H - 20)
        pg.wait_for_timeout(500)
        return H

    H = load("#/")
    pg.screenshot(path=D + "t.png")
    save("overview")
    m = {"size": [W, H], "hovers": []}
    for lab in EVALS:
        x, y, w, h = pg.evaluate(JS_ROWCELL, [lab, 10])
        pg.mouse.move(x + w / 2, y + h / 2)
        pg.wait_for_timeout(350)
        pg.screenshot(path=D + "t.png")
        box = (max(0, x - 260), max(0, y - 150), min(W, x + w + 200), y + h + 6)
        save("ov_hover_" + lab, box)
        m["hovers"].append({"eval": lab, "cell": [x, y, w, h], "box": box})
    r = pg.evaluate(
        """()=>{const tr=[...document.querySelectorAll('tbody tr')].find(t=>t.innerText.includes('Revenue in')&&t.innerText.includes('extract_match'));const b=tr.getBoundingClientRect();return [b.x,b.y+scrollY,b.width,b.height]}"""
    )
    pg.mouse.move(r[0] + 200, r[1] + r[3] / 2)
    pg.wait_for_timeout(300)
    pg.screenshot(path=D + "t.png")
    box = (r[0] - 2, r[1] - 2, r[0] + r[2] + 2, r[1] + r[3] + 2)
    save("ov_hover_row", box)
    m["hovers"].append({"eval": "row", "cell": r, "box": box})
    m["nav_compare"] = pg.evaluate(
        """()=>{const a=[...document.querySelectorAll('a,button')].find(e=>(e.getAttribute('href')||'').includes('compare')||e.title==='Model comparison'||e.getAttribute('aria-label')==='Model comparison');if(!a)return null;const b=a.getBoundingClientRect();return [b.x,b.y,b.width,b.height]}"""
    )
    meta["overview"] = m
    pg.mouse.move(0, 0)

    H = load("#/compare")
    pg.screenshot(path=D + "t.png")
    save("compare")
    m = {"size": [W, H], "hovers": []}
    for col in [1, 2, 3]:
        x, y, w, h = pg.evaluate(JS_ROWCELL, ["revenue_q4", col])
        pg.mouse.move(x + w / 2, y + h / 2)
        pg.wait_for_timeout(350)
        pg.screenshot(path=D + "t.png")
        box = (max(0, x - 260), max(0, y - 150), min(W, x + w + 200), y + h + 6)
        save(f"cmp_hover_{col}", box)
        m["hovers"].append({"col": col, "cell": [x, y, w, h], "box": box})
    meta["compare"] = m
    pg.mouse.move(0, 0)

    data = json.load(open(os.path.join(HERE, "review/data/report.json")))
    rid = [x for x in data["results"] if x["eval_id"] == "revenue_q4"][-1]["result_id"]
    H = load("#/result/" + rid)
    pg.screenshot(path=D + "t.png")
    save("result")
    meta["result"] = {"size": [W, H], "rid": rid}
    pg.close()


def improve(c, W=1240):
    S = 1.5
    pg = c.new_page()
    pg.set_viewport_size({"width": W, "height": 1200})
    pg.goto(IMPROVE + "#/")
    pg.wait_for_timeout(1500)
    pg.mouse.move(W - 10, 1190)
    pg.wait_for_timeout(300)
    card = pg.evaluate("""()=>{const s=[...document.querySelectorAll('section')].find(s=>s.innerText.includes('Scores by eval run'));const t=s.querySelector('table');const r=t.getBoundingClientRect();
     const xs=[...t.querySelectorAll('tbody td:first-child, thead th:first-child')].map(e=>e.getBoundingClientRect().left);
     const rs=[...t.querySelectorAll('td, thead th *')].map(e=>e.getBoundingClientRect().right);
     const L=Math.min(...xs)-18, R=Math.max(...rs)+4; return [L,r.y,R-L,r.height]}""")
    cells = pg.evaluate("""()=>{const s=[...document.querySelectorAll('section')].find(s=>s.innerText.includes('Scores by eval run'));
     return [...s.querySelectorAll('tbody tr, tfoot tr')].map(tr=>{const lab=tr.children[0].innerText.trim().split('\\n').pop();
       const box=i=>{const d=tr.children[i].querySelector('div');const r=d.getBoundingClientRect();return [r.x,r.y,r.width,r.height]};
       return {label:lab,n:tr.children.length,c10:box(tr.children.length-3),c11:box(tr.children.length-2)}})}""")
    pg.screenshot(path=D + "full.png")
    im = Image.open(D + "full.png").convert("RGB")
    x, y, w, h = card
    im.crop((int(x * S), int(y * S), int((x + w) * S), int((y + h) * S))).save(D + "improve-heat2.webp", quality=90)
    for cl in cells:
        cx, cy, cw, ch = cl["c10"]
        px = im.getpixel((int((cx + cw / 2) * S), int((cy + ch / 2) * S)))
        cl["c10color"] = "#%02x%02x%02x" % px
    hov = []
    for cl in cells:
        if cl["label"] in EVALS:
            cx, cy, cw, ch = cl["c11"]
            pg.mouse.move(cx + cw / 2, cy + ch / 2)
            pg.wait_for_timeout(350)
            pg.screenshot(path=D + "t.png")
            tb = pg.evaluate(
                """()=>{const els=[...document.querySelectorAll('div')].filter(d=>{const t=d.innerText||'';return t.includes('2026-10-11')&&t.includes('Accuracy')&&getComputedStyle(d).position==='fixed'});const e=els[0];const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]}"""
            )
            bx = (tb[0] - 2, tb[1] - 2, tb[0] + tb[2] + 2, tb[1] + tb[3] + 2)
            Image.open(D + "t.png").convert("RGB").crop(tuple(int(v * S) for v in bx)).save(
                D + f"improve-hov_{cl['label']}.webp", quality=90
            )
            hov.append({"label": cl["label"], "cell": cl["c11"], "box": bx})
    meta["improve"] = {"card": card, "cells": cells, "hov": hov}
    pg.close()


def define(c):
    data = json.load(open(os.path.join(HERE, "review/data/report.json")))["results"]
    latest = lambda e, run=None: [
        x for x in data if x["eval_id"] == e and (run is None or x["run_timestamp"].startswith(run))
    ][-1]["result_id"]
    shots = [  # name, result id, section heading, scroll the section to this y (None = top of page)
        ("contains", latest("top_segment"), "Accuracy", None),
        ("extract-match", latest("revenue_q4"), "Accuracy", None),
        ("llm-judge", latest("top_nations_last_year", "2026-10-09"), "Accuracy", None),
        ("provenance", latest("revenue_q4"), "Provenance", 127),
    ]
    pg = c.new_page()
    for name, rid, heading, top in shots:
        pg.goto(REVIEW + "#/result/" + rid)
        pg.wait_for_timeout(1300)
        find = f"()=>[...document.querySelectorAll('section')].find(s=>s.querySelector('h3')&&s.querySelector('h3').innerText.trim()=='{heading}')"
        pg.evaluate(
            f"(()=>{{const s=({find})();s.style.position='relative';s.style.zIndex='999';"
            f"s.style.boxShadow='0 0 0 12px #F3F2EC, 0 0 0 9999px rgba(60,80,65,.4)';}})()"
        )
        if top is not None:
            pg.evaluate(
                f"(()=>{{const s=({find})();window.scrollTo(0,s.getBoundingClientRect().top+scrollY-{top})}})()"
            )
        pg.mouse.move(1270, 750)
        pg.wait_for_timeout(300)
        pg.screenshot(path=D + f"define-{name}.png")
        # The page frames these at 1280x600 (like the YAML panel next to them): crop to that,
        # moving the window down just enough to keep the whole highlighted card in view.
        bottom = pg.evaluate(f"(()=>({find})().getBoundingClientRect().bottom)()")
        top = max(0, min(760 - 600, round(bottom + 20 - 600)))
        img = Image.open(D + f"define-{name}.png")
        k = img.width / 1280
        img.crop((0, int(top * k), img.width, int((top + 600) * k))).save(D + f"define-{name}.png")
    pg.close()


with sync_playwright() as p:
    b = p.chromium.launch()
    c = b.new_context(viewport={"width": 1240, "height": 900}, device_scale_factor=1.5)
    c.add_init_script("try{localStorage.setItem('honest-agent.sidebarMini','1')}catch(e){}")
    import sys

    if "improve-only" in sys.argv:
        meta.update(json.load(open(D + "meta.json")))
        improve(c, int(sys.argv[-1]))
    elif "define-only" not in sys.argv:
        review(c)
        improve(c)
    c2 = b.new_context(viewport={"width": 1280, "height": 760}, device_scale_factor=2)
    c2.add_init_script("try{localStorage.setItem('honest-agent.sidebarMini','1')}catch(e){}")
    define(c2)
    b.close()
if meta:
    json.dump(meta, open(D + "meta.json", "w"), indent=1)
print("done")
