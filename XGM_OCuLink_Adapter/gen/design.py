"""Single source of truth for the XGM -> OCuLink adapter: parts, pins and nets.

Both the schematic generator (make_sch.py) and the board generator
(make_pcb.py) read this file.  Pin/net data for the XG Mobile plug comes from
Docs/Connector.md, the OCuLink host pinout from SFF-9402 Rev 1.1 Table 7-1
(Root side, SFF-8621 42-circuit) and the MCU pin assignment is identical to
the Lite dock so that the stock XG_Mobile_Dock_MCU firmware runs unmodified.
"""

LIB = "XGM_OCuLink"

# --------------------------------------------------------------------------
# XG Mobile plug (86 pins).  None = not connected.
# --------------------------------------------------------------------------
xgm = {}
for lane in range(4):
    base = 1 + lane * 6
    xgm[f"C{base}"] = f"TX{lane}_P"
    xgm[f"C{base + 1}"] = f"TX{lane}_N"
    xgm[f"C{base + 2}"] = "GND"
    xgm[f"C{base + 3}"] = f"RX{lane}_P"
    xgm[f"C{base + 4}"] = f"RX{lane}_N"
    xgm[f"C{base + 5}"] = "GND"
# lane 4 (C25..C29) is left open, the host trains down to x4
xgm.update({"C25": None, "C26": None, "C27": "GND", "C28": None, "C29": None,
            "C30": "GND", "C31": "CON_DET_TOWER#"})
# lanes 5..7 (D1..D17) are left open
for n in range(1, 18):
    xgm[f"D{n}"] = "GND" if n % 3 == 0 else None
xgm.update({
    "D18": "GND", "D19": "REFCLK_P", "D20": "REFCLK_N", "D21": "GND",
    "D22": None,              # Reserve_NB
    "D23": "LOCK_DET",        # CON_SW1_DET_NB
    "D24": "SCL",             # AGPU_SMB1_CLK
    "D25": "SDA",             # AGPU_SMB1_DAT
    "D26": "MCU_IRQ#",        # EC_ACGPU_MCU_IRQ#
    "D27": "AC_LOSS",         # P_AC_LOSS_10
    "D28": "PWROK",           # DGPU_PWROK
    "D29": "RST#",            # GPU_RST#
    "D30": "PWREN#",          # DGPU_PWR_EN#
    "D31": "CON_DET",         # CON_DET_NB
})
# USB-C part: only VBUS/GND/CC1 are used (5 V supply for the MCU)
for n in range(1, 13):
    xgm[f"A{n}"] = None
    xgm[f"B{n}"] = None
xgm.update({"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
            "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
            "A5": "CC1", "SH": "GND"})

XGM_NAMES = {
    "C31": "CON_DET_TOWER#", "D19": "PCIE_CLKP", "D20": "PCIE_CLKN",
    "D22": "Reserve_NB", "D23": "CON_SW1_DET", "D24": "SMB1_CLK",
    "D25": "SMB1_DAT", "D26": "MCU_IRQ#", "D27": "P_AC_LOSS",
    "D28": "PWROK", "D29": "RST#", "D30": "PWR_EN#", "D31": "CON_DET_NB",
    "A2": "TX1+", "A3": "TX1-", "A4": "VBUS", "A5": "CC1", "A6": "D+",
    "A7": "D-", "A8": "SBU1", "A9": "VBUS", "A10": "RX2-", "A11": "RX2+",
    "B2": "TX2+", "B3": "TX2-", "B4": "VBUS", "B5": "CC2", "B6": "D+",
    "B7": "D-", "B8": "SBU2", "B9": "VBUS", "B10": "RX1-", "B11": "RX1+",
    "SH": "SHELL",
}
for lane in range(8):
    row, base = ("C", 1 + lane * 6) if lane < 5 else ("D", 1 + (lane - 5) * 6)
    XGM_NAMES[f"{row}{base}"] = f"PCIE_TXP{lane}"
    XGM_NAMES[f"{row}{base + 1}"] = f"PCIE_TXN{lane}"
    XGM_NAMES[f"{row}{base + 3}"] = f"PCIE_RXP{lane}"
    XGM_NAMES[f"{row}{base + 4}"] = f"PCIE_RXN{lane}"


def xgm_pin_name(p):
    if p in XGM_NAMES:
        return XGM_NAMES[p]
    return "GND" if xgm.get(p) == "GND" else p


# --------------------------------------------------------------------------
# OCuLink 4i receptacle, host/root pinout
# --------------------------------------------------------------------------
OCU_NAMES = {
    "A1": "3V3_VACT_RX", "A9": "BP_TYPE", "A10": "CWAKE#",
    "A12": "REFCLK+", "A13": "REFCLK-", "A21": "5V_2",
    "B1": "5V_1", "B9": "2W_CLK", "B10": "2W_DATA",
    "B12": "PERST#", "B13": "CPRSNT#", "B21": "3V3_VACT_TX", "SH": "SHELL",
}
ocu = {"SH": "GND"}
for row in "AB":
    for n in (2, 5, 8, 11, 14, 17, 20):
        ocu[f"{row}{n}"] = "GND"
        OCU_NAMES[f"{row}{n}"] = "GND"
for lane, n in enumerate((3, 6, 15, 18)):
    # row A = PER (host receives), row B = PET (host transmits)
    ocu[f"A{n}"], ocu[f"A{n + 1}"] = f"RX{lane}_P", f"RX{lane}_N"
    ocu[f"B{n}"], ocu[f"B{n + 1}"] = f"TX{lane}_P", f"TX{lane}_N"
    OCU_NAMES[f"A{n}"], OCU_NAMES[f"A{n + 1}"] = f"PERp{lane}", f"PERn{lane}"
    OCU_NAMES[f"B{n}"], OCU_NAMES[f"B{n + 1}"] = f"PETp{lane}", f"PETn{lane}"
ocu.update({"A12": "REFCLK_P", "A13": "REFCLK_N", "B12": "PERST#"})
for p in ("A1", "A9", "A10", "A21", "B1", "B9", "B10", "B13", "B21"):
    ocu[p] = None

# --------------------------------------------------------------------------
# STM32F030C8T6, same pin use as the Lite dock (stock firmware compatible)
# --------------------------------------------------------------------------
MCU_PINS = [
    (1, "VDD", "+3V3"), (2, "PC13", "LOCK_SW"), (3, "PC14", "LED_WHITE#"),
    (4, "PC15", "LED_RED#"), (5, "PF0", "LOCK_DET"), (6, "PF1", None),
    (7, "NRST", "NRST"), (8, "VSSA", "GND"), (9, "VDDA", "+3V3"),
    (10, "PA0", "CON_DET"), (11, "PA1", "PWREN#"), (12, "PA2", "RST#"),
    (13, "PA3", "PWROK"), (14, "PA4", "AC_LOSS"), (15, "PA5", "MCU_IRQ#"),
    (16, "PA6", None), (17, "PA7", None), (18, "PB0", None),
    (19, "PB1", None), (20, "PB2", None), (21, "PB10", None),
    (22, "PB11", None), (23, "VSS", "GND"), (24, "VDD", "+3V3"),
    (25, "PB12", None), (26, "PB13", None), (27, "PB14", None),
    (28, "PB15", None), (29, "PA8", None), (30, "PA9", "UART_TX"),
    (31, "PA10", None), (32, "PA11", None), (33, "PA12", None),
    (34, "PA13", "SWDIO"), (35, "PF6", None), (36, "PF7", None),
    (37, "PA14", "SWCLK"), (38, "PA15", None), (39, "PB3", None),
    (40, "PB4", None), (41, "PB5", "PERST#"), (42, "PB6", None),
    (43, "PB7", None), (44, "BOOT0", "BOOT0"), (45, "PB8", "SCL"),
    (46, "PB9", "SDA"), (47, "VSS", "GND"), (48, "VDD", "+3V3"),
]

# --------------------------------------------------------------------------
# Symbols: name -> (kind, [(number, pin name, side)])
# --------------------------------------------------------------------------
SYMBOLS = {
    "XGM_Plug": ("box", [(p, xgm_pin_name(p), "L")
                         for p in [f"C{n}" for n in range(1, 32)] +
                                  [f"A{n}" for n in range(1, 13)]] +
                        [(p, xgm_pin_name(p), "R")
                         for p in [f"D{n}" for n in range(1, 32)] +
                                  [f"B{n}" for n in range(12, 0, -1)]] +
                        [("SH", "SHELL", "R")]),
    "OCuLink_4i_Host": ("box", [(f"A{n}", OCU_NAMES.get(f"A{n}", f"A{n}"), "L")
                                for n in range(1, 22)] +
                               [(f"B{n}", OCU_NAMES.get(f"B{n}", f"B{n}"), "R")
                                for n in range(1, 22)] +
                               [("SH", "SHELL", "R")]),
    "STM32F030C8Tx": ("box", [(str(n), name, "L" if n <= 24 else "R")
                              for n, name, _ in MCU_PINS]),
    "XC6206PxxxMR": ("box", [("3", "VIN", "L"), ("1", "GND", "L"),
                             ("2", "VOUT", "R")]),
    "R": ("r", [("1", "~", "L"), ("2", "~", "R")]),
    "C": ("c", [("1", "~", "L"), ("2", "~", "R")]),
    "LED": ("led", [("1", "K", "L"), ("2", "A", "R")]),
    "SolderJumper_2_Open": ("jp", [("1", "A", "L"), ("2", "B", "R")]),
    "TestPoint": ("tp", [("1", "1", "L")]),
}

# --------------------------------------------------------------------------
# Parts: ref -> (symbol, value, footprint, {pin: net}, LCSC part, note)
# --------------------------------------------------------------------------
FP = lambda n: f"{LIB}:{n}"
R0402, C0402 = FP("R_0402_1005Metric"), FP("C_0402_1005Metric")


def two(a, b):
    return {"1": a, "2": b}


PARTS = {
    "J1": ("XGM_Plug", "XG Mobile plug (harvested)", FP("XGM_Plug_Straddle"),
           xgm, "", "From ASUS XG Mobile cable; not sold separately"),
    "J2": ("OCuLink_4i_Host", "G14A421211112HR",
           FP("Amphenol_G14A421211112HR"), ocu, "",
           "OCuLink 4i right-angle receptacle (SFF-8612)"),
    "U1": ("STM32F030C8Tx", "STM32F030C8T6", FP("LQFP-48_7x7mm_P0.5mm"),
           {str(n): net for n, _, net in MCU_PINS}, "C23922", ""),
    "U2": ("XC6206PxxxMR", "XC6206P332MR", FP("SOT-23"),
           {"1": "GND", "2": "+3V3", "3": "VBUS"}, "C5446", "3.3 V LDO"),
    "C1": ("C", "1uF", C0402, two("VBUS", "GND"), "C52923", ""),
    "C2": ("C", "1uF", C0402, two("+3V3", "GND"), "C52923", ""),
    "C3": ("C", "4.7uF", C0402, two("+3V3", "GND"), "C23733", ""),
    "C4": ("C", "100nF", C0402, two("+3V3", "GND"), "C1525", "U1 pin 1"),
    "C5": ("C", "100nF", C0402, two("+3V3", "GND"), "C1525", "U1 pin 24"),
    "C6": ("C", "100nF", C0402, two("+3V3", "GND"), "C1525", "U1 pin 48"),
    "C7": ("C", "100nF", C0402, two("+3V3", "GND"), "C1525", "U1 pin 9"),
    "C8": ("C", "100nF", C0402, two("NRST", "GND"), "C1525", ""),
    "R1": ("R", "5.1k", R0402, two("CC1", "GND"), "C25905",
           "USB-C Rd: makes the host source 5 V on VBUS"),
    "R2": ("R", "10k", R0402, two("CON_DET_TOWER#", "GND"), "C25744",
           "Tells the EC a dock is attached"),
    "R3": ("R", "10k", R0402, two("+3V3", "SCL"), "C25744", ""),
    "R4": ("R", "10k", R0402, two("+3V3", "SDA"), "C25744", ""),
    "R5": ("R", "10k", R0402, two("BOOT0", "GND"), "C25744", ""),
    "R6": ("R", "10k", R0402, two("+3V3", "NRST"), "C25744", ""),
    "R7": ("R", "10k", R0402, two("+3V3", "PERST#"), "C25744", ""),
    "R8": ("R", "1k", R0402, two("LED_WHITE#", "LED_W_K"), "C11702", ""),
    "R9": ("R", "1k", R0402, two("LED_RED#", "LED_R_K"), "C11702", ""),
    "D1": ("LED", "White", FP("LED_0603_1608Metric"),
           two("LED_W_K", "+3V3"), "C2290", "Connected / locked"),
    "D2": ("LED", "Red", FP("LED_0603_1608Metric"),
           two("LED_R_K", "+3V3"), "C2286", "eGPU powered"),
    "JP1": ("SolderJumper_2_Open", "LOCK", FP("SolderJumper_2_Open"),
            two("LOCK_SW", "GND"), "", "Open = locked. Bridge = unlocked"),
    "TP1": ("TestPoint", "SWDIO", FP("TestPoint_Pad_D1.0mm"),
            {"1": "SWDIO"}, "", ""),
    "TP2": ("TestPoint", "SWCLK", FP("TestPoint_Pad_D1.0mm"),
            {"1": "SWCLK"}, "", ""),
    "TP3": ("TestPoint", "NRST", FP("TestPoint_Pad_D1.0mm"),
            {"1": "NRST"}, "", ""),
    "TP4": ("TestPoint", "3V3", FP("TestPoint_Pad_D1.0mm"),
            {"1": "+3V3"}, "", ""),
    "TP5": ("TestPoint", "GND", FP("TestPoint_Pad_D1.0mm"),
            {"1": "GND"}, "", ""),
    "TP6": ("TestPoint", "UART_TX", FP("TestPoint_Pad_D1.0mm"),
            {"1": "UART_TX"}, "", "115200 8N1 debug log"),
    "TP7": ("TestPoint", "VBUS", FP("TestPoint_Pad_D1.0mm"),
            {"1": "VBUS"}, "", ""),
}

DIFF_NETS = [f"{d}{l}_{p}" for d in ("TX", "RX") for l in range(4)
             for p in "PN"] + ["REFCLK_P", "REFCLK_N"]
