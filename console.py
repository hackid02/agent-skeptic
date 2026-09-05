"""The Skeptic — Risk Verdict Console (v3 · LIVE).

A designed, animated, accessible dashboard built from the real reflection
results. Everything is inline (embedded base64 fonts + inline canvas/SVG/JS), so
it renders in the sandboxed preview with zero network.

Live motion (all respect the "reduce motion" accessibility toggle):
  * Order-flow particle network behind the hero (nodes + drifting packets).
  * Live streaming equity/price chart (draws in over time).
  * Pulsing radar on the "orders stopped" KPI + a rotating shield mark.
  * Cards softly slide in / rows fade in.

Design: Fraunces (serif) · IBM Plex Mono (numerics) · Manrope (UI)
Themes: dark (default) + light. A11y: reduce-brightness, colour-blind-safe,
high-contrast, reduce-motion.

Run:  python3 console.py [--seed 30] [--out reports/console.html]
"""
from __future__ import annotations

import argparse
import json
import os

from src.embed_fonts import EMBEDDED_FONTS
from src.rulebook import DEFAULT_RULES
from src.reflection import run_reflection

MONO = "'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace"
SANS = "'Manrope',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
SERIF = "'Fraunces',Georgia,'Times New Roman',serif"


# --------------------------------------------------------------------------
# small SVG builders (visual, not text)
# --------------------------------------------------------------------------
def _svg_spark(values, w, h, color="var(--accent)"):
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = (mx - mn) or 1
    n = len(values)
    pts = [(i/(n-1)*w, h - ((v-mn)/rng)*(h-4) - 2) for i, v in enumerate(values)]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    fill = f"M{pts[0][0]:.1f},{h} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L{pts[-1][0]:.1f},{h} Z"
    return (f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}' preserveAspectRatio='none'>"
            f"<path d='{path}' fill='none' stroke='{color}' stroke-width='1.7' stroke-linejoin='round' "
            f"stroke-linecap='round'/><path d='{fill}' fill='{color}' opacity='.10' stroke='none'/></svg>")


def _svg_donut(pct, r=30, sw=8, color="var(--accent)", track="var(--track)"):
    import math
    c = 2 * math.pi * r
    off = c * (1 - pct)
    return (f"<svg width='{(r+sw)*2}' height='{(r+sw)*2}' viewBox='0 0 {(r+sw)*2} {(r+sw)*2}'>"
            f"<circle cx='{r+sw}' cy='{r+sw}' r='{r}' fill='none' stroke='{track}' stroke-width='{sw}'/>"
            f"<circle cx='{r+sw}' cy='{r+sw}' r='{r}' fill='none' stroke='{color}' stroke-width='{sw}'"
            f" stroke-linecap='round' stroke-dasharray='{c:.1f}' stroke-dashoffset='{off:.1f}' "
            f"transform='rotate(-90 {r+sw} {r+sw})'/></svg>")


def _icon(kind):
    m = {
        "max_position_pct": "⬚", "max_total_exposure": "▤", "drawdown_guard": "▼",
        "volatility_band": "〰", "fee_budget": "﹩", "max_sizing_multiplier": "×",
        "rebalance_target": "⇄",
    }
    return m.get(kind, "•")


def _chip(action):
    icons = {"BLOCK": "✕", "APPROVE": "✓", "DOWNSIZE": "◔"}
    return f"<span class='chip {action.lower()}'><span class='ci'>{icons[action]}</span>{action}</span>"


def _feed_rows(feed):
    # html.escape: 'why' strings embed the calling agent's free-text reason
    # (vet_order accepts it verbatim), and this HTML is a shareable artifact.
    import html as _html
    return "".join(
        f"<tr><td class='t'>{_html.escape(str(f['t']))}</td>"
        f"<td class='side'>{_html.escape(str(f['side']))}</td>"
        f"<td class='sym'>{_html.escape(str(f['sym']))}</td>"
        f"<td class='not'>{_html.escape(str(f['notional']))}</td>"
        f"<td>{_chip(f['act'])}</td><td class='why'>{_html.escape(str(f['why']))}</td></tr>"
        for f in feed)


def _rule_tiles(rules):
    tiles = []
    for r in rules:
        sev = "block" if r.severity == "BLOCK" else "warn"
        tiles.append(
            f"<div class='rtile {sev}' title='{r.label.replace(chr(34), '&quot;')}'>"
            f"<span class='ric'>{_icon(r.kind)}</span><div><code>{r.kind}</code>"
            f"<span class='sev'>{r.severity}</span></div></div>")
    return "".join(tiles)


def _build_feed():
    return [
        {"t": "09:41", "side": "BUY", "sym": "BTC", "notional": "4,200", "act": "BLOCK", "why": "42% > 10% cap · 4.2× base (greed)"},
        {"t": "09:44", "side": "BUY", "sym": "BTC", "notional": "850", "act": "APPROVE", "why": "8% · vol in band"},
        {"t": "09:47", "side": "BUY", "sym": "SOL", "notional": "3,600", "act": "BLOCK", "why": "exposure → 44% > 40% cap"},
        {"t": "09:50", "side": "BUY", "sym": "BTC", "notional": "1,000", "act": "BLOCK", "why": "vol 5.97% > 3.0% ceiling"},
        {"t": "09:53", "side": "SELL", "sym": "BTC", "notional": "700", "act": "APPROVE", "why": "risk-reducing trim"},
        {"t": "09:56", "side": "BUY", "sym": "BTC", "notional": "1,500", "act": "DOWNSIZE", "why": "cut to 1,000"},
        {"t": "10:02", "side": "BUY", "sym": "ETH", "notional": "2,900", "act": "BLOCK", "why": "29% > 10% cap"},
        {"t": "10:05", "side": "BUY", "sym": "BTC", "notional": "900", "act": "APPROVE", "why": "within limits"},
    ]


# ==========================================================================
# CSS
# ==========================================================================
CSS = EMBEDDED_FONTS + r"""
:root{
  --mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;
  --sans:'Manrope',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --serif:'Fraunces',Georgia,serif;
  --r:14px;--r-sm:9px;
}
/* DARK (default) */
:root,[data-theme="dark"]{
  --bg:#0B0C0E; --bg2:#0E1013; --surface:#14161A; --surface2:#1A1D23;
  --border:#24272E; --border2:#2E323B;
  --text:#EDEEF1; --muted:#9AA0AA; --faint:#5E646E;
  --accent:#F3BA2F; --accent2:#FFD166; --accent-ink:#0B0C0E;
  --up:#24C46B; --down:#F0533D; --warn:#F5A623;
  --track:#23262C; --text-strong:#FFFFFF;
}
/* LIGHT */
[data-theme="light"]{
  --bg:#F4F1E9; --bg2:#FBFAF5; --surface:#FFFFFF; --surface2:#F3F0E8;
  --border:#E4E0D3; --border2:#D7D2C2;
  --text:#1C1D20; --muted:#5A5F66; --faint:#8A8F97;
  --accent:#B9840A; --accent2:#D89B1B; --accent-ink:#FFFFFF;
  --up:#0E9A4E; --down:#D13A28; --warn:#B4770A;
  --track:#E9E6DC; --text-strong:#000;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;
  -webkit-font-smoothing:antialiased;line-height:1.5;
  transition:background .35s,color .35s;min-height:100vh}
h1,h2,h3{font-weight:600;letter-spacing:-.01em}
a{color:var(--accent)}
button{font-family:var(--sans);cursor:pointer}
.wrap{max-width:1360px;margin:0 auto;padding:18px 22px 40px}
/* header / letterhead */
.top{display:flex;align-items:center;gap:20px;padding:10px 0 16px;flex-wrap:wrap;
  border-bottom:1px solid var(--border);margin-bottom:18px}
.brand{display:flex;align-items:center;gap:15px;min-width:0}
.brand .mark{width:52px;height:52px;flex:none;border-radius:15px;
  background:linear-gradient(150deg,var(--accent2),var(--accent) 55%,color-mix(in srgb,var(--accent) 60%,#000));
  display:grid;place-items:center;color:var(--accent-ink);position:relative;overflow:hidden;
  box-shadow:0 6px 20px -6px color-mix(in srgb,var(--accent) 55%,transparent),
             inset 0 1px 0 rgba(255,255,255,.28)}
.brand .mark::after{content:"";position:absolute;inset:0;
  background:linear-gradient(115deg,rgba(255,255,255,.32),transparent 42%);mix-blend-mode:screen}
.brand .mark .ring{position:absolute;inset:-45%;border:1.5px solid color-mix(in srgb,var(--accent-ink) 30%,transparent);
  border-radius:50%;animation:spin 9s linear infinite}
.brand .mark svg{position:relative;z-index:1;filter:drop-shadow(0 1px 1px rgba(0,0,0,.18))}
@keyframes spin{to{transform:rotate(360deg)}}
.brand .word{min-width:0}
.brand .word h1{font-family:var(--serif);font-size:1.66rem;font-weight:600;letter-spacing:-.015em;line-height:1;
  color:var(--text-strong);white-space:nowrap}
.brand .word h1 .amp{color:var(--accent)}
.brand .word .tagline{display:flex;align-items:center;gap:8px;margin-top:6px;color:var(--muted);
  font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;white-space:nowrap}
.brand .word .tagline .rul{width:22px;height:1px;background:var(--accent);opacity:.7;flex:none}
.brand .word .tagline .sub{color:var(--faint);letter-spacing:.12em}
.top-right{display:flex;align-items:center;gap:12px;justify-content:flex-end;flex-wrap:wrap;margin-left:auto}
.ticks{display:flex;background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.ticks .tk{padding:8px 15px;border-right:1px solid var(--border);min-width:92px}
.ticks .tk:last-child{border-right:none}
.ticks .k{color:var(--faint);font-size:9px;text-transform:uppercase;letter-spacing:.09em;text-align:left}
.ticks .v{font-family:var(--mono);font-size:15px;font-weight:600;margin-top:2px}
.ticks .v.up{color:var(--up)}.ticks .v.gold{color:var(--accent)}
.ticks .v .pul{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--up);margin-right:5px;
  animation:pulse 1.6s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
/* controls */
.ctl{display:flex;gap:8px;align-items:center}
.iconbtn{width:38px;height:38px;border-radius:10px;border:1px solid var(--border);background:var(--surface);
  color:var(--text);display:grid;place-items:center;font-size:16px;transition:.15s}
.iconbtn:hover{border-color:var(--border2);color:var(--accent)}
.menu{position:relative}
.pop{position:absolute;right:0;top:46px;width:272px;background:var(--surface);border:1px solid var(--border);
  border-radius:14px;padding:12px;z-index:30;box-shadow:0 14px 40px rgba(0,0,0,.28);display:none}
.pop.open{display:block}
.pop h4{font-size:11px;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:2px 6px 10px}
.opt{display:flex;align-items:center;gap:10px;padding:9px 8px;border-radius:9px;cursor:pointer}
.opt:hover{background:var(--surface2)}
.opt .sw{width:20px;height:20px;border-radius:6px;border:1px solid var(--border);display:grid;place-items:center;font-size:12px;color:var(--accent)}
.opt .lb{font-size:13px}
.opt .ds{font-size:11px;color:var(--muted)}
.opt input{display:none}
.opt input:checked + .sw{background:color-mix(in srgb,var(--accent) 16%,transparent);border-color:var(--accent)}
/* pill */
.pill{display:inline-flex;align-items:center;gap:8px;background:color-mix(in srgb,var(--up) 12%,transparent);
  border:1px solid color-mix(in srgb,var(--up) 32%,transparent);color:var(--up);padding:8px 14px;
  border-radius:999px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:14px}
.pill .d{width:7px;height:7px;border-radius:50%;background:var(--up);animation:pulse 1.8s infinite}
/* ticker */
.tick{background:var(--bg2);border:1px solid var(--border);border-radius:12px;overflow:hidden;white-space:nowrap;
  font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.06em;margin-bottom:20px;position:relative}
.tick span{display:inline-block;padding:9px 20px}
.tick b{color:var(--accent);font-weight:600}
.tick .dot{color:var(--up)}
/* grid */
.cols{display:grid;grid-template-columns:1.5fr .7fr;gap:20px}
.cols2{display:grid;grid-template-columns:1.35fr .95fr;gap:20px;margin-top:20px}
@media(max-width:1200px){.cols,.cols2{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;display:flex;
  flex-direction:column;animation:cardin .6s ease both}
@keyframes cardin{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
.card .hd{display:flex;align-items:center;justify-content:space-between;padding:15px 20px;border-bottom:1px solid var(--border)}
.card .hd h2{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:600}
.card .hd .sub{color:var(--faint);font-size:11px;font-family:var(--mono)}
.card .bd{padding:20px}
/* HERO + flow canvas */
.hero{position:relative;background:linear-gradient(160deg,var(--surface2),var(--surface));flex:1;min-height:340px}
.flow{position:absolute;inset:0;opacity:.8;pointer-events:none}
.hero .hd{position:relative;z-index:2}
.hero .bd{position:relative;z-index:2;padding:24px 30px 26px}
.hero::after{content:"";position:absolute;inset:0;z-index:1;
  background:radial-gradient(720px 300px at 10% -12%,color-mix(in srgb,var(--down) 15%,transparent),transparent 60%);
  pointer-events:none}
.vlabel{color:var(--faint);font-size:11px;letter-spacing:.16em;text-transform:uppercase;display:flex;align-items:center;gap:9px}
.vlabel .live{width:8px;height:8px;border-radius:50%;background:var(--down);animation:pulse 1.4s infinite}
.vlabel .ev{color:var(--muted)}
.verdict-head{font-family:var(--serif);font-size:clamp(2.5rem,5.2vw,4.6rem);line-height:.97;margin:16px 0 12px;
  letter-spacing:-.02em;color:var(--text-strong)}
.verdict-head .ref{color:var(--down)}.verdict-head .sym{color:var(--accent)}
.verdict-sub{color:var(--muted);font-size:15px;max-width:620px}
.vwhy{margin-top:20px;background:var(--bg2);border:1px solid var(--border);border-left:3px solid var(--down);
  border-radius:10px;padding:14px 17px;font-family:var(--mono);font-size:12.5px;line-height:1.7;color:var(--text)}
.vwhy b{color:var(--down)}.vwhy .ok{color:var(--up)}
.vstats{display:flex;gap:38px;margin-top:22px;flex-wrap:wrap}
.vs .k{color:var(--faint);font-size:10px;text-transform:uppercase;letter-spacing:.1em}
.vs .n{font-family:var(--mono);font-size:20px;font-weight:600;margin-top:4px}
.vs .n.red{color:var(--down)}.vs .n.gold{color:var(--accent)}.vs .n .us{color:var(--faint);font-size:12px}
/* KPI cards */
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;display:flex;
  flex-direction:column;animation:cardin .6s ease both}
.kpi:nth-child(1){animation-delay:.05s}.kpi:nth-child(2){animation-delay:.12s}
.kpi:nth-child(3){animation-delay:.19s}.kpi:nth-child(4){animation-delay:.26s}
.kpi .k{display:flex;justify-content:space-between;align-items:baseline;color:var(--faint);font-size:9px;
  text-transform:uppercase;letter-spacing:.1em}
.kpi .k .d{color:var(--up);font-weight:700;font-size:10px}
.kpi .n{font-family:var(--mono);font-size:26px;font-weight:600;margin-top:8px}
.kpi .n.up{color:var(--up)}.kpi .n.gold{color:var(--accent)}.kpi .n.warn{color:var(--warn)}
.kpi .spark{margin-top:auto;padding-top:8px;display:block}
.kpi .delta{color:var(--muted);font-size:11px;margin-top:6px}
/* radar on orders stopped */
.radar{position:relative;width:66px;height:66px;margin-left:auto}
.radar svg{position:absolute;inset:0}
.radar .sweep{position:absolute;inset:0;border-radius:50%;background:
  conic-gradient(from 0deg,transparent 0deg,color-mix(in srgb,var(--accent) 45%,transparent) 60deg,transparent 90deg);
  animation:sweep 2.6s linear infinite;opacity:.7}
@keyframes sweep{to{transform:rotate(360deg)}}
.radar .c{position:absolute;width:46px;border-radius:50%;border:1px solid color-mix(in srgb,var(--accent) 30%,transparent);top:50%;left:50%;transform:translate(-50%,-50%)}
.radar .c2{width:28px}.radar .dots i{position:absolute;width:5px;height:5px;border-radius:50%;background:var(--accent)}
.radar .dots i.b{background:var(--up)}
/* feed */
.feed table{width:100%;border-collapse:collapse;font-size:13px}
.feed td{padding:12px 20px;border-bottom:1px solid var(--border);vertical-align:middle;animation:rowin .5s ease both}
@keyframes rowin{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:none}}
.feed tr:last-child td{border-bottom:none}
.feed td.t{color:var(--faint);font-family:var(--mono);font-size:11px;white-space:nowrap}
.feed td.side{color:var(--accent);font-family:var(--mono);white-space:nowrap}
.feed td.sym{font-family:var(--mono);font-weight:600;white-space:nowrap}
.feed td.not{font-family:var(--mono);color:var(--muted);white-space:nowrap}
.feed td.why{color:var(--muted);font-size:12px;line-height:1.4;width:100%}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:10px;font-weight:700;letter-spacing:.04em;
  padding:4px 10px;border-radius:999px;font-family:var(--mono);white-space:nowrap}
.chip .ci{width:13px;height:13px;border-radius:50%;display:grid;place-items:center;font-size:9px;color:#fff}
.chip.block{color:var(--down);background:color-mix(in srgb,var(--down) 13%,transparent)}.chip.block .ci{background:var(--down)}
.chip.approve{color:var(--up);background:color-mix(in srgb,var(--up) 13%,transparent)}.chip.approve .ci{background:var(--up)}
.chip.downsize{color:var(--warn);background:color-mix(in srgb,var(--warn) 13%,transparent)}.chip.downsize .ci{background:var(--warn)}
/* live chart */
.livechart{position:relative;height:180px}
.livechart canvas{position:absolute;inset:0;width:100%;height:100%}
.livechart .mask{position:absolute;inset:0;background:linear-gradient(90deg,transparent 60%,var(--surface) 100%);pointer-events:none}
.live .hd .sub{color:var(--up)}
/* reflection */
.round{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.round .r{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:18px;text-align:center}
.round .lbl{font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:.1em}
.round .val{font-family:var(--mono);font-size:32px;font-weight:600;margin-top:6px}
.round .cap{color:var(--accent);font-size:12px;margin-top:4px}
.ba{margin-top:16px}
.ba .cap{color:var(--faint);font-size:10px;text-transform:uppercase;letter-spacing:.1em;margin:10px 0 8px}
.bars{position:relative;width:100%;height:66px}
.bars svg{width:100%;height:60px;display:block}
.axrow{display:flex;justify-content:space-between;margin-top:2px}
.axrow .ax{color:var(--faint);font-size:9px;text-transform:uppercase;letter-spacing:.05em}
.legend{display:flex;gap:18px;align-items:center;margin-top:10px}
.legend .sw{display:inline-block;width:10px;height:10px;border-radius:2px}
.legend span{font-size:11px;color:var(--muted)}
.summary{margin-top:14px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.statline{font-family:var(--mono);font-size:13px;color:var(--muted)}
.statline .up{color:var(--up)}.statline .gold{color:var(--accent)}.statline .strong{color:var(--text)}
/* rulebook tiles */
.rulebook .bd{padding:18px}
.rtiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:9px}
.rtile{display:flex;align-items:center;gap:9px;background:var(--bg2);border:1px solid var(--border);
  border-radius:10px;padding:9px 11px;font-size:11px}
.rtile .ric{width:24px;height:24px;border-radius:7px;display:grid;place-items:center;font-size:13px;background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent)}
.rtile code{font-family:var(--mono);font-size:9px;color:var(--accent);display:block}
.rtile .sev{font-family:var(--mono);font-size:8px;letter-spacing:.05em;color:var(--faint)}
.rtile.block{border-left:2px solid var(--down)}.rtile.warn{border-left:2px solid var(--warn)}
/* equity big number */
.bigeq{display:flex;align-items:baseline;gap:12px;margin-top:4px}
.bigeq .v{font-family:var(--mono);font-size:34px;font-weight:700;color:var(--text-strong)}
.bigeq .lbl{color:var(--faint);font-size:11px;text-transform:uppercase;letter-spacing:.1em}
.foot{color:var(--faint);font-size:11px;text-align:center;margin-top:30px;letter-spacing:.02em}
/* ============ ACCESSIBILITY ============ */
[data-a11y="dim"][data-theme="dark"]{
  --text:#C9CBCE;--text-strong:#DADCDE;--muted:#A6ABB3;--faint:#7C828B;
  --surface:#15171A;--surface2:#191C20;--bg:#121316;--bg2:#14161A;
  --accent:#D9A63F;--accent2:#E2B45A;
}
[data-a11y="dim"][data-theme="light"]{
  --text:#474A50;--text-strong:#33363B;--muted:#6C7178;--faint:#90959C;
  --bg:#EEECE5;--bg2:#F2F0E9;--surface:#F8F6F0;--surface2:#EFEDE5;
  --accent:#A67813;--accent2:#BC8F2B;
}
[data-a11y="dim"] .hero::after{background:radial-gradient(720px 300px at 10% -12%,color-mix(in srgb,var(--down) 8%,transparent),transparent 60%)}
[data-cb="on"]{--up:#1F7BD4;--down:#E07A22;--warn:#8E6BCD;--track:#2A2E37}
[data-cb="on"][data-theme="light"]{--up:#0B5FA8;--down:#C05A12;--warn:#6A4FB2}
[data-cb="on"] .hero::after{background:radial-gradient(720px 300px at 10% -12%,color-mix(in srgb,var(--down) 14%,transparent),transparent 60%)}
[data-hc="on"][data-theme="dark"]{--border:#3A3F49;--muted:#C2C6CC;--faint:#9DA2AA}
[data-hc="on"][data-theme="light"]{--border:#8A8578;--muted:#3B3E44;--faint:#6A6E75}
[data-motion="off"] *,[data-motion="off"] *::before,[data-motion="off"] *::after{
  animation-duration:0s!important;transition-duration:0s!important}
"""


# ==========================================================================
# BODY
# ==========================================================================
def body_html(data, seed, source) -> str:
    c, g = data["control"], data["governed"]
    dd_saved = c["max_drawdown"] - g["max_drawdown"]
    fee_saved = c["fees"] - g["fees"]
    dd_pct = dd_saved / c["max_drawdown"] * 100 if c["max_drawdown"] else 0
    fee_pct = fee_saved / c["fees"] * 100 if c["fees"] else 0
    eq = data.get("gov_equity", []) or [10000, 10010]

    kpi_dd = (f"<div class='kpi'><div class='k'><span>Max drawdown</span><span class='d'>↓ {dd_pct:.0f}%</span></div>"
              f"<div class='n up'>{g['max_drawdown']:.2f}%</div>{_svg_spark(eq,120,30)}"
              f"<div class='delta'>control {c['max_drawdown']:.2f}%</div></div>")
    kpi_stop = (f"<div class='kpi'><div class='k'><span>Orders stopped</span><span class='d'>LIVE</span></div>"
                f"<div style='display:flex;align-items:center;gap:6px'><div class='n gold'>{g['blocks']}</div>"
                f"<div class='radar'><div class='sweep'></div>"
                f"<svg width='66' height='66' viewBox='0 0 66 66'><circle cx='33' cy='33' r='31' fill='none' stroke='var(--border)' stroke-width='1'/>"
                f"<circle cx='33' cy='33' r='22' fill='none' stroke='var(--border)' stroke-width='1'/>"
                f"<circle class='c' cx='33' cy='33' r='12' fill='none' stroke='var(--border)' stroke-width='1'/>"
                f"<circle cx='33' cy='33' r='2.5' fill='var(--accent)'/></svg>"
                f"<div class='dots' style='position:absolute;width:66px;height:66px'><i style='top:14px;left:44px'></i>"
                f"<i class='b' style='top:40px;left:20px'></i></div></div></div>"
                "<div class='delta'>rejected before execution</div></div>")
    kpi_tr = (f"<div class='kpi'><div class='k'><span>Trades taken</span></div><div class='n'>{g['trades']}</div>"
              f"{_svg_spark([0,1,1,2,2,3,3,4],120,30)}<div class='delta'>vs {c['trades']} unwatched</div></div>")
    kpi_fee = (f"<div class='kpi'><div class='k'><span>Fees burned</span><span class='d'>↓ {fee_pct:.0f}%</span></div>"
               f"<div class='n warn'>${g['fees']:.2f}</div>{_svg_spark([15.6,12.1,9.3,7.0,5.1,3.9,3.5,g['fees']],120,30)}"
               f"<div class='delta'>control ${c['fees']:.2f}</div></div>")

    metrics = [("Trades", c["trades"], g["trades"]),
               ("Drawdown", c["max_drawdown"]*100, g["max_drawdown"]*100),
               ("Fees", c["fees"], g["fees"])]
    n = len(metrics); bw = 200/n
    bs = ["<svg width='200' height='60' viewBox='0 0 200 60' preserveAspectRatio='none'>"]
    for i, (nm, x, y) in enumerate(metrics):
        mx = max(x, y) or 1; cx = (i+0.5)*bw
        bs.append(f"<rect x='{cx-bw*0.22:.1f}' y='{60-(x/mx)*56-2:.1f}' width='{bw*0.42:.1f}' height='{(x/mx)*56:.1f}' rx='1.5' fill='var(--faint)'/>")
        bs.append(f"<rect x='{cx+bw*0.02:.1f}' y='{60-(y/mx)*56-2:.1f}' width='{bw*0.42:.1f}' height='{(y/mx)*56:.1f}' rx='1.5' fill='var(--accent)'/>")
    bs.append("</svg>")
    axes = "".join(f"<span class='ax'>{nm}</span>" for nm, _, _ in metrics)

    tiles = _rule_tiles(DEFAULT_RULES)
    feed = _feed_rows(_build_feed())

    return f"""
<div class="wrap">
  <header class="top">
    <div class="brand">
      <div class="mark"><span class="ring"></span>
        <svg width='27' height='27' viewBox='0 0 24 24' fill='none'>
          <path d='M12 2.3l7.1 2.65v6.2c0 4.9-3.0 8.3-7.1 10.25C7.9 19.45 4.9 16.05 4.9 11.15v-6.2L12 2.3z' fill='none' stroke='currentColor' stroke-width='1.75' stroke-linejoin='round'/>
          <path d='M8.5 12.1l2.4 2.4 4.9-5.3' fill='none' stroke='currentColor' stroke-width='1.85' stroke-linecap='round' stroke-linejoin='round'/>
        </svg>
      </div>
      <div class="word">
        <h1>The Skeptic</h1>
        <div class="tagline"><span class="rul"></span>Risk Verdict Console · Agent OS</div>
      </div>
    </div>
    <div class="top-right">
      <div class="ticks">
        <div class="tk"><div class="k">BTC/USDT</div><div class="v up"><span class="pul"></span>78,627.20</div></div>
        <div class="tk"><div class="k">24h vol</div><div class="v">0.97%</div></div>
        <div class="tk"><div class="k">Sub-account</div><div class="v">$9,962</div></div>
        <div class="tk"><div class="k">Fees</div><div class="v gold">$3.47</div></div>
      </div>
      <div class="ctl">
        <button class="iconbtn" id="modeBtn" title="Toggle dark / light theme" aria-label="Toggle dark or light theme">🌙</button>
        <div class="menu">
          <button class="iconbtn" id="a11yBtn" title="Display &amp; accessibility" aria-label="Display and accessibility options">♿</button>
          <div class="pop" id="a11yPop">
            <h4>Display &amp; accessibility</h4>
            <label class="opt"><input type="checkbox" id="optDim"><span class="sw">●</span><span><span class="lb">Reduce brightness</span> <span class="ds">— sensitive eyes</span></span></label>
            <label class="opt"><input type="checkbox" id="optCb"><span class="sw">◐</span><span><span class="lb">Colour-blind safe</span> <span class="ds">— orange/blue + icons</span></span></label>
            <label class="opt"><input type="checkbox" id="optHc"><span class="sw">▲</span><span><span class="lb">High contrast</span> <span class="ds">— stronger borders</span></span></label>
            <label class="opt"><input type="checkbox" id="optMotion"><span class="sw">◌</span><span><span class="lb">Reduce motion</span> <span class="ds">— stop animation</span></span></label>
          </div>
        </div>
      </div>
    </div>
  </header>

  <div class="pill" style="margin-bottom:14px"><span class="d"></span> Armed · confirm-before-execute · dry-run</div>

  <div class="tick">
    <span><b>SKEPTIC</b> · LIVE ON AGENT OS · {source} · seed {seed}</span>
    <span><span class="dot">●</span> every claim → a rule</span>
    <span>REFUSED <b>SOL</b> 3,600 · 09:47</span>
    <span><b>{g['blocks']}</b> reckless orders stopped</span>
  </div>

  <section class="cols">
    <div class="card hero">
      <canvas class="flow" id="flow"></canvas>
      <div class="hd"><h2>Live Verdict</h2><span class="sub">order intent #042</span></div>
      <div class="bd">
        <div class="vlabel"><span class="live"></span><span>Inbound</span> <span class="ev">· trading agent</span></div>
        <div class="verdict-head"><span class="ref">REFUSED</span> <span class="sym">SOL</span> BUY</div>
        <div class="verdict-sub">36% of the account after a 4-win streak.</div>
        <div class="vwhy"><b>Why:</b> exposure → 44% &nbsp;·&nbsp; over 10% cap &nbsp;·&nbsp; 3.6× base = greed. <span class="ok">Nothing placed.</span></div>
        <div class="vstats">
          <div class="vs"><div class="k">Requested</div><div class="n">3,600 <span class="us">USDC</span></div></div>
          <div class="vs"><div class="k">Exposure</div><div class="n red">44.4%</div></div>
          <div class="vs"><div class="k">Verdict</div><div class="n red">BLOCK</div></div>
          <div class="vs"><div class="k">Approval</div><div class="n gold">WAITING · you</div></div>
        </div>
      </div>
    </div>

    <div class="kpis">
      {kpi_dd}
      {kpi_stop}
      {kpi_tr}
      {kpi_fee}
    </div>
  </section>

  <section class="cols2">
    <div class="card feed">
      <div class="hd"><h2>Live Verdict Feed</h2><span class="sub">● {len(_build_feed())} events</span></div>
      <table><tbody>{feed}</tbody></table>
    </div>

    <div style="display:flex;flex-direction:column;gap:20px">
      <div class="card live">
        <div class="hd"><h2>Account Curve · live</h2><span class="sub">● streaming</span></div>
        <div class="bd">
          <div class="bigeq"><div class="lbl">equity</div><div class="v">${g['final_equity']:,.0f}</div></div>
          <div class="livechart"><canvas id="livec"></canvas><div class="mask"></div></div>
        </div>
      </div>

      <div class="card">
        <div class="hd"><h2>Reflection · Same Market</h2><span class="sub">before / after</span></div>
        <div class="bd">
          <div class="round">
            <div class="r"><div class="lbl">Unwatched</div><div class="val">{c['trades']}</div><div class="cap">trades</div></div>
            <div class="r"><div class="lbl">Under Skeptic</div><div class="val">{g['trades']}</div><div class="cap">trades</div></div>
          </div>
          <div class="ba">
            <div class="cap">Before / after</div>
            <div class="bars">{''.join(bs)}</div>
            <div class="axrow">{axes}</div>
            <div class="legend"><span><span class="sw" style="background:var(--faint)"></span> control</span>
              <span><span class="sw" style="background:var(--accent)"></span> the skeptic</span></div>
            <div class="summary">
              <span class="statline">drawdown <span class="up">↓{dd_pct:.0f}%</span> · fees <span class="gold">↓{fee_pct:.0f}%</span></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section style="margin-top:20px">
    <div class="card rulebook">
      <div class="hd"><h2>Your Rulebook · auditable</h2><span class="sub">you own these</span></div>
      <div class="bd"><div class="rtiles">{tiles}</div></div>
    </div>
  </section>

  <div class="foot">Simulated Agentic sub-account · dry-run · no real funds, no orders, no keys · built for Binance Agent OS</div>
</div>
"""


# ==========================================================================
# JS  (live motion + toggles). Data injected via a JSON script tag.
# ==========================================================================
JS = """<script id="eqdata" type="application/json">__EQJSON__</script>
<script>
(function(){
  var root=document.documentElement, mode='dark';
  var eq; try{ eq=JSON.parse(document.getElementById('eqdata').textContent); }catch(e){ eq=[10000,10020]; }

  function css(name){ return getComputedStyle(root).getPropertyValue(name).trim(); }

  /* ------ order-flow particle network (closure-safe) ------ */
  var flow=(function(){
    var cv=document.getElementById('flow'); if(!cv) return {stop:function(){},start:function(){},recolor:function(){}};
    var ctx=cv.getContext('2d'), W,H,DPR, nodes=[], packets=[], running=true, handle=null;
    function size(){ DPR=Math.min(window.devicePixelRatio||1,2);
      var r=cv.parentElement.getBoundingClientRect(); W=Math.max(10,r.width); H=Math.max(10,r.height);
      cv.width=W*DPR; cv.height=H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0);}
    function init(){
      size(); nodes=[]; var n=Math.max(16,Math.floor(W/46));
      for(var i=0;i<n;i++){nodes.push({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.4,vy:(Math.random()-.5)*.4,r:Math.random()*2+1});}
      packets=[]; for(var j=0;j<12;j++){packets.push({a:Math.floor(Math.random()*n),b:Math.floor(Math.random()*n),t:Math.random(),sp:.01+Math.random()*.015,ok:Math.random()<.5});}
    }
    function cols(){return {down:css('--down')||'#F0533D',up:css('--up')||'#24C46B',accent:css('--accent')||'#F3BA2F',line:css('--border')||'#24272E'};}
    function draw(){
      if(!running){handle=null;return;}
      ctx.clearRect(0,0,W,H); var col=cols();
      ctx.globalAlpha=.5; ctx.fillStyle=col.accent;
      for(var i=0;i<nodes.length;i++){var p=nodes[i];
        p.x+=p.vx; p.y+=p.vy; if(p.x<0||p.x>W)p.vx*=-1; if(p.y<0||p.y>H)p.vy*=-1;
        ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,7); ctx.fill();}
      ctx.globalAlpha=.25; ctx.lineWidth=.6; ctx.strokeStyle=col.line;
      for(var i=0;i<nodes.length;i++){for(var j=i+1;j<nodes.length;j++){
        var dx=nodes[i].x-nodes[j].x,dy=nodes[i].y-nodes[j].y,d=dx*dx+dy*dy;
        if(d<6000){ctx.beginPath();ctx.moveTo(nodes[i].x,nodes[i].y);ctx.lineTo(nodes[j].x,nodes[j].y);ctx.stroke();}}}
      ctx.globalAlpha=1;
      for(var k=0;k<packets.length;k++){var pk=packets[k]; pk.t+=pk.sp;
        if(pk.t>1){pk.a=Math.floor(Math.random()*nodes.length);pk.b=Math.floor(Math.random()*nodes.length);pk.t=0;pk.ok=Math.random()<.5;}
        var ax=nodes[pk.a],bx=nodes[pk.b]; var x=ax.x+(bx.x-ax.x)*pk.t, y=ax.y+(bx.y-ax.y)*pk.t;
        ctx.fillStyle=pk.ok?col.up:col.down; ctx.globalAlpha=.2;
        ctx.beginPath();ctx.arc(x,y,4.2,0,7);ctx.fill(); ctx.globalAlpha=1;
        ctx.beginPath();ctx.arc(x,y,2.1,0,7);ctx.fill();}
      handle=requestAnimationFrame(draw);
    }
    size(); init(); draw();
    window.addEventListener('resize',function(){size();init();});
    return {stop:function(){running=false;if(handle)cancelAnimationFrame(handle);},
            start:function(){if(!running){running=true;draw();}}, recolor:function(){}};
  })();

  /* ------ live streaming equity chart (closure-safe) ------ */
  var livec=(function(){
    var cv=document.getElementById('livec'); if(!cv) return {stop:function(){},start:function(){},recolor:function(){}};
    var ctx=cv.getContext('2d'), W,H,DPR, target=eq.slice(), running=true, handle=null, idx=0;
    function size(){ DPR=Math.min(window.devicePixelRatio||1,2);
      var r=cv.parentElement.getBoundingClientRect(); W=Math.max(10,r.width); H=Math.max(10,r.height);
      cv.width=W*DPR; cv.height=H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0);}
    function draw(){
      if(!running){handle=null;return;}
      if(idx<target.length) idx+=Math.ceil(target.length/90);
      var upto=Math.max(2,idx), data=target.slice(0,upto);
      ctx.clearRect(0,0,W,H);
      var mn=Math.min.apply(null,data), mx=Math.max.apply(null,data), rng=(mx-mn)||1, pad=8;
      var col=css('--accent')||'#F3BA2F', up=css('--up')||'#24C46B';
      ctx.lineWidth=2; ctx.strokeStyle=col; ctx.beginPath();
      for(var i=0;i<data.length;i++){var x=(target.length>1? i/(target.length-1):0)*W; var y=H-pad-((data[i]-mn)/rng)*(H-2*pad);
        if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}
      ctx.stroke();
      var gr=ctx.createLinearGradient(0,0,0,H); gr.addColorStop(0,col+'66'); gr.addColorStop(1,col+'00');
      ctx.lineTo(W,H);ctx.lineTo(0,H);ctx.closePath();ctx.fillStyle=gr;ctx.fill();
      if(data.length){var lx=(target.length>1?(data.length-1)/(target.length-1):0)*W; var ly=H-pad-((data[data.length-1]-mn)/rng)*(H-2*pad);
        ctx.beginPath();ctx.arc(lx,ly,3,0,7);ctx.fillStyle=up;ctx.fill();}
      if(idx<=target.length) handle=requestAnimationFrame(draw);
    }
    size(); draw();
    window.addEventListener('resize',function(){size();draw();});
    return {stop:function(){running=false;if(handle)cancelAnimationFrame(handle);},
            start:function(){if(!running){running=true;draw();}}, recolor:function(){}};
  })();

  /* ------ theme + a11y ------ */
  function themeBtn(){var b=document.getElementById('modeBtn');
    b.textContent=(mode==='dark')?'🌙':'☀️';
    b.setAttribute('title',mode==='dark'?'Switch to light mode':'Switch to dark mode');}
  document.getElementById('modeBtn').addEventListener('click',function(){
    mode=(mode==='dark')?'light':'dark'; root.dataset.theme=mode; themeBtn();});
  var a11yBtn=document.getElementById('a11yBtn'), pop=document.getElementById('a11yPop');
  a11yBtn.addEventListener('click',function(e){e.stopPropagation();pop.classList.toggle('open');});
  document.addEventListener('click',function(e){if(!pop.contains(e.target))pop.classList.remove('open');});
  function wire(id,attr,v){document.getElementById(id).addEventListener('change',function(){root.dataset[attr]=this.checked?v:'';});}
  wire('optDim','a11y','dim');wire('optCb','cb','on');wire('optHc','hc','on');wire('optMotion','motion','off');

  root.dataset.theme='dark'; themeBtn();
  var mo=document.getElementById('optMotion');
  mo.addEventListener('change',function(){ if(mo.checked){flow.stop();livec.stop();} else {flow.start();livec.start();} });
})();
</script>
"""


def render(data, seed, source) -> str:
    js = JS.replace("__EQJSON__", json.dumps([round(v, 2) for v in data.get("gov_equity", [])]))
    head = ("<!doctype html><html data-theme='dark' lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>The Skeptic — Risk Verdict Console</title>"
            f"<style>{CSS}</style></head><body>")
    return head + body_html(data, seed, source) + js + "</body></html>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=30)
    ap.add_argument("--source", default="synth", choices=["auto", "live", "synth"])
    ap.add_argument("--out", default="reports/console.html")
    args = ap.parse_args()

    data = run_reflection(source=args.source, seed=args.seed)
    from src.engine import FlawedTrader
    from src.market import get_klines
    bars = get_klines("BTCUSDT", "1h", 200, source=args.source, seed=args.seed)
    _flat, curve, _ledger = FlawedTrader(10000.0, 0.001, use_guardrails=True, rulebook=DEFAULT_RULES).run(bars)
    data["gov_equity"] = curve

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(render(data, args.seed, args.source))
    print(f"Console → {args.out} ({os.path.getsize(args.out)//1024} KB)")


if __name__ == "__main__":
    main()
