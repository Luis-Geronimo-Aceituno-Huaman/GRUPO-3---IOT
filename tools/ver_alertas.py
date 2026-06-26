#!/usr/bin/env python3
"""ver_alertas.py — visor tiny de consola para datos/alerts.db (solo stdlib).

Uso:
    python3 tools/ver_alertas.py                # ultimas alertas en tabla
    python3 tools/ver_alertas.py -n 20          # las ultimas 20
    python3 tools/ver_alertas.py --sql "SELECT det_class, COUNT(*) FROM alerts GROUP BY det_class"
"""
import sqlite3
import sys
import argparse
from pathlib import Path
from datetime import datetime

DB = Path(__file__).resolve().parent.parent / "datos" / "alerts.db"


def fmt(v, col):
    if v is None:
        return "-"
    if col == "ts":                       # epoch ms -> hora legible
        return datetime.fromtimestamp(v / 1000).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, float):
        return f"{v:.3f}"
    s = str(v)
    return s if len(s) <= 40 else s[:37] + "..."


def tabla(rows, cols):
    if not rows:
        print("(sin filas)")
        return
    data = [[fmt(r[c], c) for c in cols] for r in rows]
    w = [max(len(cols[i]), *(len(d[i]) for d in data)) for i in range(len(cols))]
    line = "  ".join(c.ljust(w[i]) for i, c in enumerate(cols))
    print(line)
    print("  ".join("-" * w[i] for i in range(len(cols))))
    for d in data:
        print("  ".join(d[i].ljust(w[i]) for i in range(len(cols))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10, help="numero de alertas recientes")
    ap.add_argument("--sql", help="consulta SQL libre")
    a = ap.parse_args()
    if not DB.exists():
        sys.exit(f"No existe {DB} (aun no hay alertas guardadas).")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    if a.sql:
        rows = con.execute(a.sql).fetchall()
        tabla(rows, rows[0].keys() if rows else [])
    else:
        cols = ["id", "ts", "node_id", "det_class", "confidence",
                "det_count", "temp_c", "turb_v", "status"]
        rows = con.execute(
            f"SELECT {','.join(cols)} FROM alerts ORDER BY id DESC LIMIT ?", (a.n,)
        ).fetchall()
        n = con.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        print(f"alerts.db -> {n} alertas en total. Mostrando las {min(a.n, n)} ultimas:\n")
        tabla(rows, cols)
    con.close()


if __name__ == "__main__":
    main()
