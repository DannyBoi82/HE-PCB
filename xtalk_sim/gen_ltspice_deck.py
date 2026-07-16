#!/usr/bin/env python3
"""
Generate a coupled-line crosstalk SPICE deck (LTspice/ngspice compatible) for
one HE-PCB parallel bus.

Model: a VICTIM trace flanked by TWO aggressors (worst case), each an N-segment
RLGC ladder.  Nearest-neighbour coupling only (dominant term):
  - mutual inductance via K statements (coeff kL)
  - mutual capacitance Cm between adjacent line nodes (coeff kC)
Aggressors switch together (worst-case simultaneous), victim driver holds low.

FREQUENCY / EDGE-RATE PARAMETERS live as .param at the top of the generated
deck -- edit TR / PERIOD / VDD / RDRV / CLOAD and re-run without regenerating.
Geometry (per-bus length, L/C per inch, kL/kC) is baked in by this generator;
re-run it to change bus or spacing.

    python gen_ltspice_deck.py --bus input_data --spacing 6 --tr 0.5 --n 40
"""
import argparse, os
import he_pcb_xtalk as m   # reuse extracted geometry + net lengths

R0_OHM_PER_IN = 0.062      # 8 mil / 1 oz copper, DC-ish series loss


def bus_max_len_in(bus):
    lens = [L for net, L in m.NET_LEN_MILS.items() if m.bus_of(net) == bus]
    if not lens:
        raise SystemExit(f"bus '{bus}' not found. Options: "
                         + ", ".join(sorted({m.bus_of(n) for n in m.NET_LEN_MILS})))
    return max(lens) / 1000.0


def gen(bus, spacing, tr_ns, period_ns, n, vdd, rdrv, cload_pf):
    Lin = bus_max_len_in(bus)
    kL, kC = m.coeffs_for_spacing(spacing)
    dl = Lin / n
    Lseg = m.L0 * dl                 # H
    Cseg = m.C0 * dl                 # F
    Cmut = kC * m.C0 * dl            # F
    Rseg = R0_OHM_PER_IN * dl        # ohm

    L = []
    a = L.append
    a(f"* HE-PCB crosstalk: bus={bus}  len={Lin:.3f} in  gap={spacing:.1f} mil  "
      f"N={n} segments")
    a(f"* Z0={m.Z0} ohm  tpd={m.TPD*1e12:.1f} ps/in  kL={kL:.4f} kC={kC:.4f}  "
      f"(victim between 2 aggressors)")
    a("*--- edit these to sweep edge-rate / data-rate ---")
    a(f".param VDD={vdd}")
    a(f".param TR={tr_ns}n        ; rise time (PRIMARY knob - crosstalk scales with this)")
    a(f".param TF={{TR}}          ; fall time")
    a(f".param PERIOD={period_ns}n  ; bit/clock period")
    a(f".param PW={{PERIOD/2-TR}}   ; high time")
    a(f".param RDRV={rdrv}        ; driver output impedance (ohm)")
    a(f".param CLOAD={cload_pf}p   ; receiver input capacitance")
    a("*--------------------------------------------------")

    # --- aggressor drivers (switch together), victim held low by its driver ---
    a("VA1 na1_src 0 PULSE(0 {VDD} 1n {TR} {TF} {PW} {PERIOD})")
    a("VA2 na2_src 0 PULSE(0 {VDD} 1n {TR} {TF} {PW} {PERIOD})")
    a("RA1 na1_src a1_0 {RDRV}")
    a("RA2 na2_src a2_0 {RDRV}")
    a("RV  0 v_0 {RDRV}            ; victim driver holding LOW (source Z to gnd)")

    # --- ladders ---
    for i in range(n):
        for ln in ("a1", "v", "a2"):
            a(f"R{ln}_{i} {ln}_{i} {ln}r_{i} {Rseg:.6e}")
            a(f"L{ln}_{i} {ln}r_{i} {ln}_{i+1} {Lseg:.6e}")
        # mutual inductance nearest-neighbour
        a(f"Kav1_{i} La1_{i} Lv_{i} {kL:.5f}")
        a(f"Kav2_{i} Lv_{i} La2_{i} {kL:.5f}")

    # --- shunt self + mutual caps at nodes 1..N ---
    for i in range(1, n + 1):
        for ln in ("a1", "v", "a2"):
            a(f"C{ln}_{i} {ln}_{i} 0 {Cseg:.6e}")
        a(f"Cm1_{i} a1_{i} v_{i} {Cmut:.6e}")
        a(f"Cm2_{i} v_{i} a2_{i} {Cmut:.6e}")

    # --- far-end receiver loads ---
    a(f"CLa1 a1_{n} 0 {{CLOAD}}")
    a(f"CLv  v_{n} 0 {{CLOAD}}")
    a(f"CLa2 a2_{n} 0 {{CLOAD}}")

    # --- analysis + measurements ---
    a(".tran 0 {4*PERIOD} 0 {TR/20}")
    a(".meas TRAN aggr_swing PP V(a1_0)")
    a(".meas TRAN next_pos MAX V(v_0)")
    a(".meas TRAN next_neg MIN V(v_0)")
    a(f".meas TRAN next_pk  MAX abs(V(v_0))")
    a(f".meas TRAN fext_pk  MAX abs(V(v_{n}))")
    a(".end")
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bus", default="input_data")
    p.add_argument("--spacing", type=float, default=6.0)
    p.add_argument("--tr", type=float, default=0.5, help="rise time (ns)")
    p.add_argument("--period", type=float, default=10.0, help="bit period (ns)")
    p.add_argument("--n", type=int, default=40, help="ladder segments")
    p.add_argument("--vdd", type=float, default=1.8)
    p.add_argument("--rdrv", type=float, default=30.0)
    p.add_argument("--cload", type=float, default=3.0, help="receiver cap (pF)")
    p.add_argument("--out", default=None)
    a = p.parse_args()

    deck = gen(a.bus, a.spacing, a.tr, a.period, a.n, a.vdd, a.rdrv, a.cload)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                f"xtalk_{a.bus}.cir")
    with open(out, "w") as f:
        f.write(deck)
    print(f"wrote {out}  ({a.n} segments, bus={a.bus}, gap={a.spacing} mil, Tr={a.tr} ns)")


if __name__ == "__main__":
    main()
