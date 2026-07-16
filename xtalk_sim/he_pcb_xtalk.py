#!/usr/bin/env python3
"""
HE-PCB parallel-bus crosstalk screen (coupled-microstrip, closed form).

Geometry extracted from HE-PCB / PCB1.PcbDoc via the Altium MCP bridge:
  - Bus traces:  W = 8 mil, Top Layer, referenced to VSS plane 2.8 mil below
  - Dielectric:  prepreg, er = 4.1  ->  Z0 = 28.4 ohm, tpd = 135.33 ps/in
  - Worst-case adjacent spacing = design Clearance rule = 6 mil (pitch 14 mil)
  - Victim modelled between TWO aggressors switching together (worst case)
  - Signalling: 1.8 V CMOS.  Edge rate (rise time) is the primary knob.

This is a FIRST-ORDER SCREEN, not a field-solved answer.  The coupling
coefficients kL/kC are seeded from the odd-mode impedance the Altium
calculator returned; refine them with a 2D field solver (Polar Si9000 /
HyperLynx) before signing anything off.  NEXT (near-end) is the robust
number; FEXT is dominated by (kL-kC) and is low-confidence here.

Usage:
    python he_pcb_xtalk.py                 # default rise-time sweep
    python he_pcb_xtalk.py --tr 0.5        # single rise time (ns)
    python he_pcb_xtalk.py --spacing 6     # worst-case gap (mil), rescales k
"""
import argparse, csv, math, os, re

# ---------------------------------------------------------------------------
# Transmission-line parameters (per inch), from the extracted geometry
# ---------------------------------------------------------------------------
Z0        = 28.4              # ohm, single-ended microstrip (Altium calc)
TPD       = 135.33e-12        # s/in, propagation delay
VDD       = 1.8              # V, logic swing
C0        = TPD / Z0          # F/in  self capacitance to plane
L0        = TPD * Z0          # H/in  self inductance

# Coupling coefficients at the worst-case 6 mil gap (s/h = 6/2.8 = 2.14).
# Derived from Z_odd = 26.7 ohm (Zdiff/2) and Z_even ~ Z0^2/Z_odd:
#   kL = Lm/L0 ~ 0.065 , kC = Cm/C0 ~ 0.0625
# Coupling falls off ~exp(-0.96*s/h); --spacing rescales from this 6 mil base.
KL_BASE   = 0.065
KC_BASE   = 0.0625
S_BASE    = 6.0              # mil, gap the base coefficients correspond to
H_DIEL    = 2.8              # mil, trace height over VSS plane
N_AGGR    = 2                # aggressors flanking the victim (both sides)

# ---------------------------------------------------------------------------
# Routed length per net (mils), pulled from pcb_get_trace_lengths on PCB1.
# ---------------------------------------------------------------------------
NET_LEN_MILS = {
    "input_data0":1850.16,"input_data1":2065.06,"input_data2":2014.70,"input_data3":2197.39,
    "input_data4":2146.73,"input_data5":2329.42,"input_data6":2034.07,"input_data7":2095.33,
    "input_data8":2290.03,"input_data9":2259.59,"input_data10":2453.99,"input_data11":2423.83,
    "input_data12":2379.52,"input_data13":2349.07,"input_data14":2543.77,"input_data15":2513.32,
    "output_data0":995.08,"output_data1":1121.18,"output_data2":1005.85,"output_data3":1131.95,
    "output_data4":1016.62,"output_data5":1142.72,"output_data6":1027.39,"output_data7":1153.78,
    "output_data8":1096.74,"output_data9":1106.27,"output_data10":999.23,"output_data11":1117.04,
    "output_data12":1009.996,"output_data13":1127.81,"output_data14":1020.77,"output_data15":1105.44,
    "ap_done0":2725.45,"ap_done1":2764.18,"ap_done2":2578.36,"ap_done3":2497.90,"ap_done4":2537.22,
    "ap_done5":2493.29,"ap_done6":2431.73,"ap_done7":2470.46,"ap_done8":2268.48,"ap_done9":2264.35,
    "ap_done10":2482.93,"ap_done11":2282.59,"ap_done12":2352.18,"ap_done13":2175.85,"ap_done14":2259.39,
    "ap_done15":2244.11,
    "bank0_addr0":2030.67,"bank0_addr1":2225.08,"bank0_addr2":2193.92,"bank0_addr3":2347.49,
    "bank0_addr4":2078.03,"bank0_addr5":2272.43,"bank0_addr6":2242.28,"bank0_addr7":2303.55,
    "bank0_addr8":2497.95,"bank0_addr9":2315.98,"bank0_addr10":2331.77,"bank0_addr11":2676.08,
    "bank1_addr0":1176.15,"bank1_addr1":1260.82,"bank1_addr2":1145.50,"bank1_addr3":1271.59,
    "bank1_addr4":1156.27,"bank1_addr5":1282.36,"bank1_addr6":1167.04,"bank1_addr7":1293.13,
    "bank1_addr8":1177.81,"bank1_addr9":1303.90,"bank1_addr10":1188.58,"bank1_addr11":1314.67,
    "o_start_w0":1215.20,"o_start_w1":1318.43,"o_start_w2":1189.20,"o_start_w3":1226.20,
    "o_start_w4":1463.20,"o_start_w5":1266.43,"o_start_w6":1137.20,"o_start_w7":1242.48,
    "o_start_w8":1124.67,"o_start_w9":1388.96,
    "ap_done_x":0,  # placeholder removed below
    "REP_SEL0":1451.43,"REP_SEL1":1322.20,"REP_SEL2":1425.43,"REP_SEL3":1296.20,
    "REP_SEL4":1399.43,"REP_SEL5":1270.20,
    "bank0_init_pad_in0":1197.86,"bank0_init_pad_in1":1090.82,"bank0_init_pad_in2":1967.05,
    "bank0_init_pad_in3":1969.11,
    "bank1_init_pad_in0":2225.10,"bank1_init_pad_in1":2114.02,"bank1_init_pad_in2":1959.52,
    "bank1_init_pad_in3":2061.58,
    "dp_tpp_model0":2489.995,"dp_tpp_model1":2754.28,
}
NET_LEN_MILS.pop("ap_done_x", None)


def bus_of(net):
    """Group a bus member -> bus prefix (strip trailing index digits)."""
    return re.sub(r"\d+$", "", net)


def coeffs_for_spacing(spacing_mil):
    """Rescale kL/kC from the 6 mil base using the exp(-0.96*s/h) trend."""
    f = math.exp(-0.96 * (spacing_mil - S_BASE) / H_DIEL)
    return KL_BASE * f, KC_BASE * f


def crosstalk(len_in, tr_s, kL, kC):
    """Return (NEXT_V, FEXT_V) for a victim flanked by N_AGGR aggressors.

    NEXT saturates to Kb*Vdd once 2*Td >= Tr, else derates by 2*Td/Tr.
    FEXT peak ~ 0.5*(kL-kC)*(Td/Tr)*Vdd  (low confidence for microstrip).
    """
    Td = len_in * TPD
    Kb = 0.25 * (kL + kC)
    next_1 = Kb * VDD * min(1.0, 2.0 * Td / tr_s)
    fext_1 = 0.5 * abs(kL - kC) * (Td / tr_s) * VDD
    fext_1 = min(fext_1, 0.5 * abs(kL - kC) * VDD * 3)  # clamp doublet growth
    return N_AGGR * next_1, N_AGGR * fext_1, Td


def build_bus_table():
    buses = {}
    for net, L in NET_LEN_MILS.items():
        b = bus_of(net)
        buses.setdefault(b, []).append(L)
    rows = []
    for b, lens in buses.items():
        if len(lens) < 2:      # only ranking true parallel buses
            continue
        Lmax_in = max(lens) / 1000.0
        rows.append((b, len(lens), Lmax_in))
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tr", type=float, default=None,
                    help="single rise time in ns (default: sweep)")
    ap.add_argument("--spacing", type=float, default=S_BASE,
                    help="adjacent gap in mil (default 6 = worst case)")
    ap.add_argument("--csv", default="xtalk_ranking.csv")
    args = ap.parse_args()

    kL, kC = coeffs_for_spacing(args.spacing)
    tr_list = [args.tr] if args.tr else [0.25, 0.5, 1.0, 2.0, 5.0]
    Kb = 0.25 * (kL + kC)

    print("=" * 78)
    print("HE-PCB parallel-bus crosstalk screen  (1.8 V CMOS, victim between 2 aggressors)")
    print(f"Geometry: W=8mil Top/VSS h=2.8mil er=4.1  Z0={Z0} ohm  tpd={TPD*1e12:.1f} ps/in")
    print(f"Gap={args.spacing:.1f} mil  ->  kL={kL:.4f} kC={kC:.4f}  "
          f"saturated 2-sided NEXT = {2*Kb*VDD*1000:.0f} mV ({2*Kb*100:.1f}% of swing)")
    print("=" * 78)

    rows = build_bus_table()
    csv_rows = []
    for tr_ns in tr_list:
        tr = tr_ns * 1e-9
        print(f"\n--- rise time Tr = {tr_ns:g} ns "
              f"(edges saturate NEXT when routed Td*2 >= {tr_ns:g} ns) ---")
        print(f"{'bus':<22}{'bits':>5}{'Lmax_in':>9}{'Td_ps':>8}"
              f"{'NEXT_mV':>9}{'%swing':>8}{'sat?':>6}{'FEXT_mV':>9}")
        for b, n, Lin in rows:
            nx, fx, Td = crosstalk(Lin, tr, kL, kC)
            sat = "yes" if 2 * Td >= tr else "no"
            print(f"{b:<22}{n:>5}{Lin:>9.3f}{Td*1e12:>8.0f}"
                  f"{nx*1000:>9.1f}{nx/VDD*100:>8.1f}{sat:>6}{fx*1000:>9.1f}")
            csv_rows.append({"bus": b, "bits": n, "Lmax_in": round(Lin, 3),
                             "Td_ps": round(Td*1e12, 1), "Tr_ns": tr_ns,
                             "NEXT_mV": round(nx*1000, 1),
                             "pct_swing": round(nx/VDD*100, 2),
                             "saturated": sat, "FEXT_mV": round(fx*1000, 1)})

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.csv)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        w.writeheader(); w.writerows(csv_rows)
    print(f"\nwrote {out}")
    print("\nNOTE: NEXT is the trustworthy figure. FEXT here is small only because the")
    print("seeded kL~kC; real microstrip FEXT needs a 2D field solver to pin down.")


if __name__ == "__main__":
    main()
