#!/usr/bin/env python3
"""Generate the footprints that do not exist anywhere else:

* XGM_Plug_Straddle - the male XG Mobile plug, straddle-mounted on the board
  edge.  THE DIMENSIONS BELOW ARE ESTIMATES taken from the photos in
  Docs/images/cable_pcb_*.jpg.  Measure the harvested plug (or the ASUS cable
  head PCB it came from) and correct PLUG before ordering boards, then re-run
  make_pcb.py - the routing follows these numbers.
* SolderJumper_2_Open
"""
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PRETTY = os.path.join(os.path.dirname(HERE), "lib", "XGM_OCuLink.pretty")
NS = uuid.UUID("0d5b2c9e-3b6f-4f0e-8d52-6a41c1d1a001")

# Origin: centre of pad C1 in X, board edge in Y.  -Y is into the board.
PLUG = dict(
    pitch=0.5,        # contact pitch, both sections            (estimate)
    pad_w=0.28,       # solder pad width                        (estimate)
    pad_len=1.4,      # solder pad length                       (estimate)
    pad_edge=0.3,     # board edge to start of pad              (estimate)
    usb_gap=4.1,      # centre of C31 to centre of A1           (estimate)
    shell_w=0.7,      # shell tab pad                           (estimate)
    shell_len=1.2,
    shell_off=0.95,   # A1 / A12 centre to shell tab centre     (estimate)
    board_t=0.8,      # PCB thickness the plug straddles        (estimate)
)


def pad_y():
    return -(PLUG["pad_edge"] + PLUG["pad_len"] / 2)


def pad_x(name):
    """X of a plug pad.  C/D rows are stacked (Dn under Cn), the USB-C part
    follows the Type-C convention (B12 under A1)."""
    row, n = name[0], int(name[1:])
    p = PLUG["pitch"]
    if row in "CD":
        return -p * (n - 1)
    a1 = -p * 30 - PLUG["usb_gap"]
    if row == "A":
        return a1 - p * (n - 1)
    return a1 - p * (12 - n)


def u(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


def smd(name, x, y, w, h, side, shape="rect"):
    L = "F" if side == "F" else "B"
    return (f'\t(pad "{name}" smd {shape} (at {x:.3f} {y:.3f}) (size {w} {h})'
            f' (layers "{L}.Cu" "{L}.Mask" "{L}.Paste") (uuid "{u(name, side, x)}"))\n')


def header(name, descr, attr="smd"):
    def prop(k, v, y, layer, hide):
        h = " (hide yes)" if hide else ""
        return (f'\t(property "{k}" "{v}" (at 0 {y} 0) (layer "{layer}"){h} (uuid "{u(name, k)}")'
                f' (effects (font (size 0.8 0.8) (thickness 0.12))))\n')
    return (f'(footprint "{name}"\n\t(version 20241229)\n\t(generator "xgm_oculink_gen")\n'
            f'\t(generator_version "9.0")\n\t(layer "F.Cu")\n\t(descr "{descr}")\n'
            + prop("Reference", "REF**", 2.0, "F.SilkS", False)
            + prop("Value", name, 3.2, "F.Fab", False)
            + prop("Datasheet", "", 0, "F.Fab", True)
            + prop("Description", descr, 0, "F.Fab", True)
            + f'\t(attr {attr})\n')


def line(x1, y1, x2, y2, layer, w=0.1):
    return (f'\t(fp_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f})'
            f' (stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{u(layer, x1, y1, x2, y2)}"))\n')


def rect(x1, y1, x2, y2, layer, w=0.05):
    return (f'\t(fp_rect (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f})'
            f' (stroke (width {w}) (type solid)) (fill no) (layer "{layer}") (uuid "{u(layer, x1, y1, x2, y2)}"))\n')


def plug():
    P = PLUG
    y = pad_y()
    out = header("XGM_Plug_Straddle",
                 "ASUS XG Mobile plug, straddle mount, 86 pin. ESTIMATED DIMENSIONS - VERIFY BY MEASUREMENT")
    for n in range(1, 32):
        out += smd(f"C{n}", pad_x(f"C{n}"), y, P["pad_w"], P["pad_len"], "F")
        out += smd(f"D{n}", pad_x(f"D{n}"), y, P["pad_w"], P["pad_len"], "B")
    for n in range(1, 13):
        out += smd(f"A{n}", pad_x(f"A{n}"), y, P["pad_w"], P["pad_len"], "F")
        out += smd(f"B{n}", pad_x(f"B{n}"), y, P["pad_w"], P["pad_len"], "B")
    for x in (pad_x("A1") + P["shell_off"], pad_x("A12") - P["shell_off"]):
        for side in "FB":
            out += smd("SH", x, y, P["shell_w"], P["shell_len"], side)
    x_min, x_max = pad_x("A12") - 2.0, 2.0
    for side in "FB":
        out += rect(x_min, -2.0, x_max, 9.0, f"{side}.CrtYd")
        out += rect(x_min, 0.0, x_max, 8.5, f"{side}.Fab", 0.1)
        out += line(pad_x("C1") + 0.6, -1.7, pad_x("C1") + 0.6, -0.3, f"{side}.SilkS", 0.12)
    out += line(x_min, 0, x_max, 0, "Dwgs.User", 0.1)
    out += (f'\t(fp_text user "PCB edge - plug body this side" (at {(x_min + x_max) / 2:.2f} 1.0 0)'
            f' (layer "Dwgs.User") (uuid "{u("edge-text")}") (effects (font (size 0.8 0.8) (thickness 0.1))))\n')
    out += '\t(embedded_fonts no)\n)\n'
    with open(os.path.join(PRETTY, "XGM_Plug_Straddle.kicad_mod"), "w") as f:
        f.write(out)


def jumper():
    out = header("SolderJumper_2_Open", "Solder jumper, 2 pads, open", attr="exclude_from_pos_files exclude_from_bom")
    for name, x in (("1", -0.5), ("2", 0.5)):
        out += (f'\t(pad "{name}" smd rect (at {x} 0) (size 0.7 1.0) (layers "F.Cu" "F.Mask")'
                f' (uuid "{u("jp", name)}"))\n')
    out += rect(-1.1, -0.75, 1.1, 0.75, "F.CrtYd")
    out += rect(-1.0, -0.65, 1.0, 0.65, "F.SilkS", 0.12)
    out += '\t(embedded_fonts no)\n)\n'
    with open(os.path.join(PRETTY, "SolderJumper_2_Open.kicad_mod"), "w") as f:
        f.write(out)


if __name__ == "__main__":
    plug()
    jumper()
    print("footprints written")
