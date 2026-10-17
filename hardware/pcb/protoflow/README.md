# Protoflow hand-off: CHOTU carrier PCB layout

[Protoflow](https://www.protoflow.ai) is a desktop app for AI-assisted PCB design, built on KiCad. This folder has everything it needs to lay out the CHOTU carrier board.

> **What is and is not done.** The circuit, netlist, parts list and layout rules are complete and checked (`../erc_report.txt`, `tests/test_pcb_netlist.py`). The **layout, Gerbers and STEP have not been produced yet.** Protoflow is a GUI app and could not be driven from this automated session, so the steps below have to be done by hand. No board has been ordered.

| File | What |
|---|---|
| `PROTOFLOW_BRIEF.md` | The prompt to paste into Protoflow: board spec, electrical rules, every part with its footprint, every net, the GPIO map |
| `bom_jlcpcb.csv` | BOM with JLCPCB/LCSC part suggestions for the SMD passives (for example C17414 10 k, C49678 100 nF) |
| `chotu_carrier.net` | KiCad netlist (a copy of `../chotu_carrier.net`) |
| `make_protoflow_package.py` | Regenerates the three files above from `../chotu_carrier.py` |

## Steps in Protoflow

1. Install Protoflow (Windows: `%LOCALAPPDATA%\Programs\Protoflow`) and sign in.
2. **New project** → name it `chotu_carrier`.
3. Import `chotu_carrier.net` (*Import netlist*). If your version has no importer, skip this step; the brief alone describes the whole circuit.
4. Open the AI chat. Paste everything below the `---` line of `PROTOFLOW_BRIEF.md` and send it.
5. Check what it proposes against the brief:
   - the board is 90 × 65 mm with four M3 holes
   - there is no copper under the ESP32 antenna
   - power traces are 2 mm
   - motor and logic grounds meet at one star point
   - the MOSFETs and diodes sit on the edge away from the antenna
6. Run **ERC** and **DRC** until both are clean.
7. Export **Gerbers + drill, BOM, CPL (pick-and-place) and STEP** into `hardware/pcb/protoflow/output/`.
8. Commit `output/` and check the STEP against the electronics deck in `bot_3d_printing/step/electronics_deck.step`.

If the circuit changes, edit `../chotu_carrier.py`, then run `python hardware/pcb/protoflow/make_protoflow_package.py` and repeat from step 4.
