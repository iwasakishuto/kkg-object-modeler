"""Generate SolidCraft command scripts for building-element trials.

Every dimension below is read from a real door / fixture schedule (sheet values),
or is marked ASSUMED where the schedule gives none. Run:

    python examples/kkg-trial/generate.py

and then build each script with `solidcraft-cli run <script> --out <file>`.
Expected volumes are computed here from the same inputs, independently of
SolidCraft, and written to expected.json for the blind check in check.py.
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent


def box(name, x0, y0, z0, lx, ly, lz, op="new", targets=None):
    p = {"length": lx, "width": ly, "height": lz, "corner": [x0, y0, z0], "operation": op, "name": name}
    if op == "new":
        p["body_name"] = name
    if targets:
        p["targets"] = targets
    return {"command": "solid.box", "params": p}


def write(name, commands, expected):
    (OUT / f"{name}.json").write_text(json.dumps({"commands": commands}, indent=1), encoding="utf-8")
    return {name: expected}


expected = {}

# ---------------------------------------------------------------------------
# 1. Smoke-exhaust window (door schedule mark "2R-AW")
#    Schedule: W 1100, H 800, frame depth 70, sill at FL+1500,
#    effective opening 1012 x 587, rails 146 (bottom) / 67 (top),
#    glazing FW6.8 + AR8 + Low-E3 = 17.8 mm.
#    Parametric: W, H, depth and sill are parameters; the frame sizes
#    follow the schedule's rail widths.
# ---------------------------------------------------------------------------
W, H, D, SILL = 1100.0, 800.0, 70.0, 1500.0
JAMB = (W - 1012.0) / 2  # 44 per side, from W and the effective opening
BOT, TOP = 146.0, 67.0
GL = 6.8 + 8 + 3
win = [
    {"command": "parameters.add", "params": {"name": "W", "expression": f"{W} mm"}},
    {"command": "parameters.add", "params": {"name": "H", "expression": f"{H} mm"}},
    {"command": "parameters.add", "params": {"name": "D", "expression": f"{D} mm"}},
    {"command": "parameters.add", "params": {"name": "sill", "expression": f"{SILL} mm"}},
    {"command": "parameters.add", "params": {"name": "jamb", "expression": f"{JAMB} mm"}},
    {"command": "parameters.add", "params": {"name": "rail_b", "expression": f"{BOT} mm"}},
    {"command": "parameters.add", "params": {"name": "rail_t", "expression": f"{TOP} mm"}},
    {"command": "parameters.add", "params": {"name": "glass", "expression": f"{GL} mm"}},
    {"command": "solid.box", "params": {"length": "W", "width": "D", "height": "H", "corner": [0, 0, "sill"],
                                         "operation": "new", "name": "Frame", "body_name": "Frame"}},
    {"command": "solid.box", "params": {"length": "W - 2*jamb", "width": "D + 2", "height": "H - rail_b - rail_t",
                                         "corner": ["jamb", -1, "sill + rail_b"], "operation": "cut",
                                         "targets": ["Frame"], "name": "Opening"}},
    {"command": "solid.box", "params": {"length": "W - 2*jamb", "width": "glass", "height": "H - rail_b - rail_t",
                                         "corner": ["jamb", "(D - glass)/2", "sill + rail_b"], "operation": "new",
                                         "name": "Glass", "body_name": "Glass"}},
]
ow, oh = W - 2 * JAMB, H - BOT - TOP
expected.update(write("window_smoke_exhaust", win, {
    "Frame": {"volume": W * D * H - ow * D * oh, "bbox": [[0, 0, SILL], [W, D, SILL + H]]},
    "Glass": {"volume": ow * GL * oh, "bbox": [[JAMB, (D - GL) / 2, SILL + BOT], [W - JAMB, (D + GL) / 2, SILL + BOT + oh]]},
    "_source": "schedule 2R-AW: W1100 H800 depth70 sill FL+1500, opening 1012x587, glazing 17.8",
}))

# Parameter change on the same design: a 1400 x 900 version of the window.
W2, H2 = 1400.0, 900.0
ow2, oh2 = W2 - 2 * JAMB, H2 - BOT - TOP
win_resized = win + [
    {"command": "parameters.change", "params": {"name": "W", "expression": f"{W2} mm"}},
    {"command": "parameters.change", "params": {"name": "H", "expression": f"{H2} mm"}},
]
expected.update(write("window_smoke_exhaust_resized", win_resized, {
    "Frame": {"volume": W2 * D * H2 - ow2 * D * oh2, "bbox": [[0, 0, SILL], [W2, D, SILL + H2]]},
    "Glass": {"volume": ow2 * GL * oh2},
    "_source": "same window, W and H changed to 1400 x 900 after building",
}))

# ---------------------------------------------------------------------------
# 2. Storefront sash with a bi-parting automatic door (door schedule mark "1-AW")
#    Schedule: overall W 14145.5, H 2630, frame depth 100.
#    Bays (incl. outer 30 jambs): 1805.5 | 1808 x4 | 3033 | 1715, mullions 60.
#    Transom 60 at FL+1820 (lower lite 1820, upper 750).
#    Door bay: 706.5 FIX | 60 | 1500 door | 60 | 706.5 FIX, door head 100 at FL+2100.
#    Door leaves 2 x 777.5 wide, DH 2097, tempered glass t=5.
#    Glazing: lower FL5+AR16+Low-E5 = 26, upper FL3+AR16+Low-E3 = 22.
#    ASSUMED: outer jamb and head 30 (dimension "30" at the ends); sill flush
#    with FL (no bottom rail drawn); leaves modelled as the 5 mm glass alone
#    (stile sizes are not in the schedule).
# ---------------------------------------------------------------------------
SW, SH, SD = 14145.5, 2630.0, 100.0
JB, HEAD, MUL, TR_Z, TR = 30.0, 30.0, 60.0, 1820.0, 60.0
bays = [1805.5, 1808, 1808, 1808, 1808, 3033, 1715]
assert abs(sum(bays) + MUL * (len(bays) - 1) - SW) < 1e-6
GL_LO, GL_UP = 26.0, 22.0
cmds = [box("Frame", 0, 0, 0, SW, SD, SH)]
glass = []  # (name, x0, z0, lx, lz, t)
cut_vol = 0.0
x = 0.0
for i, bw in enumerate(bays):
    x0 = x + (JB if i == 0 else 0)
    x1 = x + bw - (JB if i == len(bays) - 1 else 0)
    if bw == 3033:
        fix = 706.5
        parts = [(x0, x0 + fix, "fix"), (x0 + fix + MUL, x0 + fix + MUL + 1500, "door"), (x1 - fix, x1, "fix")]
        for j, (a, b, kind) in enumerate(parts):
            if kind == "fix":
                lo = (a, 0.0, b - a, TR_Z)
                up = (a, TR_Z + TR, b - a, SH - HEAD - TR_Z - TR)
            else:
                lo = (a, 0.0, b - a, 2100.0)
                up = (a, 2200.0, b - a, SH - HEAD - 2200.0)
            for tag, (ax, az, lx, lz), t in (("L", lo, GL_LO), ("U", up, GL_UP)):
                n = f"Bay{i + 1}{tag}{j + 1}"
                cmds.append(box(f"Cut{n}", ax, -1, az, lx, SD + 2, lz, op="cut", targets=["Frame"]))
                cut_vol += lx * SD * lz
                if not (kind == "door" and tag == "L"):
                    glass.append((f"Glass{n}", ax, az, lx, lz, t))
        door_x0 = parts[1][0]
    else:
        for tag, az, lz, t in (("L", 0.0, TR_Z, GL_LO), ("U", TR_Z + TR, SH - HEAD - TR_Z - TR, GL_UP)):
            n = f"Bay{i + 1}{tag}"
            cmds.append(box(f"Cut{n}", x0, -1, az, x1 - x0, SD + 2, lz, op="cut", targets=["Frame"]))
            cut_vol += (x1 - x0) * SD * lz
            glass.append((f"Glass{n}", x0, az, x1 - x0, lz, t))
    x += bw + MUL
for n, ax, az, lx, lz, t in glass:
    cmds.append(box(n, ax, (SD - t) / 2, az, lx, t, lz))
LEAF_W, LEAF_H, LEAF_T, OVERLAP = 777.5, 2097.0, 5.0, 15.0
leaves_w = 2 * LEAF_W - OVERLAP
lx0 = door_x0 + 750.0 - leaves_w / 2
cmds.append(box("LeafL", lx0, -20, 0, LEAF_W, LEAF_T, LEAF_H))
cmds.append(box("LeafR", lx0 + LEAF_W - OVERLAP, -30, 0, LEAF_W, LEAF_T, LEAF_H))
exp = {"Frame": {"volume": SW * SD * SH - cut_vol, "bbox": [[0, 0, 0], [SW, SD, SH]]},
       "LeafL": {"volume": LEAF_W * LEAF_T * LEAF_H}, "LeafR": {"volume": LEAF_W * LEAF_T * LEAF_H}}
for n, ax, az, lx, lz, t in glass:
    exp[n] = {"volume": lx * t * lz}
exp["_source"] = "schedule 1-AW: W14145.5 H2630 depth100, 7 bays, transom FL+1820, auto door 2x777.5 DH2097"
expected.update(write("storefront_auto_door", cmds, exp))

# ---------------------------------------------------------------------------
# 3. Sanitary fixtures from the fixture schedule (outer sizes only).
#    Service sink (mop sink) W440 x D400 x H275.
#    Grease trap W610 x D310 x H600 (50 L class).
#    Multipurpose sink concrete base W620 x D620 x H120.
#    ASSUMED: shell walls 10 mm (sink) and 5 mm (trap); the schedule gives none.
# ---------------------------------------------------------------------------
sink_t, trap_t = 10.0, 5.0
fx = [
    box("ServiceSink", 0, 0, 0, 440, 400, 275),
    {"command": "solid.shell", "params": {"faces": [[220, 200, 275]], "thickness": sink_t, "body": "ServiceSink"}},
    box("GreaseTrap", 800, 0, -600, 610, 310, 600),
    {"command": "solid.shell", "params": {"faces": [[1105, 155, 0]], "thickness": trap_t, "body": "GreaseTrap"}},
    box("GreaseTrapLid", 800, 0, 0, 610, 310, 5),
    box("SinkBase", 1700, 0, 0, 620, 620, 120),
]


def open_box_volume(a, b, c, t):
    return a * b * c - (a - 2 * t) * (b - 2 * t) * (c - t)


expected.update(write("sanitary_fixtures", fx, {
    "ServiceSink": {"volume": open_box_volume(440, 400, 275, sink_t), "bbox": [[0, 0, 0], [440, 400, 275]]},
    "GreaseTrap": {"volume": open_box_volume(610, 310, 600, trap_t), "bbox": [[800, 0, -600], [1410, 310, 0]]},
    "GreaseTrapLid": {"volume": 610 * 310 * 5},
    "SinkBase": {"volume": 620 * 620 * 120},
    "_source": "fixture schedule: SK500 440x400x275, grease trap 610x310x600, base 620x620x120",
}))

# ---------------------------------------------------------------------------
# 4. Drain piping into a small inspection chamber (150 dia, from the chamber list).
#    ASSUMED: route (down 600, 90-degree bend R 150, run 2000) is a test path,
#    not taken from a plan; pipe VP50 per JIS K 6741 (OD 60, wall 4.1).
# ---------------------------------------------------------------------------
OD, WALL, R, DROP, RUN = 60.0, 4.1, 150.0, 600.0, 2000.0
c45 = R * (1 - math.cos(math.radians(45)))
pipe = [
    {"command": "sketch.create", "params": {"plane": {"origin": [0, 0, 0], "x_dir": [1, 0, 0], "y_dir": [0, 0, 1]}, "name": "Route"}},
    {"command": "sketch.line", "params": {"points": [[0, 0], [0, -DROP]], "infer": False}},
    {"command": "sketch.arc.three_point", "params": {"start": [0, -DROP], "through": [c45, -DROP - R * math.sin(math.radians(45))], "end": [R, -DROP - R]}},
    {"command": "sketch.line", "params": {"points": [[R, -DROP - R], [R + RUN, -DROP - R]], "infer": False}},
    {"command": "sketch.finish", "params": {}},
    {"command": "solid.pipe", "params": {"path_sketch": "Route", "path": ["l1", "a1", "l2"], "diameter": OD, "wall": WALL,
                                          "operation": "new", "name": "DrainPipe", "body_name": "DrainPipe"}},
    {"command": "solid.cylinder", "params": {"diameter": 150 + 2 * 5, "height": 900, "base": [R + RUN + 80, 0, -DROP - R - 300],
                                              "operation": "new", "name": "Chamber", "body_name": "Chamber"}},
    {"command": "solid.shell", "params": {"faces": [[R + RUN + 80, 0, -DROP - R + 600]], "thickness": 5, "body": "Chamber"}},
]
ring = math.pi / 4 * (OD ** 2 - (OD - 2 * WALL) ** 2)
path_len = DROP + math.pi * R / 2 + RUN
cyl_outer = math.pi * (80 ** 2) * 900
cyl_inner = math.pi * (75 ** 2) * (900 - 5)
expected.update(write("drain_pipe_chamber", pipe, {
    "DrainPipe": {"volume": ring * path_len},
    "Chamber": {"volume": cyl_outer - cyl_inner},
    "_source": "chamber list: small chamber 150 dia; pipe VP50 assumed; route assumed",
}))

(OUT / "expected.json").write_text(json.dumps(expected, indent=1), encoding="utf-8")
print("wrote", len(expected), "scripts")
