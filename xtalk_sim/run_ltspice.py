#!/usr/bin/env python3
"""
One-command crosstalk runner: generate a coupled-line deck for a bus, run it
headless in LTspice, parse the .meas results, sweep edge rate.

    python run_ltspice.py --bus ap_done --spacing 6 --tr 0.25 0.5 1 2
    python run_ltspice.py --bus input_data          # default sweep

Requires LTspice (auto-detected). Falls back to a manual path via --ltspice.
"""
import argparse, os, re, subprocess, sys
import gen_ltspice_deck as g

HERE = os.path.dirname(os.path.abspath(__file__))
LT_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\ADI\LTspice\LTspice.exe"),
    r"C:\Program Files\ADI\LTspice\LTspice.exe",
    r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe",
]


def find_ltspice(override):
    for c in ([override] if override else []) + LT_CANDIDATES:
        if c and os.path.isfile(c):
            return c
    sys.exit("LTspice.exe not found; pass --ltspice <path>")


def parse_log(logpath):
    out = {}
    with open(logpath, errors="ignore") as f:
        for line in f:
            mt = re.match(r"(\w+):.*?=\s*(-?[\d.eE+-]+)", line.strip())
            if mt:
                out[mt.group(1)] = float(mt.group(2))
    return out


def run_one(lt, bus, spacing, tr_ns, period, n, vdd, rdrv, cload):
    deck = g.gen(bus, spacing, tr_ns, period, n, vdd, rdrv, cload)
    cir = os.path.join(HERE, f"xtalk_{bus}_tr{tr_ns:g}.cir")
    with open(cir, "w") as f:
        f.write(deck)
    subprocess.run([lt, "-b", "-Run", cir], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return parse_log(cir[:-4] + ".log")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bus", default="input_data")
    p.add_argument("--spacing", type=float, default=6.0)
    p.add_argument("--tr", type=float, nargs="+", default=[0.25, 0.5, 1.0, 2.0])
    p.add_argument("--period", type=float, default=10.0)
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--vdd", type=float, default=1.8)
    p.add_argument("--rdrv", type=float, default=30.0)
    p.add_argument("--cload", type=float, default=3.0)
    p.add_argument("--ltspice", default=None)
    a = p.parse_args()

    lt = find_ltspice(a.ltspice)
    print(f"LTspice: {lt}")
    print(f"bus={a.bus}  gap={a.spacing} mil  N={a.n}  Vdd={a.vdd}  "
          f"Rdrv={a.rdrv}ohm  Cload={a.cload}pF\n")
    print(f"{'Tr_ns':>6}{'NEXT_mV':>10}{'FEXT_mV':>10}{'%swing(worst)':>15}")
    for tr in a.tr:
        r = run_one(lt, a.bus, a.spacing, tr, a.period, a.n, a.vdd, a.rdrv, a.cload)
        nx = r.get("next_pk", 0) * 1000
        fx = r.get("fext_pk", 0) * 1000
        worst = max(nx, fx) / (a.vdd * 1000) * 100
        print(f"{tr:>6g}{nx:>10.1f}{fx:>10.1f}{worst:>14.1f}%")


if __name__ == "__main__":
    main()
