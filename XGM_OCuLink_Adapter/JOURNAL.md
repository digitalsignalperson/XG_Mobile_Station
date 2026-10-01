Design Journal: XGM to OCuLink Adapter
======================================
This is a record of how revision 0.1 of the adapter was produced on 2026-10-01: what was investigated, what was decided and why, what went wrong, and what is still unknown. The design itself is described in the [README](README.md).

The work was done by an AI assistant (Claude) in one session, from the contents of this repository and public sources. Nothing was built or measured. Every statement below about hardware behaviour is either taken from the repository's documentation, taken from a cited source, or marked as an assumption.

## Starting point
The question was whether a small adapter could plug directly into the XGM port and present an OCuLink port, so that an off-the-shelf OCuLink eGPU dock could be used. The project author had answered that it is possible, that the repository holds enough information, and that "you have twice the cable length and thus need redrivers".

## Summary of the outcome
| Item                       | Result                                                                        |
|----------------------------|-------------------------------------------------------------------------------|
| Schematic                  | Complete. ERC: 0 violations                                                   |
| Board                      | 4 layers, 0.8 mm, 32.7 x 18.3 mm. DRC: 0 violations, 0 unconnected, 0 schematic parity issues |
| PCIe pairs                 | Lane order and polarity preserved. Intra-pair skew 0 µm on all nine pairs     |
| Firmware                   | No changes: MCU and pin assignment copied from the Lite dock                  |
| Ready to manufacture       | **No.** The plug footprint is estimated from photos                           |
| Tested on hardware         | No                                                                            |

## Tools used
| Tool                                  | Used for                                                                |
|---------------------------------------|-------------------------------------------------------------------------|
| KiCad 10.0.6, `kicad-cli`             | Netlist export, ERC, DRC with schematic parity, SVG plots               |
| KiCad `pcbnew` Python module          | Extracting footprints from existing boards, building the new board      |
| Python 3.14, numpy, scipy             | Generators, the grid router, connected-component labelling              |
| `rsvg-convert`, ImageMagick           | Turning plots into images so the layout could be inspected              |
| `pdftotext`                           | Searching the SFF-9402 specification (its tables are images, see below) |
| git                                   | Fetching two Antmicro reference designs                                 |
| Temurin JRE 21, Freerouting 2.1.0     | Tried for the low-speed nets, then abandoned. Not needed to regenerate  |

The KiCad standard symbol and footprint libraries were not installed on the machine. Generic footprints (0402, 0603, SOT-23, LQFP-48, test pad) were therefore extracted from `XG_Mobile_Dock_Lite.kicad_pcb`, and all symbols were generated.

## Log

### 1. Understanding the port
| Task | Goal | Result |
|------|------|--------|
| Read `Docs/Connector.md`, `Connector_GC33.md` | Pinout of the 86-pin port | 62 pins of PCIe and sideband (rows C, D) plus a full USB-C port (rows A, B). Lanes 0-4 are on row C, lanes 5-7 and all sidebands on row D |
| Read `Docs/MCU.md`, `Docs/Diary.md` | What a dock must do before the host enables PCIe | Sideband sequence plus an SMBus exchange with the embedded controller. Plain pull-ups are not enough: the diary records an ACPI bug when "connected" and "locked" assert together, and the BIOS shows an error screen on reboot without the SMBus handshake. An MCU is required |
| Export the Lite dock netlist with `kicad-cli` | Find the minimum circuit that is known to work | PCIe lanes go straight from cable to slot with no components. One 10 kΩ pulls `CON_DET_TOWER#` low. An STM32F030C8T6 handles everything else. SMBus has 10 kΩ pull-ups |
| Read `XG_Mobile_Dock_MCU/Core/Src/xg_mobile_dock.c` and the GPIO setup in `main.c` | Which MCU pins matter, and what happens to the unused ones | State machine driven by SMBus register 1, `CON_DET`, lock switch and `PWREN#`. `PERST#` mirrors `GPU_RST#`. Lock input has an internal pull-up and reads "locked" when high. Fan, ADC, second I2C and external-board pins can be left open |

### 2. The plug
| Task | Goal | Result |
|------|------|--------|
| Look for a plug footprint in `Footprints/` | Reuse it | None exists. Every board here mates with the far end of the ASUS cable. `2351970-1` in `XG_Mobile.pretty` is a power connector |
| Web search and the parts-store listing | Buy the plug | Not possible. The part sold as "XG Mobile dock connector" (12019-00170600, $49) is the receptacle for the laptop motherboard |
| Search for an existing XGM to OCuLink adapter | Avoid redoing work | None found. GitHub discussion #10 and issue #21 ask for one; neither led to a design |
| Study `Docs/images/cable_pcb_1..8.jpg` | Learn how the plug is mounted | It straddles the board edge: rows A and C on one face, B and D on the other. Silkscreen in the photos shows D1 under C1 and B12 under A1. Pad pitch is the same in both sections |
| Estimate dimensions from the photos | Get a placeholder footprint | 0.5 mm pitch assumed (the usual USB-C plug pitch). The gap between the sections came out as about 4.1 mm by counting pixels against that pitch. Pad size, shell tabs, edge cut-outs and board thickness are guesses |

This is the unknown that could not be resolved. It decided the structure of the whole project: the footprint is parametric, and the board is generated from it, so the numbers can be corrected later.

### 3. The OCuLink side
| Task | Goal | Result |
|------|------|--------|
| Recall the pinout from memory | Quick start | Not trusted. The sideband positions could not be reconstructed with confidence |
| Extract netlists from Antmicro's `oculink-pcie-adapter` (device) and `job-oculink-expansion` (host) | Two independent real designs | They agree with each other and show the cable swaps rows: host A(n) connects to device B(n). Host transmit is on row B, host receive on row A, clock on A12/A13, reset on B12 |
| Fetch SFF-9402 Rev 1.1 | Confirm against the standard | The text extract contained no tables (they are images). Reading pages 25 and 30 as images gave Table 7-1 and 7-6, which match the Antmicro host pinout. A1/A21/B1/B21 are power pins that standard cables do not wire |
| Take the receptacle footprint from the Antmicro board | A drawn, used footprint | Amphenol G14A421211112HR. All pads on one side, two rows 2.19 mm apart, row B at the rear. Two of its own pads sit 0.136 mm from its locating holes |

### 4. Electrical decisions
| Question | Options considered | Decision and reason |
|----------|--------------------|---------------------|
| Redrivers? | Add a redriver; stay passive | Passive. The author's remark assumed the ASUS cable stays in the path. With the plug on the board the added length is about 10 mm. A redriver would also need power, layout area and tuning. Revisit if PCIe 4.0 proves unstable |
| AC coupling capacitors? | Add; omit | Omit. They belong at each transmitter. Host signal names end in `_C` (after the capacitors) and the Lite dock has none |
| Which MCU? | Smaller package (TSSOP-20, QFN) with ported firmware; same LQFP-48 | Same part on the same pins. Costs about 9 x 9 mm of board but the released firmware binary should run unchanged, which removes a whole class of risk |
| Power source? | External supply; OCuLink cable power pins; the port's USB-C VBUS | VBUS. A 5.1 kΩ resistor on CC1 makes the port source 5 V. OCuLink carries no power in standard cables. Cost: the USB-C half of the port is used up. **Assumption:** VBUS is present early enough at boot. A pad for external 5 V is provided |
| USB-C pass-through socket? | Add; omit | Omitted to keep the board small. A first-generation Ally therefore cannot charge with the adapter in |
| Lock switch? | Slide switch; solder jumper; nothing | Solder jumper, default open, which the firmware reads as locked. The handshake still sees "connected" before "locked" because lock is only reported after the host's first SMBus write |
| Lanes 4-7 | Terminate; leave open | Left open. The host finds no receiver and trains at x4 |
| `PERST#` | Direct from `GPU_RST#`; through the MCU | Through the MCU as on the Lite dock, with a 10 kΩ pull-up. A pull-down was rejected: against the MCU's internal pull-up it would hold the line at an invalid level |
| `CWAKE#`, `CPRSNT#`, 2-wire bus, cable power pins | Connect; leave open | Left open. None is needed for a link, each would have had to cross the PCIe pairs, and joining the laptop's EC bus to an unknown dock was judged a risk |
| ESD protection on the lanes | Add; omit | Omitted, as on the Lite dock |

### 5. Layout decisions
| Problem | Resolution |
|---------|------------|
| Board thickness and stack-up | 0.8 mm guessed for the plug. Thin 0.1 mm prepreg so the pairs can be narrow. Inner layers are solid ground |
| Trace geometry | IPC microstrip formulas give about 85 Ω differential for 0.16 mm traces with a 0.15 mm gap, and about 87 Ω for 0.18 mm traces at the 0.5 mm connector pitch. These are approximations and must be checked with the fab's calculator |
| Row A of the receptacle is behind row B | Host-transmit pairs stay on the top layer and end on row B. Host-receive pairs go to the bottom layer, pass under row B and come up between the pad rows |
| Ground vias for row B collide with the receive pairs underneath | The receive pairs run 0.5 mm to one side until they are past those vias, then step back |
| Reference clock starts on the bottom face between lanes 2 and 3 but ends in the middle of the receptacle | It crosses lane 2 on the bottom layer at a point where that lane is still on the top layer |
| `PERST#` has to get from the middle of the receptacle to the MCU on the far side of all pairs | Routed around the front of the receptacle on the bottom layer. Using an inner layer was rejected because it would cut the ground plane under the receive pairs |
| MCU side and rotation | Bottom side reverses the pin order relative to the sideband pads and would force crossings. Top side, rotated 90°, puts pins 10-15 in the same order as pads D31-D26 |
| Ground pads C24, C27, C30 have sideband pads directly beneath them | No room for a via each. They are joined by a short bar and share one via |

### 6. Building the files
| Task | Goal | Result |
|------|------|--------|
| `gen/design.py` | One description of parts and nets for both schematic and board | Done |
| `gen/make_sch.py` | Schematic and symbol library | Every pin gets a stub and a net label. ERC first reported 62 warnings because no project file existed and the library tables were not loaded; 0 once it did |
| `gen/make_fp.py` | Parametric plug footprint, solder jumper | Done |
| `gen/make_pcb.py`, high-speed part | Place parts and compute the pair geometry | First render matched the plan. No clearance errors |
| Project file overwritten | `SaveBoard` replaced the `.kicad_pro` with defaults, so DRC used 0.2 mm rules and reported 698 violations | The settings now live in `gen/project_settings.json` and are copied back after every save |
| Iterating over tracks failed | The `pcbnew` binding raises an error under Python 3.14 when listing tracks | The generator keeps its own list of what it adds |
| Schematic parity warnings | Extracted footprints carried old `LCSC` and `Description` fields | Fields are overwritten from `design.py` |
| Hole clearance | The receptacle's own pads are 0.136 mm from its locating holes | Board minimum lowered to 0.13 mm. All vias placed by the generator keep 0.2 mm or more |

### 7. Routing the low-speed nets
Freerouting was tried first, with the PCIe area fenced off and the pairs locked.

* `--help` opened a GUI and hung. The first attempt to stop it also killed the shell running the command.
* Run headless, it threw internal exceptions, cycled between 16 and 24 unrouted connections for 139 passes, and had written no result when stopped after 200 seconds.

It was replaced by `gen/router.py`, a grid router written for this board: 0.05 mm grid, two layers, shortest path with a turn penalty, no rip-up. Ground pads get a short stub to a via into the planes. Because it cannot rip up, the outcome depends on net order and placement. The runs:

| Change | Open connections |
|--------|------------------|
| First run, power nets last | 13 |
| Power first, thin-trace fallback | 6 |
| Power after signals again, CC1 first | 10 |
| Passives spread out from under the MCU | 7 |
| Ground vias placed before any signal | 7 (ground vias walled in three sideband pads) |
| Ground for C24/C27/C30 deferred | 4 |
| Automatic retry, failed nets moved to the front, 8 attempts | 4 at best. It oscillated |
| Ground bar on the plug, lock jumper moved | 3 |
| Board widened 2 mm on the left | 6, then 2 after restoring ground-first order |
| Debug pads moved from under the LEDs to a row along the top edge | 1 |
| Reset net routed earlier | 0 |

The widening is the one place where routing changed the mechanical design: the board grew from 30.7 mm to 32.7 mm.

### 8. Verification
| Check | Result |
|-------|--------|
| ERC | 0 violations |
| DRC with schematic parity | 0 violations, 0 unconnected items, 0 parity issues |
| Pair lengths, summed from the board file | TX 8.69 mm on all lanes. RX 11.25 mm (lanes 0, 2) and 11.87 mm (lanes 1, 3). Clock 14.02 mm. P and N equal in every pair |
| Visual check of plots | Pair routing as planned. Low-speed routing is correct but untidy |

Not checked: impedance with a field solver, the 3D fit of the plug and receptacle, anything on real hardware.

## Requirements that came out of the investigation
**From the repository**
* A dock must hold `CON_DET_TOWER#` low, see `CON_DET_NB` grounded by the host, report lock on `CON_SW1_DET` only after "connected", raise `DGPU_PWROK` after `DGPU_PWR_EN#`, and answer SMBus commands `A0`-`A3` including a once-per-second heartbeat.
* The handshake must also succeed at boot, so the MCU has to be powered before the BIOS check.
* `GPU_RST#` must reach the card as `PERST#`.
* The reference clock comes from the host and must be passed on.

**From the standards and reference designs**
* OCuLink host pinout: receive on row A, transmit on row B, clock on A12/A13, `PERST#` on B12. The cable swaps rows.
* No power on a standard OCuLink cable.
* PCIe needs lane order kept. Polarity may be swapped at a receiver, but it was kept anyway.
* 85 Ω differential, pairs referenced to unbroken ground, matched length within a pair. Lane-to-lane length does not need matching.

**Implicit, found while designing**
* The plug dictates the board thickness.
* Signal-layer assignment is forced by the connectors: lanes 0-3 are all on one face of the plug, but the two halves of each lane land on different pad rows of the receptacle.
* A USB-C sink resistor is needed for the port to supply any power at all.
* The original cable head latches into the laptop. The adapter has no latch.

## Still unknown
| Unknown | How to resolve it |
|---------|-------------------|
| Plug dimensions, edge cut-outs, board thickness | Measure a harvested plug and its original PCB |
| Whether VBUS is up before the BIOS handshake | Power-on test, with the external 5 V pad as fallback |
| Whether the stock firmware behaves with the unused pins open | Read the UART log on first power-up |
| PCIe 4.0 margin without a redriver | Test with short cables on a Flow and an Ally |
| Whether a given dock switches on without cable power pins | Test per dock |
| Real impedance of the pairs | Fab calculator or a field solver for the chosen stack-up |
| Fit of other OCuLink receptacles | Compare each part's drawing with the footprint |
| Linux control path (`egpu_enable` in `asus-nb-wmi`) | Stated from memory, not verified on a current kernel |

## Sources
* This repository: `Docs/Connector.md`, `Docs/MCU.md`, `Docs/Diary.md`, `Docs/images/cable_pcb_*.jpg`, the Lite dock schematic and the MCU firmware.
* SFF-9402 Rev 1.1, Tables 7-1 and 7-6 (SNIA).
* Antmicro [oculink-pcie-adapter](https://github.com/antmicro/oculink-pcie-adapter) and [job-oculink-expansion](https://github.com/antmicro/job-oculink-expansion), Apache-2.0.
* [Discussion #10](https://github.com/osy/XG_Mobile_Station/discussions/10) and [issue #21](https://github.com/osy/XG_Mobile_Station/issues/21) of the upstream project.
