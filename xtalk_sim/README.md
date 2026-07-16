# HE-PCB parallel-bus crosstalk simulation

First-order crosstalk/coupling study for the parallel single-ended buses on
`HE-PCB / PCB1.PcbDoc`. Geometry was extracted live from the board via the
Altium MCP bridge.

## Board geometry used (extracted, not assumed)
| Parameter | Value | Source |
|---|---|---|
| Trace width | 8 mil | `Width` rule / track query |
| Signal layer | Top | track query |
| Reference plane | VSS (MidLayer1), 2.8 mil below | polygon + stackup |
| Dielectric εr | 4.1 (prepreg) | stackup |
| Single-ended Z0 | 28.4 Ω | `pcb_calc_impedance` |
| Prop delay | 135.33 ps/in | `pcb_calc_impedance` |
| Worst-case gap | 6 mil (= Clearance rule) | design rules |
| Logic | 1.8 V CMOS | user |

Coupling coefficients at 6 mil gap: **kL ≈ 0.065, kC ≈ 0.0625** (seeded from
the odd-mode impedance; refine with a 2D field solver for sign-off).

## Files
- `he_pcb_xtalk.py` — fast closed-form screen + ranks every bus, writes
  `xtalk_ranking.csv`. No SPICE needed.
- `gen_ltspice_deck.py` — emits a coupled-line SPICE deck (`xtalk_<bus>.cir`)
  for one bus: victim between two aggressors, N-segment RLGC ladder,
  nearest-neighbour L (K) + C coupling.
- `run_ltspice.py` — generate + run headless in LTspice + parse `.meas`,
  sweeps edge rate.

## Frequency / edge-rate parameterisation
Crosstalk is driven by **edge rate (rise time)**, not clock frequency — a
"slow" bus with fast CMOS edges still couples. The primary knob is `TR`.
- In a generated `.cir`: edit the `.param TR=...` / `.param PERIOD=...` block
  and re-run — no regeneration needed.
- From the runner: `python run_ltspice.py --bus ap_done --tr 0.25 0.5 1 2 5`

## Results (LTspice 26.0.2, worst bus `ap_done`, 6 mil gap, 3 pF CMOS load)
| Tr (ns) | NEXT (mV) | FEXT (mV) | worst % of 1.8 V |
|--------:|----------:|----------:|-----------------:|
| 0.25 | 63.8 | 112.0 | 6.2 % |
| 0.5  | 60.8 | 108.0 | 6.0 % |
| 1.0  | 47.4 |  83.4 | 4.6 % |
| 2.0  | 42.3 |  46.2 | 2.6 % |
| 5.0  | 17.9 |  19.7 | 1.1 % |

## Caveats / how to raise fidelity
1. **FEXT is far-end-load sensitive.** It's computed with an assumed 3 pF
   unterminated CMOS receiver; the ringing depends on that. Swap in real
   **IBIS** driver/receiver models for a trustworthy number.
2. **kL/kC are seeded, not field-solved.** Run a 2D solver (Polar Si9000,
   Saturn PCB Toolkit, or Altium's SI) to pin the coupling.
3. **Worst-case assumption:** entire routed length treated as adjacent at the
   6 mil minimum gap, both neighbours switching simultaneously. Real coupling
   is lower where traces diverge.
4. **Stackup is under-defined** (missing core between the VSS/VDD planes) —
   fix before any plane-aware / 3D solve. Does not affect the microstrip
   numbers above (those use only the 2.8 mil Top→VSS spacing).
