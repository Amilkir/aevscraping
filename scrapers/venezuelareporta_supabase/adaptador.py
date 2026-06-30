"""
adaptador.py

Transforma el CSV de venezuelareporta.org (extraído vía Supabase) al esquema
canónico de 16 columnas que usa el consolidador.

Entrada: venezuelareporta_data_actualizado.csv
Salida:  venezuelareporta_supabase.json (mismo esquema que los demás scrapers)
"""

import csv
import json
import sys
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone

INPUT_FILE = Path(__file__).parent / "venezuelareporta_data_actualizado.csv"
OUTPUT_FILE = Path(__file__).parent / "venezuelareporta_supabase.json"

# Mapeo de status de Supabase -> estado canónico
STATUS_MAP = {
    "buscando": "Desaparecido",
    "encontrado": "Localizado",
    "a_salvo": "Localizado",
}


def map_id(val):
    """UUID -> bigint estable de 64 bits con signo. Misma lógica que los demás scrapers."""
    if not val:
        return 0
    try:
        return uuid.UUID(str(val)).int % 9223372036854775807
    except ValueError:
        h = hashlib.sha256(str(val).encode('utf-8')).hexdigest()
        return int(h, 16) % 9223372036854775807


def clean_str(val):
    return str(val).strip() if val else None


def construir_ubicacion(ciudad, zona):
    partes = [p for p in (clean_str(ciudad), clean_str(zona)) if p]
    return ", ".join(partes) if partes else None


def construir_observaciones(genero, ultima_vez, descripcion):
    partes = []
    if clean_str(genero):
        partes.append(f"Género: {genero.strip().capitalize()}")
    if clean_str(ultima_vez):
        partes.append(ultima_vez.strip())
    if clean_str(descripcion):
        partes.append(descripcion.strip())
    return ". ".join(partes) + "." if partes else None


def map_fecha(created_at):
    """created_at viene como ISO con offset, ej: 2026-06-28T22:54:49.933937+00:00"""
    if not created_at:
        return datetime.now(timezone.utc).isoformat()
    return created_at


def transformar_registro(row):
    nombre = clean_str(row.get("nombre"))
    if not nombre:
        return None  # sin nombre, se rechaza igual que el resto del pipeline

    status_original = clean_str(row.get("status")) or "buscando"
    estado = STATUS_MAP.get(status_original.lower(), "Desaparecido")

    ubicacion = construir_ubicacion(row.get("ciudad"), row.get("zona"))

    edad = None
    if clean_str(row.get("edad")):
        try:
            edad = int(float(row["edad"]))
        except ValueError:
            edad = None

    es_menor = edad is not None and edad < 18

    fecha = map_fecha(row.get("created_at"))

    return {
        "id": map_id(row.get("id")),
        "nombre": nombre,
        "cedula": clean_str(row.get("cedula")) or "N/D",
        "edad": edad,
        "ultima_ubicacion": ubicacion,
        "telefono_contacto": None,
        "observaciones": construir_observaciones(
            row.get("genero"), row.get("ultima_vez"), row.get("descripcion")
        ),
        "estado": estado,
        "ubicacion_encontrado": ubicacion if estado != "Desaparecido" else None,
        "encontrado_por": None,
        "encontrado_por_cedula": None,
        "foto_url": clean_str(row.get("foto_url")),
        "fecha_registro": fecha,
        "fecha_actualizacion": fecha,
        "es_menor": es_menor,
        "fuente": "venezuelareporta",
    }


def main():
    if not INPUT_FILE.exists():
        print(f"Error: no se encontró {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    print("====================================================")
    print("  ADAPTADOR VENEZUELAREPORTA (Supabase -> canónico) ")
    print("====================================================")

    with open(INPUT_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Leídos {len(rows)} registros del CSV.")

    resultado = []
    rechazados = 0
    for row in rows:
        r = transformar_registro(row)
        if r is None:
            rechazados += 1
            continue
        resultado.append(r)

    print(f"Transformados: {len(resultado)}")
    print(f"Rechazados (sin nombre): {rechazados}")

    OUTPUT_FILE.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()