"""Prueba de endpoints adicionales del CEN (servicios SIP y Operación) antes de integrarlos.

Para cada endpoint registra: código HTTP, cantidad de registros, campos, un registro de ejemplo,
rango de fechas presente en la respuesta (para estimar el atraso) y el tipo de paginación
(incluido si las páginas parten en 0 o en 1, que en los endpoints PCP no es lo documentado).

Las consultas van en secuencia con el cliente del proyecto (throttle adaptativo y backoff ante 429).
El resultado se guarda en scripts/smoke_test_extra.json después de cada endpoint.

Uso:
    .venv\\Scripts\\python scripts\\smoke_test_extra.py            # todo
    .venv\\Scripts\\python scripts\\smoke_test_extra.py --solo pid erv   # filtra por texto en la ruta
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen.client import CENClient, CENError  # noqa: E402

SALIDA = Path(__file__).with_name("smoke_test_extra.json")
LIMIT = 100  # registros por página en la prueba (basta para ver forma, campos y paginación)

HOY = date.today()
FECHAS = {"hoy": HOY, "ayer": HOY - timedelta(days=1), "hace_7d": HOY - timedelta(days=7)}

# tipo: v4 = startDate/endDate/page/limit · v3 = startDate/endDate/page/pageSize ·
#       op_fecha = date/page · op_rango = initDate/endDate/page/pageSize · fijo = sin fechas (una vez)
ENDPOINTS: list[dict[str, Any]] = [
    # ---- SIP, prioridad ALTA (pestaña baterías)
    {"svc": "sip", "path": "cmg-programado-pid/v4/findByDate", "tipo": "v4", "prio": "alta"},
    {"svc": "sip", "path": "pronostico-erv/v4/findByDate", "tipo": "v4", "prio": "alta"},
    {"svc": "sip", "path": "pronosticos-demanda-corto-plazo/v4/findByDate", "tipo": "v4", "prio": "alta"},
    {"svc": "sip", "path": "pronosticos-demanda-mediano-plazo/v4/findByDate", "tipo": "v4", "prio": "alta"},
    # ---- SIP, prioridad MEDIA (explicar el CMg)
    {"svc": "sip", "path": "limitaciones-transmision/v4/findByDate", "tipo": "v4", "prio": "media"},
    {"svc": "sip", "path": "flujo-programado-pcp/v4/findByDate", "tipo": "v4", "prio": "media"},
    {"svc": "sip", "path": "flujo-programado-pid/v4/findByDate", "tipo": "v4", "prio": "media"},
    {"svc": "sip", "path": "potencia-transitada/v4/findByDate", "tipo": "v4", "prio": "media"},
    {"svc": "sip", "path": "instrucciones-operacionales-cmg/v4/findByDate", "tipo": "v4", "prio": "media"},
    {"svc": "sip", "path": "embalse-real/v3/findLast", "tipo": "fijo", "prio": "media"},
    {"svc": "sip", "path": "stock-combustibles/v4/findByDate", "tipo": "v4", "prio": "media"},
    # ---- SIP, prioridad MEDIA (programado vs real)
    {"svc": "sip", "path": "generacion-programada-pcp/v4/findByDate", "tipo": "v4", "prio": "media"},
    {"svc": "sip", "path": "generacion-programada-pid/v4/findByDate", "tipo": "v4", "prio": "media"},
    {"svc": "sip", "path": "demanda-programada-pid/v4/findByDate", "tipo": "v4", "prio": "media"},
    # ---- SIP, prioridad BAJA (contexto)
    {"svc": "sip", "path": "capacidad-instalada/v4/findByDate", "tipo": "fijo", "prio": "baja",
     "params": {"page": 0, "limit": LIMIT}},
    {"svc": "sip", "path": "programas-mantenimiento-mayor/v4/findByDate", "tipo": "v4", "prio": "baja"},
    {"svc": "sip", "path": "solicitudes-trabajo/v4/findByDate", "tipo": "v4", "prio": "baja"},
    {"svc": "sip", "path": "energia-no-suministrada/v4/findByDate", "tipo": "v4", "prio": "baja"},
    {"svc": "sip", "path": "servicios-complementarios-programados-pcp/v4/findByDate", "tipo": "v4", "prio": "baja"},
    {"svc": "sip", "path": "instrucciones-operacionales-sscc/v4/findByDate", "tipo": "v4", "prio": "baja"},
    # ---- SIP, extras encontrados en la especificación (no estaban en la lista original)
    {"svc": "sip", "path": "generacion-programada-sum/v3/getSumGeneration", "tipo": "v3", "prio": "extra",
     "params": {"technology": "Solar"}},
    {"svc": "sip", "path": "pronostico-centrales-pasada/v4/findByDate", "tipo": "v4", "prio": "extra"},
    {"svc": "sip", "path": "unidades-generadoras/v4/findByDate", "tipo": "v4", "prio": "extra"},
    {"svc": "sip", "path": "api/v2/recursos/demanda_sistema_real/", "tipo": "fijo", "prio": "extra",
     "params": {"limit": LIMIT, "offset": 0}},
    # ---- Operación, prioridad ALTA
    {"svc": "operacion", "path": "reduccion/v1/generacion", "tipo": "fijo", "prio": "alta", "params": {"page": 1}},
    {"svc": "operacion", "path": "reduccion/v1/consumo", "tipo": "fijo", "prio": "alta", "params": {"page": 1}},
    # ---- Operación, prioridad MEDIA
    {"svc": "operacion", "path": "servicios-complementarios/v1", "tipo": "op_rango", "prio": "media"},
    {"svc": "operacion", "path": "operativos/v1/estados", "tipo": "fijo", "prio": "media", "params": {"page": 1}},
    {"svc": "operacion", "path": "reportes/v3/generation", "tipo": "op_fecha", "prio": "media"},
    {"svc": "operacion", "path": "reportes/v3/deviation", "tipo": "op_fecha", "prio": "media"},
    {"svc": "operacion", "path": "unidades-generadoras/v1", "tipo": "fijo", "prio": "extra", "params": {"page": 1}},
    {"svc": "operacion", "path": "mantenimiento-mayor/v1", "tipo": "fijo", "prio": "extra",
     "params": {"page": 1, "fechaInicioLocalGte": (HOY - timedelta(days=7)).isoformat()}},
    # net-power exige un id de unidad: se toma de unidades-generadoras/v1 (ver main)
    {"svc": "operacion", "path": "net-power/v1/", "tipo": "fijo", "prio": "media", "params": {}},
]

RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}")
CLAVES_FECHA = ("fecha", "date", "hora", "time", "dia", "periodo", "created", "inicio", "fin")


# ----------------------------------------------------------------- análisis
def registros(payload: Any) -> tuple[list, str, dict]:
    """(lista de registros, forma de la respuesta, metadatos de paginación)."""
    if isinstance(payload, list):
        return payload, "lista", {}
    if isinstance(payload, dict):
        meta = {k: payload[k] for k in ("totalPages", "page", "limit", "pageSize", "count", "next",
                                        "previous", "total", "totalElements") if k in payload}
        for k in ("data", "results", "items", "content"):
            if isinstance(payload.get(k), list):
                return payload[k], f"objeto con '{k}'", meta
        return [payload], "objeto único", meta
    return [], type(payload).__name__, {}


def campos(regs: list) -> list[str]:
    out: dict[str, None] = {}
    for r in regs[:20]:
        if isinstance(r, dict):
            out.update(dict.fromkeys(r))
    return list(out)


def rango_fechas(regs: list) -> tuple[str | None, str | None]:
    vals: list[str] = []
    for r in regs:
        if not isinstance(r, dict):
            continue
        for k, v in r.items():
            if not any(c in k.lower() for c in CLAVES_FECHA):
                continue
            if isinstance(v, str) and RE_FECHA.match(v):
                vals.append(v[:19].replace("T", " "))
            elif isinstance(v, (int, float)) and v > 1e12:  # epoch en ms
                vals.append(datetime.fromtimestamp(v / 1000).strftime("%Y-%m-%d %H:%M:%S"))
    return (min(vals), max(vals)) if vals else (None, None)


def recortar(x: Any, n: int = 160) -> Any:
    if isinstance(x, dict):
        return {k: recortar(v, n) for k, v in list(x.items())[:40]}
    if isinstance(x, list):
        return [recortar(v, n) for v in x[:3]]
    if isinstance(x, str) and len(x) > n:
        return x[:n] + "…"
    return x


# ------------------------------------------------------------------ pruebas
def consulta(cli: CENClient, path: str, params: dict) -> dict:
    t0 = time.time()
    try:
        resp = cli.request(path, **params)
    except CENError as exc:
        return {"params": params, "http": None, "error": str(exc), "seg": round(time.time() - t0, 1)}
    out: dict[str, Any] = {"params": params, "http": resp.status_code, "seg": round(time.time() - t0, 1)}
    if resp.status_code != 200:
        out["error"] = resp.text[:300]
        return out
    try:
        payload = resp.json()
    except ValueError:
        out["error"] = "respuesta no es JSON: " + resp.text[:200]
        return out
    regs, forma, meta = registros(payload)
    fmin, fmax = rango_fechas(regs)
    out.update({"n": len(regs), "forma": forma, "meta": meta, "campos": campos(regs),
                "ejemplo": recortar(regs[0]) if regs else None, "fecha_min": fmin, "fecha_max": fmax,
                "_primer_id": json.dumps(regs[0], sort_keys=True, default=str)[:300] if regs else None})
    return out


def params_fecha(tipo: str, d: date, pagina: int, extra: dict) -> dict:
    ds = d.isoformat()
    if tipo == "v4":
        return {"startDate": ds, "endDate": ds, "page": pagina, "limit": LIMIT, **extra}
    if tipo == "v3":
        return {"startDate": ds, "endDate": ds, "page": pagina, "pageSize": LIMIT, **extra}
    if tipo == "op_fecha":
        return {"date": ds, "page": pagina, **extra}
    if tipo == "op_rango":
        return {"initDate": ds, "endDate": ds, "page": pagina, "pageSize": LIMIT, **extra}
    raise ValueError(tipo)


def probar_paginacion(cli: CENClient, ep: dict, d: date, primera: dict) -> dict:
    """Determina si las páginas parten en 0 o 1 y consulta la última página (fecha más reciente)."""
    tipo, extra = ep["tipo"], ep.get("params", {})
    tp = (primera.get("meta") or {}).get("totalPages")
    res: dict[str, Any] = {"totalPages": tp}
    if not tp or tp < 2:
        res["base"] = "una sola página"
        return res
    p0 = primera["params"]["page"]
    sig = consulta(cli, ep["path"], params_fecha(tipo, d, p0 + 1, extra))
    if sig.get("http") == 200 and sig.get("_primer_id") == primera.get("_primer_id"):
        res["base"] = f"page={p0} repite page={p0 + 1}: numeración desde {p0 + 1}"
        base = p0 + 1
    else:
        res["base"] = f"desde {p0}"
        base = p0
    ultima = consulta(cli, ep["path"], params_fecha(tipo, d, base + tp - 1, extra))
    res["ultima_pagina"] = {"page": base + tp - 1, "http": ultima.get("http"), "n": ultima.get("n"),
                            "fecha_min": ultima.get("fecha_min"), "fecha_max": ultima.get("fecha_max")}
    return res


def probar(cli: CENClient, ep: dict) -> dict:
    out: dict[str, Any] = {"servicio": ep["svc"], "path": ep["path"], "prioridad": ep["prio"], "tipo": ep["tipo"],
                           "pruebas": {}}
    extra = ep.get("params", {})
    if ep["tipo"] == "fijo":
        out["pruebas"]["sin_fecha"] = consulta(cli, ep["path"], dict(extra))
        return out
    pagina0 = 0 if ep["tipo"] == "v4" else 1
    for nombre, d in FECHAS.items():
        r = consulta(cli, ep["path"], params_fecha(ep["tipo"], d, pagina0, extra))
        if r.get("http") and r["http"] >= 500 and pagina0 == 0:
            # en cmg-programado-pcp page=0 da 502: se reintenta desde 1
            r2 = consulta(cli, ep["path"], params_fecha(ep["tipo"], d, 1, extra))
            r2["nota"] = f"page=0 respondió HTTP {r['http']}; se usó page=1"
            r = r2
        out["pruebas"][nombre] = r
        if nombre == "hoy" and r.get("http") == 200:
            out["paginacion"] = probar_paginacion(cli, ep, d, r)
        if r.get("http") == 403:
            break  # clave rechazada: no insistir con otras fechas
    return out


def resumen(resultados: list[dict]) -> str:
    filas = ["| Endpoint | Serv. | Prio | HTTP hoy/ayer/-7d | Reg. hoy | Págs. | Dato más reciente | Paginación |",
             "|---|---|---|---|---|---|---|---|"]
    for r in resultados:
        pr = r["pruebas"]
        if "sin_fecha" in pr:
            http = str(pr["sin_fecha"].get("http"))
            principal = pr["sin_fecha"]
        else:
            http = "/".join(str(pr.get(k, {}).get("http", "–")) for k in FECHAS)
            principal = pr.get("hoy", {})
        pag = r.get("paginacion", {})
        ult = (pag.get("ultima_pagina") or {}).get("fecha_max")
        fmax = max([f for f in (principal.get("fecha_max"), ult) if f], default="–")
        tp = (principal.get("meta") or {}).get("totalPages") or (principal.get("meta") or {}).get("count") or "–"
        filas.append(f"| `{r['path']}` | {r['servicio']} | {r['prioridad']} | {http} | {principal.get('n', '–')} | "
                     f"{tp} | {fmax} | {pag.get('base', principal.get('forma', '–'))} |")
    return "\n".join(filas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", nargs="*", help="probar solo rutas que contengan alguno de estos textos")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

    eps = [e for e in ENDPOINTS if not args.solo or any(s in e["path"] for s in args.solo)]
    clientes = {s: CENClient(service=s, min_interval=2.0) for s in {e["svc"] for e in eps}}
    resultados: list[dict] = []
    op_rechazada = False
    inicio = datetime.now()

    for i, ep in enumerate(eps, 1):
        if ep["svc"] == "operacion" and op_rechazada:
            resultados.append({"servicio": "operacion", "path": ep["path"], "prioridad": ep["prio"], "tipo": ep["tipo"],
                               "pruebas": {"sin_fecha": {"http": 403, "error": "omitido: la clave de Operación fue rechazada"}}})
            continue
        if ep["path"] == "net-power/v1/":
            uni = next((r for r in resultados if r["path"] == "unidades-generadoras/v1"), None)
            ej = ((uni or {}).get("pruebas", {}).get("sin_fecha", {}) or {}).get("ejemplo") or {}
            if ej.get("id") is None:
                resultados.append({"servicio": "operacion", "path": ep["path"], "prioridad": ep["prio"], "tipo": "fijo",
                                   "pruebas": {"sin_fecha": {"http": None, "error": "sin id de unidad para probar"}}})
                continue
            ep = {**ep, "params": {"id": ej["id"]}}
        print(f"[{i}/{len(eps)}] {ep['svc']:9} {ep['path']} …", flush=True)
        r = probar(clientes[ep["svc"]], ep)
        resultados.append(r)
        if ep["svc"] == "operacion" and any(p.get("http") == 403 for p in r["pruebas"].values()):
            op_rechazada = True
            print("  !! La clave de Operación fue rechazada (HTTP 403). Se omiten los demás endpoints de Operación.",
                  flush=True)
        for p in r["pruebas"].values():
            p.pop("_primer_id", None)
        SALIDA.write_text(json.dumps({"generado": datetime.now().isoformat(timespec="seconds"),
                                      "fechas": {k: v.isoformat() for k, v in FECHAS.items()},
                                      "resultados": resultados}, ensure_ascii=False, indent=1, default=str),
                          encoding="utf-8")

    print("\n" + resumen(resultados))
    print(f"\nConsultas: " + ", ".join(f"{s}={c.request_count} (reintentos {c.retry_count})" for s, c in clientes.items())
          + f" · duración {datetime.now() - inicio}")
    print(f"Detalle en {SALIDA}")


if __name__ == "__main__":
    main()
