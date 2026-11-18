"""Smoke test contra la API real del CEN (paso 1 del plan, sección 4.7).

Verifica:
  1. Que ``bar_transf`` filtra el CMg en línea (una sola barra).
  2. El último ``fecha_minuto`` disponible hoy en el CMg en línea.
  3. El comportamiento ante 429 (cuántas consultas seguidas aguanta sin pausa).

Uso:  .venv\\Scripts\\python scripts\\smoke_test.py [--burst N]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen.client import BASE_URL, CENClient  # noqa: E402

BARRA = "AJAHUEL_______500"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--burst", type=int, default=0, help="consultas seguidas sin pausa para medir el 429")
    ap.add_argument("--barra", default=BARRA)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    c = CENClient(min_interval=2.0)
    hoy = date.today()
    ayer = hoy - timedelta(days=1)

    print(f"\n== 1. Filtro bar_transf={args.barra} (ayer {ayer}) ==")
    p = c.get("costo-marginal-online/v4/findByDate", startDate=ayer.isoformat(), endDate=ayer.isoformat(),
              bar_transf=args.barra, limit=500, page=0)
    rows = p.get("data", [])
    barras = {r.get("barra_transf") for r in rows}
    print(f"filas={len(rows)} totalPages={p.get('totalPages')} barras distintas={barras}")
    print("FILTRO OK" if barras == {args.barra} else "FILTRO NO FUNCIONA (o barra inexistente)")

    print(f"\n== 2. CMg en línea de hoy ({hoy}) ==")
    p = c.get("costo-marginal-online/v4/findByDate", startDate=hoy.isoformat(), endDate=hoy.isoformat(),
              bar_transf=args.barra, limit=500, page=0)
    rows = p.get("data", [])
    if rows:
        ultimo = max(r["fecha_minuto"] for r in rows)
        print(f"filas={len(rows)} último fecha_minuto={ultimo}  (ahora {time.strftime('%H:%M')})")
    else:
        print("sin datos para hoy")

    print("\n== 2b. CMg 8 barras ==")
    p = c.get("costos-marginales-online-8b/v4/findAll")
    for b in p.get("barras", []):
        vals = b.get("valores", [])
        print(f"  {b['nombre']}: {len(vals)} valores")

    if args.burst:
        print(f"\n== 3. Ráfaga de {args.burst} consultas sin pausa ==")
        s = requests.Session()
        for i in range(1, args.burst + 1):
            r = s.get(f"{BASE_URL}/costos-marginales-online-8b/v4/findAll", params={"user_key": c.user_key}, timeout=60)
            print(f"  #{i}: HTTP {r.status_code}")
            if r.status_code == 429:
                print(f"  -> 429 tras {i} consultas seguidas")
                break

    print(f"\nrequests={c.request_count} reintentos={c.retry_count}")


if __name__ == "__main__":
    main()
