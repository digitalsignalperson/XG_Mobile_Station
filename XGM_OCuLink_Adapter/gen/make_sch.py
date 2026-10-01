#!/usr/bin/env python3
"""Generate lib/XGM_OCuLink.kicad_sym and XGM_OCuLink_Adapter.kicad_sch from
design.py.  Every pin gets a short wire stub and a net label, so the sheet
reads like an annotated netlist."""
import os
import uuid

from design import LIB, PARTS, SYMBOLS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NS = uuid.UUID("6f1d4b7e-58a1-4a51-9a0e-0c0a11a70c01")
G = 2.54


def uid(*key):
    return str(uuid.uuid5(NS, "/".join(str(k) for k in key)))


def font(hide=False, size=1.27, justify=None):
    j = f" (justify {justify})" if justify else ""
    h = " (hide yes)" if hide else ""
    return f"(effects (font (size {size} {size})){j}{h})"


def box_geometry(pins):
    left = [p for p in pins if p[2] == "L"]
    right = [p for p in pins if p[2] == "R"]
    rows = max(len(left), len(right))
    longest = max([len(p[1]) for p in pins] + [1])
    half_w = max(4, int((longest * 2 * 1.0 + 6) / G / 2) + 1) * G
    top = (rows - 1) / 2 * G
    # keep pin ends on the 1.27 mm grid
    top = round(top / 1.27) * 1.27
    return left, right, half_w, top


def symbol_pins(name):
    """-> {number: (x, y, side)} of the connection point, symbol coords (y up)"""
    kind, pins = SYMBOLS[name]
    out = {}
    if kind == "box":
        left, right, half_w, top = box_geometry(pins)
        for i, (num, _, _) in enumerate(left):
            out[num] = (-half_w - G, top - i * G, "L")
        for i, (num, _, _) in enumerate(right):
            out[num] = (half_w + G, top - i * G, "R")
    elif kind == "tp":
        out[pins[0][0]] = (-G, 0, "L")
    else:
        out[pins[0][0]] = (-3.81, 0, "L")
        out[pins[1][0]] = (3.81, 0, "R")
    return out


def pin_sexp(num, pname, x, y, side, length, show=True):
    ang = 0 if side == "L" else 180
    return (f'\t\t\t\t(pin passive line (at {x:.2f} {y:.2f} {ang}) (length {length})\n'
            f'\t\t\t\t\t(name "{pname}" {font()})\n'
            f'\t\t\t\t\t(number "{num}" {font()})\n\t\t\t\t)\n')


def lib_symbol(name, prefix=""):
    kind, pins = SYMBOLS[name]
    pos = symbol_pins(name)
    refdes = {"box": "U", "r": "R", "c": "C", "led": "D", "jp": "JP", "tp": "TP"}[kind]
    if name in ("XGM_Plug", "OCuLink_4i_Host"):
        refdes = "J"
    body = ""
    stroke = "(stroke (width 0.254) (type default))"
    if kind == "box":
        left, right, half_w, top = box_geometry(pins)
        rows = max(len(left), len(right))
        y0, y1 = top + G, top - (rows - 1) * G - G
        body += (f'\t\t\t\t(rectangle (start {-half_w:.2f} {y0:.2f}) (end {half_w:.2f} {y1:.2f})'
                 f' {stroke} (fill (type background)))\n')
        ref_at, val_at = (0, y0 + 1.27), (0, y1 - 1.27)
        hide_names, plen = False, G
    elif kind == "r":
        body += f'\t\t\t\t(rectangle (start -2.54 1.016) (end 2.54 -1.016) {stroke} (fill (type none)))\n'
        ref_at, val_at, hide_names, plen = (0, 2.54), (0, -2.54), True, 1.27
    elif kind == "c":
        for x in (-0.762, 0.762):
            body += (f'\t\t\t\t(polyline (pts (xy {x} 2.032) (xy {x} -2.032))'
                     f' (stroke (width 0.508) (type default)) (fill (type none)))\n')
        ref_at, val_at, hide_names, plen = (0, 3.81), (0, -3.81), True, 3.048
    elif kind == "led":
        body += (f'\t\t\t\t(polyline (pts (xy 1.27 1.27) (xy 1.27 -1.27) (xy -1.27 0) (xy 1.27 1.27))'
                 f' {stroke} (fill (type none)))\n'
                 f'\t\t\t\t(polyline (pts (xy -1.27 1.27) (xy -1.27 -1.27)) {stroke} (fill (type none)))\n')
        ref_at, val_at, hide_names, plen = (0, 3.81), (0, -3.81), True, 2.54
    elif kind == "jp":
        for x in (-0.508, 0.508):
            body += (f'\t\t\t\t(polyline (pts (xy {x} 1.27) (xy {x} -1.27))'
                     f' (stroke (width 0.762) (type default)) (fill (type none)))\n')
        ref_at, val_at, hide_names, plen = (0, 3.81), (0, -3.81), True, 3.302
    else:  # tp
        body += f'\t\t\t\t(circle (center 0.762 0) (radius 0.762) {stroke} (fill (type none)))\n'
        ref_at, val_at, hide_names, plen = (2.54, 1.27), (2.54, -1.27), True, G
    pin_txt = "".join(pin_sexp(num, pname, *pos[num][:2], pos[num][2], plen)
                      for num, pname, _ in pins)
    names = "(pin_names (offset 1.016) (hide yes))" if hide_names else "(pin_names (offset 1.016))"
    numbers = "(pin_numbers (hide yes))\n\t\t\t" if kind in ("r", "c", "led", "jp", "tp") else ""
    return (f'\t\t(symbol "{prefix}{name}"\n\t\t\t{numbers}{names}\n'
            f'\t\t\t(exclude_from_sim no) (in_bom yes) (on_board yes)\n'
            f'\t\t\t(property "Reference" "{refdes}" (at {ref_at[0]:.2f} {ref_at[1]:.2f} 0) {font()})\n'
            f'\t\t\t(property "Value" "{name}" (at {val_at[0]:.2f} {val_at[1]:.2f} 0) {font()})\n'
            f'\t\t\t(property "Footprint" "" (at 0 0 0) {font(True)})\n'
            f'\t\t\t(property "Datasheet" "~" (at 0 0 0) {font(True)})\n'
            f'\t\t\t(property "Description" "" (at 0 0 0) {font(True)})\n'
            f'\t\t\t(symbol "{name}_1_1"\n{body}{pin_txt}\t\t\t)\n'
            f'\t\t\t(embedded_fonts no)\n\t\t)\n'), ref_at, val_at


# ------------------------------------------------------------------ placement
PLACE = {"J1": (60.96, 152.4), "J2": (165.1, 76.2), "U1": (289.56, 86.36),
         "U2": (165.1, 152.4)}
col_x = {"C": 144.78, "R": 198.12, "D": 251.46, "JP": 251.46, "TP": 304.8}
row_y = {"C": 177.8, "R": 177.8, "D": 177.8, "JP": 198.12, "TP": 177.8}
counters = {}
for ref in PARTS:
    if ref in PLACE:
        continue
    key = ref.rstrip("0123456789")
    i = counters.get(key, 0)
    counters[key] = i + 1
    PLACE[ref] = (col_x[key], row_y[key] + i * 10.16)

TEXTS = [
    (20.32, 17.78, "XG Mobile port -> OCuLink 4i host adapter", 3.0),
    (20.32, 24.13, "PCIe lanes 0-3 and REFCLK pass straight through (no AC caps: they sit at each transmitter).", 1.5),
    (20.32, 27.94, "U1 answers the EC handshake (Docs/MCU.md) and runs the stock XG_Mobile_Dock_MCU firmware.", 1.5),
    (20.32, 31.75, "J1 footprint is an ESTIMATE - measure the harvested plug before ordering boards.", 1.5),
    (139.7, 142.24, "5 V from the port's own USB-C VBUS (R1 = Rd)", 1.5),
    (139.7, 170.18, "Decoupling", 1.5), (193.04, 170.18, "Pull-ups / pull-downs", 1.5),
    (246.38, 170.18, "Status / lock", 1.5), (299.72, 170.18, "Debug pads", 1.5),
]


def main():
    lib_body = "".join(lib_symbol(n)[0] for n in SYMBOLS)
    with open(os.path.join(ROOT, "lib", f"{LIB}.kicad_sym"), "w") as f:
        f.write('(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "xgm_oculink_gen")\n'
                '\t(generator_version "9.0")\n' + lib_body + ')\n')

    root_uuid = uid("root")
    out = [f'(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n'
           f'\t(uuid "{root_uuid}")\n\t(paper "A3")\n'
           f'\t(title_block\n\t\t(title "XGM to OCuLink Adapter")\n\t\t(rev "0.1")\n'
           f'\t\t(comment 1 "Generated by gen/make_sch.py - edit gen/design.py")\n\t)\n'
           f'\t(lib_symbols\n']
    geo = {}
    for n in SYMBOLS:
        txt, ref_at, val_at = lib_symbol(n, prefix=f"{LIB}:")
        geo[n] = (ref_at, val_at)
        out.append(txt)
    out.append('\t)\n')

    for x, y, text, size in TEXTS:
        out.append(f'\t(text "{text}" (exclude_from_sim no) (at {x} {y} 0)\n'
                   f'\t\t{font(size=size, justify="left bottom")}\n\t\t(uuid "{uid("text", text)}")\n\t)\n')

    for ref, (sym, value, fp, pins, lcsc, note) in PARTS.items():
        sx, sy = PLACE[ref]
        pos = symbol_pins(sym)
        for num, (px, py, side) in pos.items():
            x, y = round(sx + px, 2), round(sy - py, 2)
            net = pins.get(num)
            if net is None:
                out.append(f'\t(no_connect (at {x} {y}) (uuid "{uid("nc", ref, num)}"))\n')
                continue
            x2 = round(x - G, 2) if side == "L" else round(x + G, 2)
            ang, just = (180, "right bottom") if side == "L" else (0, "left bottom")
            out.append(f'\t(wire (pts (xy {x} {y}) (xy {x2} {y})) (stroke (width 0) (type default))'
                       f' (uuid "{uid("w", ref, num)}"))\n')
            out.append(f'\t(label "{net}" (at {x2} {y} {ang})\n\t\t{font(justify=just)}\n'
                       f'\t\t(uuid "{uid("l", ref, num)}")\n\t)\n')
        (rx, ry), (vx, vy) = geo[sym]
        props = [("Reference", ref, sx + rx, sy - ry, False),
                 ("Value", value, sx + vx, sy - vy, False),
                 ("Footprint", fp, sx, sy, True), ("Datasheet", "~", sx, sy, True),
                 ("Description", note, sx, sy, True)]
        if lcsc:
            props.append(("LCSC", lcsc, sx, sy, True))
        ptxt = "".join(f'\t\t(property "{k}" "{v}" (at {x:.2f} {y:.2f} 0) {font(h)})\n'
                       for k, v, x, y, h in props)
        pintxt = "".join(f'\t\t(pin "{num}" (uuid "{uid("p", ref, num)}"))\n' for num in pos)
        dnp = "yes" if False else "no"
        out.append(f'\t(symbol\n\t\t(lib_id "{LIB}:{sym}")\n\t\t(at {sx} {sy} 0)\n\t\t(unit 1)\n'
                   f'\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp {dnp})\n'
                   f'\t\t(uuid "{uid("s", ref)}")\n{ptxt}{pintxt}'
                   f'\t\t(instances\n\t\t\t(project "XGM_OCuLink_Adapter"\n\t\t\t\t(path "/{root_uuid}"\n'
                   f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')
    out.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    with open(os.path.join(ROOT, "XGM_OCuLink_Adapter.kicad_sch"), "w") as f:
        f.write("".join(out))
    print("schematic + symbol library written")


if __name__ == "__main__":
    main()
