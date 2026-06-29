"""
run_consolidacion.py

Orquestador de la corrida. Flujo:
  1. AUTO: levanta y carga la DB (aplica migraciones pendientes).
  2. Ejecuta los scrapers (best-effort; --no-scrape para omitir).
  3. Ingiere las salidas .json de los scrapers.
  4. Contrasta contra el maestro -> nuevos / actualizados / sin_cambio / rechazados.
  5. Salida en out/<run_id>/: delta en .xlsx (<=max-mb), reporte.json, rechazados.csv.
  6. Emite el delta como nueva(s) migración(es) y las aplica (el maestro queda al día).

Correr con el venv (openpyxl):  .venv/bin/python consolidator/run_consolidacion.py
La generación del seed es aparte y manual (scripts/gen_seed_migrations.py).
"""

import argparse
import csv
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consolidator.lib import migrate as mig
from consolidator.lib import diff as diffmod
from consolidator.lib import cotejo as cotejomod
from consolidator.lib.export_xlsx import export_delta
from consolidator.lib.registros import CANONICAL_COLUMNS
from consolidator.scripts.gen_seed_migrations import emit_migrations, next_version

BASE = Path(__file__).resolve().parent
REPO = BASE.parent
DEFAULT_DB = BASE / "master.db"
MIGRATIONS = BASE / "migrations"
OUT = BASE / "out"

# Scrapers a ejecutar (mismos pasos que run_daily). python3 = sistema (urllib/playwright).
SCRAPERS = [
    ("venezuelatebusca",        ["node", "scraper.js", "--update"], REPO / "Amilkir"),
    ("redayuda (activos)",      ["python3", "scraper.py", "--status", "active",
                                 "--output", "desaparecidos_redayudavenezuela"], REPO / "chiki"),
    ("redayuda (localizados)",  ["python3", "scraper.py", "--status", "found",
                                 "--output", "localizados_redayudavenezuela"], REPO / "chiki"),
    ("terremoto",               ["python3", "scraper_terremoto.py"], REPO / "chiki"),
    ("terremoto (parse)",       ["python3", "parse_desaparecidos.py"], REPO / "chiki"),
    ("sosvenezuela2026",        ["python3", "scraper.py"], REPO / "scrapers" / "sosvenezuela2026"),
    ("venezuelareporta",        ["python3", "scraper.py"], REPO / "scrapers" / "venezuelareporta"),
]

# Salidas .json a ingerir tras el scrape.
INGEST = [
    REPO / "Amilkir" / "personas_venezuela.json",
    REPO / "chiki" / "desaparecidos_redayudavenezuela.json",
    REPO / "chiki" / "localizados_redayudavenezuela.json",
    REPO / "chiki" / "personas_desaparecidas_venezuela_parsed.json",
    REPO / "chiki" / "pacientes_hospitalizados.json",
    REPO / "scrapers" / "sosvenezuela2026" / "sosvenezuela2026.json",
    REPO / "scrapers" / "venezuelareporta" / "venezuelareporta.json",
]


def run_scrapers():
    for label, cmd, cwd in SCRAPERS:
        print(f">>> scraper: {label}")
        rc = subprocess.run(cmd, cwd=str(cwd)).returncode
        if rc != 0:
            print(f"   ERROR {label} (rc={rc}) — se continúa", file=sys.stderr)


def ingest(paths):
    for p in map(Path, paths):
        if not p.exists():
            print(f"   omitido (no existe): {p}", file=sys.stderr)
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"   ingerido {p.name}: {len(data)} registros")
        yield from data


def write_rejected(rechazados, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CANONICAL_COLUMNS + ["motivo_rechazo"])
        for r in rechazados:
            motivo = "sin id" if r.get("id") in (None, "") else "sin nombre"
            w.writerow([r.get(c, "") for c in CANONICAL_COLUMNS] + [motivo])


def main():
    ap = argparse.ArgumentParser(description="Corrida del consolidador (delta vs maestro).")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--migrations", default=str(MIGRATIONS))
    ap.add_argument("--max-mb", type=float, default=5.0)
    ap.add_argument("--no-scrape", action="store_true", help="No corre scrapers (usa salidas existentes).")
    ap.add_argument("--input", nargs="*", help="JSONs a ingerir (override de las fuentes).")
    ap.add_argument("--upload", action="store_true", help="Sube el delta a la API (producción).")
    ap.add_argument("--no-cotejo", action="store_true", help="No corre el cotejo cross-source.")
    args = ap.parse_args()

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = OUT / run_id   # FIJO en consolidator/out/<run_id>/
    sources = args.input if args.input else INGEST
    print(f"== corrida {run_id} ==")

    reporte = run(
        db=args.db, migrations=args.migrations, out_dir=out_dir,
        sources=sources, run_id=run_id, max_mb=args.max_mb,
        scrape=not args.no_scrape, upload=args.upload, cotejo=not args.no_cotejo,
    )
    print(f"procesados={reporte['procesados']} nuevos={reporte['nuevos']} "
          f"actualizados={reporte['actualizados']} sin_cambio={reporte['sin_cambio']} "
          f"dup_lote={reporte['duplicados_lote']} rechazados={reporte['rechazados']}")
    print(f"salida en {out_dir}  ({len(reporte['archivos_xls'])} xls)")


def run(db, migrations, out_dir, sources, run_id, max_mb=5.0, scrape=False,
        upload=False, cotejo=True):
    """Ejecuta la corrida completa y devuelve el reporte. Parametrizable para tests;
    main() la invoca con out_dir fijo en consolidator/out/<run_id>/."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    # 1. AUTO: levantar + cargar la DB
    mig.migrate(db, migrations)

    # 2. scrapers
    if scrape:
        run_scrapers()

    # 3. ingesta  +  4. diff contra el maestro
    records = list(ingest(sources))
    # Normalización previa al diff
    from consolidator.lib.normalizar import split_multi_persona, dedup_por_nombre
    records = split_multi_persona(records)
    records = dedup_por_nombre(records)
    con = sqlite3.connect(str(db))
    res = diffmod.classify(records, diffmod.load_master_index(con))
    con.close()
    delta = res["nuevos"] + res["actualizados"]

    # 5. salidas del delta: xls + rechazados
    xls = export_delta(delta, out_dir, max_mb=max_mb)
    write_rejected(res["rechazados"], out_dir / "rechazados.csv")

    # 6. emitir el delta como migración y aplicarlo (maestro al día)
    if delta:
        emit_migrations(delta, migrations, next_version(migrations), f"run_{run_id}")
        mig.migrate(db, migrations)

    reporte = {
        "run_id": run_id, "started_at": started,
        "procesados": res["procesados"],
        "nuevos": len(res["nuevos"]),
        "actualizados": len(res["actualizados"]),
        "sin_cambio": res["sin_cambio"],
        "duplicados_lote": res["duplicados_lote"],
        "rechazados": len(res["rechazados"]),
        "delta_total": len(delta),
        "archivos_xls": [p.name for p in xls],
    }

    # 7. cotejo cross-source sobre el maestro YA actualizado (parte del pipeline).
    # Por corrida se escriben SOLO las alertas críticas (lo accionable); la cola
    # completa de coincidencias se saca on-demand con cotejo.py standalone.
    if cotejo:
        grupos = cotejomod.find_matches(cotejomod.load_master_records(db))
        reporte["cotejo"] = cotejomod.summarize(grupos)   # conteos sobre TODOS los grupos
        alertas = [g for g in grupos if g["alerta_critica"]]
        (out_dir / "alertas.json").write_text(
            json.dumps(alertas, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"cotejo: {reporte['cotejo']['grupos_coincidencia']} grupos, "
              f"{reporte['cotejo']['alertas_criticas']} alertas críticas -> alertas.json")

    # 8. subir el delta a la API (opt-in; pega a producción)
    if upload and xls:
        from consolidator.lib import api   # import perezoso: requests solo si se sube
        reporte["subida"] = api.upload_delta(xls)
        oks = sum(1 for r in reporte["subida"] if r["ok"])
        print(f"subida API: {oks}/{len(xls)} partes OK")

    # 9. escribir el reporte (incluye cotejo + subida)
    (out_dir / "reporte.json").write_text(
        json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")

    # 10. registrar la corrida
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT OR REPLACE INTO runs"
        "(run_id, started_at, procesados, nuevos, actualizados, sin_cambio, rechazados)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_id, started, res["procesados"], len(res["nuevos"]),
         len(res["actualizados"]), res["sin_cambio"], len(res["rechazados"])),
    )
    con.commit()
    con.close()
    return reporte


if __name__ == "__main__":
    main()
