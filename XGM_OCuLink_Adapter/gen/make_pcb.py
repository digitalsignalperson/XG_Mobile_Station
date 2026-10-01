#!/usr/bin/env python3
"""Build XGM_OCuLink_Adapter.kicad_pcb from a KiCad netlist.

    kicad-cli sch export netlist --format kicadsexpr -o adapter.net \\
        ../XGM_OCuLink_Adapter.kicad_sch
    ./make_pcb.py adapter.net

Parts are placed from the PLACEMENT table, the PCIe pairs are routed by
construction (route_high_speed) and the remaining low-speed nets by the small
grid router in router.py.

The high-speed geometry is derived from the plug footprint parameters in
make_fp.py, so correcting those and re-running regenerates the routing.
Coordinates: X = 0 at plug pad C1, Y = 0 at the plug-side board edge,
-Y points into the board (towards the OCuLink connector).
"""
import math
import os
import re
import shutil
import sys

import pcbnew

from design import LIB, PARTS
from make_fp import PLUG, pad_x, pad_y
from make_sch import uid
from router import Router

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PRETTY = os.path.join(ROOT, "lib", f"{LIB}.pretty")
BOARD = os.path.join(ROOT, "XGM_OCuLink_Adapter.kicad_pcb")
OX, OY = 140.0, 110.0          # where the origin sits on the sheet

# ---------------------------------------------------------------- parameters
W_PAIR, GAP_PAIR = 0.16, 0.15  # ~85 ohm differential on 0.1 mm prepreg
D = (W_PAIR + GAP_PAIR) / 2    # centreline offset of each trace in a pair
W_LOOSE = 0.18                 # uncoupled bits at 0.5 mm connector pitch
W_SIG, W_GND = 0.15, 0.25
VIA, DRILL = 0.45, 0.3
VIA_SPREAD = 0.35              # half pitch of a differential via pair

PAD_END = -(PLUG["pad_edge"] + PLUG["pad_len"])   # inboard end of plug pads
PAD_Y = pad_y()
Y_GV = PAD_END - 0.5           # ground vias behind the plug pads
Y_RXV_NEAR = PAD_END - 1.15    # RX0/RX1 drop to the bottom layer here
Y_RXV_FAR = PAD_END - 3.3      # RX2/RX3 drop later (REFCLK crosses under RX2)
Y_CLK_RUN = PAD_END - 1.6      # REFCLK's sideways run on the bottom layer
Y_TX_JOG = PAD_END - 4.5
Y_B = PAD_END - 7.6            # OCuLink row B (PET, host transmit) pad centres
J2_X = pad_x("C1") - 5.0
J2_Y = Y_B - 4.305
Y_A = J2_Y + 2.115             # OCuLink row A (PER, host receive) pad centres
OCU_PAD_HALF = 0.455
Y_BG = Y_B + 1.0               # ground vias for row B, plug side
Y_GAP = (Y_A + Y_B) / 2        # signal vias between the two pad rows
Y_AG = Y_A - 0.865             # ground vias for row A, connector-front side
Y_FRONT = J2_Y + 0.4           # PERST# runs here, under the connector front

X_LEFT, X_RIGHT = pad_x("A12") - 4.5, 3.6
Y_TOP, Y_BOT = J2_Y - 4.7, 0.0

U1_X, U1_Y = -19.4, -12.3


def under_u1(dx, dy):
    """A 0402 on the bottom side, underneath the MCU body."""
    return (U1_X + dx, U1_Y + dy, 0, "B")


TP_X = X_LEFT + 1.1         # left-edge column for the LEDs
# ref: (x, y, rotation, side)
PLACEMENT = {
    "J1": (0, 0, 0, "F"), "J2": (J2_X, J2_Y, 180, "F"),
    "U1": (U1_X, U1_Y, 90, "F"),
    "U2": (-25.0, -4.3, 0, "F"),
    "C1": (-22.0, -4.9, 0, "F"), "C2": (-25.9, -6.7, 0, "F"),
    "R1": (-21.6, -3.3, 90, "F"), "R2": (-15.6, -3.1, 90, "F"),
    "D1": (TP_X, -8.8, 90, "F"), "R8": (TP_X, -11.3, 90, "F"),
    "D2": (TP_X, -15.8, 90, "F"), "R9": (TP_X, -13.3, 90, "F"),
    # decoupling sits under the MCU, next to its supply pins
    "C4": under_u1(-2.2, 2.2), "C6": under_u1(-2.2, 0.3),
    "C7": under_u1(1.2, 2.2), "C8": under_u1(1.2, 0.3),
    "C5": under_u1(1.8, -2.2), "R6": under_u1(-2.2, -1.9),
    # the rest goes on the bottom between the MCU and the plug
    "R3": (-23.6, -6.0, 0, "B"), "R4": (-20.9, -3.2, 0, "B"),
    "R5": (-23.6, -4.6, 0, "B"), "R7": (-21.2, -4.6, 0, "B"),
    "C3": (-23.6, -3.2, 0, "B"), "JP1": (-21.3, -6.2, 0, "B"),
}
for _i, _ref in enumerate(("TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "TP7")):
    # debug pads: a row along the top edge, on the bottom side
    PLACEMENT[_ref] = (X_LEFT + 1.6 + 2.0 * _i, Y_TOP + 1.1, 0, "B")

mm = pcbnew.FromMM


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


# ------------------------------------------------------------------ helpers
class Builder:
    def __init__(self, board):
        self.b = board
        self.nets = {}
        self.tracks = []     # (layer, (x1, y1), (x2, y2), width, net)
        self.vias = []       # (x, y, net)

    def net(self, name):
        if name not in self.nets:
            ni = self.b.FindNet(name)
            if ni is None:
                ni = pcbnew.NETINFO_ITEM(self.b, name)
                self.b.Add(ni)
            self.nets[name] = ni
        return self.nets[name]

    def track(self, layer, pts, width, net, lock=True):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(P(x1, y1))
            t.SetEnd(P(x2, y2))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(self.net(net))
            t.SetLocked(lock)
            self.b.Add(t)
            self.tracks.append((layer, (x1, y1), (x2, y2), width, net))

    def via(self, x, y, net, lock=True):
        v = pcbnew.PCB_VIA(self.b)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetPosition(P(x, y))
        v.SetWidth(pcbnew.F_Cu, mm(VIA))
        v.SetDrill(mm(DRILL))
        v.SetNet(self.net(net))
        v.SetLocked(lock)
        self.b.Add(v)
        self.vias.append((x, y, net))

    def zone(self, layers, net, pts, clearance=0.2, name=""):
        z = pcbnew.ZONE(self.b)
        ls = pcbnew.LSET()
        for layer in layers:
            ls.AddLayer(layer)
        z.SetLayerSet(ls)
        z.SetNet(self.net(net))
        z.SetZoneName(name)
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(mm(OX + x), mm(OY + y))
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(0.15))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        self.b.Add(z)
        return z


def offset_path(pts, off):
    """Parallel curve of a polyline.  Positive = +X side when heading -Y."""
    out = []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        def normal(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            return (-dy / L, dx / L)
        if i == 0:
            nx, ny = normal(pts[0], pts[1])
            out.append((x + nx * off, y + ny * off))
        elif i == n - 1:
            nx, ny = normal(pts[-2], pts[-1])
            out.append((x + nx * off, y + ny * off))
        else:
            n0, n1 = normal(pts[i - 1], pts[i]), normal(pts[i], pts[i + 1])
            mx, my = n0[0] + n1[0], n0[1] + n1[1]
            L = math.hypot(mx, my)
            mx, my = mx / L, my / L
            k = off / (mx * n1[0] + my * n1[1])
            out.append((x + mx * k, y + my * k))
    return out


def pair(bd, layer, name, centre, lead_in, lead_out):
    """Route a differential pair along `centre`.  lead_in/lead_out are
    callables(sign) returning the extra points before/after the coupled
    section for the P (+1, +X side) and N (-1) trace."""
    for sign, suffix in ((1, "_P"), (-1, "_N")):
        net = f"/{name}{suffix}"
        mid = offset_path(centre, sign * D)
        a, b = lead_in(sign), lead_out(sign)
        if a:
            bd.track(layer, a + [mid[0]], W_LOOSE, net)
        bd.track(layer, mid, W_PAIR, net)
        if b:
            bd.track(layer, [mid[-1]] + b, W_LOOSE, net)


# OCuLink pad X for our placement (rotated 180 degrees about J2_X)
def ocu_x(name):
    row, n = name[0], int(name[1:])
    local = (-4.75 if row == "A" else -5.25) + 0.5 * (n - 1)
    return J2_X - local


def route_high_speed(bd):
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    for lane in range(4):
        n = 1 + lane * 6
        # ------------------------------------------------ TX: top layer only
        cs = (pad_x(f"C{n}") + pad_x(f"C{n + 1}")) / 2
        bp = (3, 6, 15, 18)[lane]
        ct = (ocu_x(f"B{bp}") + ocu_x(f"B{bp + 1}")) / 2
        y_end = Y_BG - 0.3
        centre = [(cs, PAD_END - 0.245), (cs, Y_TX_JOG),
                  (ct, Y_TX_JOG - abs(ct - cs)), (ct, y_end)]
        pair(bd, F, f"TX{lane}", centre,
             lambda s: [(cs + s * 0.25, PAD_Y), (cs + s * 0.25, PAD_END - 0.15)],
             lambda s: [(ct + s * 0.25, y_end - 0.095), (ct + s * 0.25, Y_B)])

        # --------------------- RX: top stub -> bottom layer -> up between rows
        cs = (pad_x(f"C{n + 3}") + pad_x(f"C{n + 4}")) / 2
        ct = (ocu_x(f"A{bp}") + ocu_x(f"A{bp + 1}")) / 2
        cc = ct + 0.5          # corridor that clears the row-B ground vias
        yv = Y_RXV_NEAR if lane < 2 else Y_RXV_FAR
        yj = min(yv - 0.65, Y_CLK_RUN - 0.2) if lane < 2 else yv - 0.6
        for s, suffix in ((1, "_P"), (-1, "_N")):
            net = f"/RX{lane}{suffix}"
            bd.track(F, [(cs + s * 0.25, PAD_Y), (cs + s * 0.25, yv + 0.45),
                         (cs + s * VIA_SPREAD, yv + 0.35), (cs + s * VIA_SPREAD, yv)],
                     W_LOOSE, net)
            bd.via(cs + s * VIA_SPREAD, yv, net)
            bd.via(ct + s * VIA_SPREAD, Y_GAP, net)
            bd.track(F, [(ct + s * VIA_SPREAD, Y_GAP), (ct + s * VIA_SPREAD, Y_GAP - 0.2),
                         (ct + s * 0.25, Y_GAP - 0.3), (ct + s * 0.25, Y_A)],
                     W_LOOSE, net)
        centre = [(cs, yv - 0.495), (cs, yj), (cc, yj - abs(cc - cs)),
                  (cc, Y_BG - 0.45), (ct, Y_BG - 0.95), (ct, Y_GAP + 0.645)]
        pair(bd, B, f"RX{lane}", centre,
             lambda s: [(cs + s * VIA_SPREAD, yv), (cs + s * VIA_SPREAD, yv - 0.3)],
             lambda s: [(ct + s * VIA_SPREAD, Y_GAP + 0.45), (ct + s * VIA_SPREAD, Y_GAP)])

    # ------------- REFCLK: bottom layer, slides sideways under RX2's top stub
    cs = (pad_x("D19") + pad_x("D20")) / 2
    ct = (ocu_x("A12") + ocu_x("A13")) / 2
    cc = ct + 0.5
    centre = [(cs, PAD_END - 0.245), (cs, Y_CLK_RUN + 0.5), (cs + 0.5, Y_CLK_RUN),
              (cc - 0.5, Y_CLK_RUN), (cc, Y_CLK_RUN - 0.5), (cc, Y_BG - 0.45),
              (ct, Y_BG - 0.95), (ct, Y_GAP + 0.645)]
    pair(bd, B, "REFCLK", centre,
         lambda s: [(cs + s * 0.25, PAD_Y), (cs + s * 0.25, PAD_END - 0.15)],
         lambda s: [(ct + s * VIA_SPREAD, Y_GAP + 0.45), (ct + s * VIA_SPREAD, Y_GAP)])
    for s, suffix in ((1, "_P"), (-1, "_N")):
        net = f"/REFCLK{suffix}"
        bd.via(ct + s * VIA_SPREAD, Y_GAP, net)
        bd.track(F, [(ct + s * VIA_SPREAD, Y_GAP), (ct + s * VIA_SPREAD, Y_GAP - 0.2),
                     (ct + s * 0.25, Y_GAP - 0.3), (ct + s * 0.25, Y_A)], W_LOOSE, net)

    # ------- PERST#: row B pad -> via between the rows -> around the front
    x = ocu_x("B12")
    xv = x + 0.45
    bd.track(F, [(x, Y_B), (x, Y_B - 0.65), (xv, Y_GAP)], W_SIG, "/PERST#")
    bd.via(xv, Y_GAP, "/PERST#")
    bd.track(B, [(xv, Y_GAP), (xv + 0.3, Y_GAP - 0.3), (xv + 0.3, Y_FRONT + 0.3),
                 (xv, Y_FRONT), (J2_X - 8.5, Y_FRONT)], W_SIG, "/PERST#")

    # --------------------------------------------------------- ground vias
    for n in range(3, 22, 3):                       # plug, between the pairs
        x = pad_x(f"C{n}")
        bd.via(x, Y_GV, "/GND")
        bd.track(F, [(x, PAD_Y), (x, Y_GV)], W_GND, "/GND")
        bd.track(B, [(x, PAD_Y), (x, Y_GV)], W_GND, "/GND")
    for n in (2, 5, 8, 11, 14, 17, 20):
        x = ocu_x(f"B{n}")                          # OCuLink row B
        bd.via(x, Y_BG, "/GND")
        bd.track(F, [(x, Y_B), (x, Y_BG)], W_GND, "/GND")
        x = ocu_x(f"A{n}")                          # OCuLink row A
        bd.via(x, Y_AG, "/GND")
        bd.track(F, [(x, Y_A), (x, Y_AG)], W_GND, "/GND")
    # VBUS: tie the top and bottom contacts together
    for name in ("A4", "A9"):
        x = pad_x(name)
        bd.via(x, Y_GV, "/VBUS")
        bd.track(F, [(x, PAD_Y), (x, Y_GV)], W_GND, "/VBUS")
        bd.track(B, [(x, PAD_Y), (x, Y_GV)], W_GND, "/VBUS")
    # C24/C27/C30 have sideband pads right underneath, so there is no room
    # for a via each: tie them together and let the router find one via
    y = PAD_END - 0.4
    for name in ("C24", "C27", "C30"):
        bd.track(F, [(pad_x(name), PAD_Y), (pad_x(name), y)], 0.2, "/GND")
    bd.track(F, [(pad_x("C24"), y), (pad_x("C30"), y)], 0.2, "/GND")
    # LOCK_DET (D23) sits under RX3: escape it by hand to the left
    x = pad_x("D23")
    bd.track(B, [(x, PAD_Y), (x, Y_RXV_FAR + 0.75), (x - 0.5, Y_RXV_FAR + 0.75)],
             W_SIG, "/LOCK_DET")


def outline(board):
    c = 1.0
    pts = [(X_LEFT, Y_BOT), (X_RIGHT, Y_BOT), (X_RIGHT, Y_TOP + c),
           (X_RIGHT - c, Y_TOP), (X_LEFT + c, Y_TOP), (X_LEFT, Y_TOP + c)]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(*a))
        s.SetEnd(P(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)


def text(board, s, x, y, layer, size=0.8, mirror=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetMirrored(mirror)
    board.Add(t)


def read_netlist(path):
    """-> {(ref, pin): net name} from a KiCad s-expression netlist."""
    txt = open(path).read()
    out = {}
    for m in re.finditer(r'\(net\s+\(code "\d+"\)\s+\(name "([^"]*)"\)(.*?)(?=\(net\s+\(code|\Z)', txt, re.S):
        for ref, pin in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', m.group(2)):
            out[(ref, pin)] = m.group(1)
    return out


def _stackup():
    """0.8 mm 4-layer, thin prepreg (approximates JLC04081H-3313)."""
    cu = lambda n, t: f'\t\t\t(layer "{n}" (type "copper") (thickness {t}))\n'
    di = lambda n, kind, t: (f'\t\t\t(layer "dielectric {n}" (type "{kind}") (thickness {t})'
                             f' (material "FR4") (epsilon_r 4.1) (loss_tangent 0.02))\n')
    core = round(PLUG["board_t"] - 2 * 0.035 - 2 * 0.0152 - 2 * 0.0994, 4)
    return ('\t\t(stackup\n'
            '\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))\n'
            '\t\t\t(layer "F.Paste" (type "Top Solder Paste"))\n'
            '\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))\n'
            + cu("F.Cu", 0.035) + di(1, "prepreg", 0.0994) + cu("In1.Cu", 0.0152)
            + di(2, "core", core) + cu("In2.Cu", 0.0152) + di(3, "prepreg", 0.0994)
            + cu("B.Cu", 0.035) +
            '\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))\n'
            '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))\n'
            '\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))\n'
            '\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)\n')


STACKUP = _stackup()


def save(board):
    """SaveBoard rewrites the .kicad_pro with defaults, so put ours back."""
    pcbnew.SaveBoard(BOARD, board)
    txt = open(BOARD).read()
    if "(stackup" not in txt:
        txt = txt.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1)
        open(BOARD, "w").write(txt)
    shutil.copyfile(os.path.join(HERE, "project_settings.json"),
                    os.path.splitext(BOARD)[0] + ".kicad_pro")


BOARD_AREA = lambda: [(X_LEFT, Y_BOT), (X_RIGHT, Y_BOT), (X_RIGHT, Y_TOP), (X_LEFT, Y_TOP)]
OUTLINE = lambda c=1.0: [(X_LEFT, Y_BOT), (X_RIGHT, Y_BOT), (X_RIGHT, Y_TOP + c),
                         (X_RIGHT - c, Y_TOP), (X_LEFT + c, Y_TOP), (X_LEFT, Y_TOP + c)]

# Low-speed nets in routing order: (net, width)
ROUTE_ORDER = [
    ("/CC1", 0.15), ("/LED_W_K", 0.15), ("/LED_R_K", 0.15), ("GND", 0),
    ("/LOCK_SW", 0.15), ("/LED_WHITE#", 0.15), ("/LED_RED#", 0.15),
    ("/NRST", 0.15), ("/VBUS", 0.25), ("/+3V3", 0.25),
    ("/CON_DET", 0.15), ("/PWREN#", 0.15), ("/RST#", 0.15), ("/PWROK", 0.15),
    ("/AC_LOSS", 0.15), ("/MCU_IRQ#", 0.15), ("/SDA", 0.15), ("/SCL", 0.15),
    ("/LOCK_DET", 0.15), ("GND_LATE", 0), ("/PERST#", 0.15),
    ("/CON_DET_TOWER#", 0.15),
    ("/UART_TX", 0.15), ("/SWDIO", 0.15), ("/SWCLK", 0.15),
    ("/BOOT0", 0.15),
]


def make_router(board, bd):
    rt = Router(X_LEFT, Y_TOP, X_RIGHT, Y_BOT)
    lay = {pcbnew.F_Cu: 0, pcbnew.B_Cu: 1}
    to = pcbnew.ToMM
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            x0, y0 = to(bb.GetLeft()) - OX, to(bb.GetTop()) - OY
            x1, y1 = to(bb.GetRight()) - OX, to(bb.GetBottom()) - OY
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                rt.add_hole((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0)
                continue
            net = pad.GetNetname() or f"nc:{fp.GetReference()}:{pad.GetNumber()}"
            for layer, idx in lay.items():
                if pad.IsOnLayer(layer):
                    rt.add_rect(idx, net, x0, y0, x1, y1)
    for layer, a, b, width, net in bd.tracks:
        rt.add_seg(lay[layer], net, a, b, width)
    for x, y, net in bd.vias:
        rt.add_via(net, x, y)
    pts = OUTLINE()
    for a, b in zip(pts, pts[1:] + pts[:1]):       # stay 0.25 mm+ off the edge
        for idx in (0, 1):
            rt.add_seg(idx, None, a, b, 0.4)
    # keep the low-speed nets out of the PCIe corridor
    fence = pad_x("D23") - 0.25
    rt.fences += [(None, fence, Y_TOP, X_RIGHT, Y_BOT),
                  (None, J2_X - 8.2, Y_TOP, X_RIGHT, Y_FRONT + 0.5)]
    return rt


def route_low_speed(board, bd, attempts=1):
    """Sequential routing with no rip-up: when a net cannot be completed it is
    moved to the front of the queue and everything is routed again."""
    order = list(ROUTE_ORDER)
    # the plug's C24/C27/C30 ground pads wait until the sideband pads below
    # them have escaped, otherwise their vias wall those pads in
    late = lambda x, y: pad_x("C31") - 0.3 < x < pad_x("C24") + 0.3 and y > PAD_END - 0.2
    best = None
    for attempt in range(attempts):
        rt = make_router(board, bd)
        stubs, failed = [], []
        for net, width in order:
            if net == "GND":
                stubs += rt.ground_stubs("/GND", skip=late)
            elif net == "GND_LATE":
                stubs += rt.ground_stubs("/GND", reach=200.0)
            elif rt.route_net(net, width):
                failed.append((net, width))
        stubs += rt.ground_stubs("/GND", reach=200.0)
        score = len(failed) + len(stubs)
        print(f"  attempt {attempt + 1}: unrouted nets {[n for n, _ in failed]},"
              f" ground pads without via {len(stubs)}", flush=True)
        if best is None or score < best[0]:
            best = (score, rt)
        if score == 0 or not failed:
            break
        order = failed + [o for o in order if o not in failed]
    score, rt = best
    for layer, pts, width, net in rt.new_tracks:
        bd.track(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu, pts, width, net, lock=False)
    for x, y, net in rt.new_vias:
        bd.via(x, y, net, lock=False)
    print(f"low-speed routing: {len(rt.new_tracks)} tracks, {len(rt.new_vias)} vias,"
          f" {score} connections left open")


def build(netlist):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    board.GetDesignSettings().SetBoardThickness(mm(PLUG["board_t"]))
    bd = Builder(board)
    nets = read_netlist(netlist)

    for ref, (sym, value, fpname, _, lcsc, note) in PARTS.items():
        name = fpname.split(":")[1]
        fp = pcbnew.FootprintLoad(PRETTY, name)
        fp.SetFPID(pcbnew.LIB_ID(LIB, name))
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPath(pcbnew.KIID_PATH(f"/{uid('s', ref)}"))
        x, y, rot, side = PLACEMENT[ref]
        board.Add(fp)
        fp.SetPosition(P(x, y))
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            n = nets.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(bd.net(n))
        for f in fp.GetFields():
            if f.GetName() == "LCSC":
                f.SetText(lcsc)
            elif f.GetName() == "Description":
                f.SetText(note)
            elif f.GetName() == "Datasheet":
                f.SetText("")
        fp.SetExcludedFromBOM(False)
        fp.SetExcludedFromPosFiles(ref[:2] in ("TP", "JP", "J1"))
        fp.Reference().SetVisible(ref[0] in "JU")
        fp.Value().SetVisible(False)

    outline(board)
    route_high_speed(bd)
    route_low_speed(board, bd)

    bd.zone([pcbnew.In1_Cu, pcbnew.In2_Cu], "/GND", BOARD_AREA(), name="GND planes")
    bd.zone([pcbnew.F_Cu, pcbnew.B_Cu], "/GND", BOARD_AREA(), clearance=0.25, name="GND pour")
    F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
    text(board, "XGM-OCuLink r0.1", U1_X, Y_TOP + 0.75, F, 0.6)
    text(board, "W", PLACEMENT["D1"][0] + 1.1, PLACEMENT["D1"][1], F, 0.6)
    text(board, "R", PLACEMENT["D2"][0] + 1.1, PLACEMENT["D2"][1], F, 0.6)
    for ref, label in (("TP1", "DIO"), ("TP2", "CLK"), ("TP3", "RST"), ("TP4", "3V3"),
                       ("TP5", "GND"), ("TP6", "TX"), ("TP7", "5V")):
        x, y = PLACEMENT[ref][:2]
        text(board, label, x, y + 1.2, B, 0.6, mirror=True)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save(board)
    print("board written:", BOARD)


if __name__ == "__main__":
    build(sys.argv[1])
