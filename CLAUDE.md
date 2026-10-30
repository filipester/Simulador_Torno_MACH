# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A backplot simulator for CNC lathe programs in the **MACH8/MACH9 dialect** (Romi/MCS controls),
built because generic ISO simulators (CIMCO, NC-Corrector) misread the dialect. Pure Python +
matplotlib + tkinter; no other dependencies. Portfolio project — see README.md for the user-facing
description.

## Commands

- Run: `python simulador.py [file.nc|.txt|.docx]`
- Tests: `python -m unittest -v`
- Build: `pyinstaller --noconsole --onedir --name "Simulador Torno MACH" simulador.py`

## Architecture

- `mach_parser.py` — text → `Bloco` (sequence number, `(letter, value|None)` words, comment,
  per-line warnings). `None` = bare word (`GXZ`), which is **zero** in MACH. Also reads `.docx`
  with stdlib `zipfile` (no python-docx).
- `mach_sim.py` — state machine `simular(blocos, torre_traseira)` → `Resultado` (segments in
  `(z, radius)` plane, warnings by line, state after each line). X is stored internally as
  diameter.
- `desenho.py` — matplotlib drawing, shared by GUI and static images.
- `simulador.py` — tkinter GUI only; no G-code logic here.

## Dialect rules (source: Romi manual R69001C, MACH9) — do not "fix" these to ISO

- `G20`/`G21` = X in diameter/radius (not inch/mm). `G70`/`G71` = inch/mm.
- `G` alone = `G0`; axis without value = 0. `GXZ` outside `G92` = go to machine zero → position
  unknown until next `G92 X Z` (not drawn).
- `I`/`K` = **absolute** arc center (I in diameter). `R` arcs ≤ 180°, short arc chosen.
- `G2`/`G3` direction depends on turret: rear turret (default) G2 = clockwise with Z right, X up.
  Verified against a real full-radius groove (G2 R1 at the groove bottom is concave).
- `G2`/`G3` are not modal; they authorize G1 for following blocks.
- `T0?0?` is the user's placeholder for "tool position still to be checked on the machine".

## Conventions

- Never guess geometry: unsupported cycles (G33/G37/G66/G67/G68/G73/G74/G75/G76/G83), G41/G42,
  subprograms → per-line warning, nothing drawn.
- Real factory programs must NOT be committed (public portfolio repo). Use `exemplos/` with
  fictional programs; `programas/` is git-ignored for local real files.
