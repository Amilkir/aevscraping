import urllib.request
import urllib.error
import json
import csv
import sys
import argparse
import time
import uuid
import hashlib
from datetime import datetime, timezone

# Fuente: reportave.app — API REST publica, sin auth, sin paginacion.
# Un unico GET a /api/missing devuelve todos los registros en un array JSON plano.
# Estado de persona: campo "status" (solo "desaparecida" observado) +
# "found_reports_count" > 0 senala avistamientos/localizacion.

FUENTE = "reportave"
BASE_URL = "https://reportave.app/api"
USER_AGENT = "CentralizadorHumanitario/1.0 (Contacto: ayuda-humanitaria@ejemplo.com)"

CANONICAL_COLUMNS = [
    "id", "nombre", "cedula", "edad", "ultima_ubicacion", "telefono_contacto",
    "observaciones", "estado", "ubicacion_encontrado", "encontrado_por",
    "encontrado_por_cedula", "foto_url", "fecha_registro", "fecha_actualizacion",
    "es_menor", "fuente",
]


def map_id(val):
    if not val:
        return 0
    try:
        return uuid.UUID(str(val)).int % 9223372036854775807
    except ValueError:
        h = hashlib.sha256(str(val).encode("utf-8")).hexdigest()
        return int(h, 16) % 9223372036854775807


def map_timestamp(val):
    if not val:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
        try:
            return datetime.fromtimestamp(float(val) / 1000.0, timezone.utc).isoformat()
        except Exception:
            pass
    try:
        s = str(val).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).isoformat()
    except Exception:
        return str(val)


def _clean(val):
    if val is None:
        return None
    s = str(val).replace("\n", " ").strip()
    return s if s else None


def map_estado(item):
    if (item.get("found_reports_count") or 0) > 0:
        return "Localizado"
    status = (item.get("status") or "").lower()
    if "fallec" in status or "deceased" in status or "muert" in status:
        return "Fallecido"
    return "Desaparecido"


def map_row(item):
    nombre = _clean(item.get("name")) or "Desconocido"
    edad = item.get("age")
    ultima_ubicacion = _clean(item.get("last_seen_place"))
    estado = map_estado(item)
    fecha = map_timestamp(item.get("created_at"))

    # Descripcion + coordenadas como observaciones
    partes = []
    desc = _clean(item.get("description"))
    if desc:
        partes.append(desc)
    lat = item.get("lat")
    lng = item.get("lng")
    if lat is not None and lng is not None:
        partes.append(f"Coords: {lat}, {lng}")
    observaciones = " | ".join(partes) if partes else None

    es_menor = isinstance(edad, int) and edad < 18

    return {
        "id": map_id(item.get("id")),
        "nombre": nombre,
        "cedula": "N/D",
        "edad": edad,
        "ultima_ubicacion": ultima_ubicacion,
        "telefono_contacto": None,
        "observaciones": observaciones,
        "estado": estado,
        "ubicacion_encontrado": ultima_ubicacion if estado != "Desaparecido" else None,
        "encontrado_por": None,
        "encontrado_por_cedula": None,
        "foto_url": _clean(item.get("photo_url")),
        "fecha_registro": fecha,
        "fecha_actualizacion": fecha,
        "es_menor": es_menor,
        "fuente": FUENTE,
    }


def fetch_missing(tries=4, base_delay=2.0, timeout=30):
    url = f"{BASE_URL}/missing"
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500 and e.code != 429:
                raise
        except Exception as e:
            last = e
        if attempt < tries - 1:
            time.sleep(base_delay * (2 ** attempt))
    raise last


def write_outputs(rows, base):
    out_json = f"{base}.json"
    out_csv = f"{base}.csv"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return out_json, out_csv


def main():
    ap = argparse.ArgumentParser(
        description="Exporta personas desaparecidas de reportave.app al esquema unificado."
    )
    ap.add_argument("--output", default=FUENTE, help="Nombre base de salida sin extension.")
    ap.add_argument("--limit", type=int, default=None, help="Limite de registros (pruebas).")
    args = ap.parse_args()

    base = args.output
    for ext in (".json", ".csv"):
        if base.endswith(ext):
            base = base[: -len(ext)]

    print("====================================================")
    print("      SCRAPER reportave.app -> ESQUEMA BBDD         ")
    print("====================================================")
    print("Descargando registros...")

    try:
        data = fetch_missing()
    except Exception as e:
        print(f"Error al descargar datos: {e}", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        data = data[: args.limit]

    rows = [map_row(item) for item in data if item.get("name")]
    write_outputs(rows, base)

    estados = {}
    for r in rows:
        estados[r["estado"]] = estados.get(r["estado"], 0) + 1

    print(f"Registros descargados : {len(data)}")
    print(f"Registros exportados  : {len(rows)}")
    for estado, n in sorted(estados.items()):
        print(f"   {estado:<20}{n}")
    print(f"Archivos generados    : {base}.json / {base}.csv")


if __name__ == "__main__":
    main()
