import urllib.request
import urllib.parse
import json
import csv
import sys
import argparse
import time
import uuid
import hashlib
from datetime import datetime, timezone

SUPABASE_URL = "https://cpavwkdonvkvrwygfzfo.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNwYXZ3a2RvbnZrdnJ3eWdmemZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIzNjAyODMsImV4cCI6MjA5NzkzNjI4M30.-_FAsA2csTrB9qt267pBfjJkczMP7pcaUi4plMv3kv4"

def map_id(val):
    if not val:
        return 0
    try:
        # Convert UUID to bigint (signed 64-bit integer: max 9223372036854775807)
        return uuid.UUID(str(val)).int % 9223372036854775807
    except ValueError:
        # Fallback to standard SHA-256 hash if not a valid UUID string
        h = hashlib.sha256(str(val).encode('utf-8')).hexdigest()
        return int(h, 16) % 9223372036854775807

def map_timestamp(val):
    if not val:
        return datetime.now(timezone.utc).isoformat()
    # If it's a number (milliseconds Unix timestamp)
    if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
        try:
            return datetime.fromtimestamp(float(val) / 1000.0, timezone.utc).isoformat()
        except Exception:
            pass
    # If it's already an ISO or date string
    try:
        s = str(val).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except Exception:
        return str(val)

def map_row(item):
    # nombre: text, NOT NULL
    nombre = item.get("name")
    if not nombre:
        nombre = "Desconocido"
    else:
        nombre = str(nombre).strip()
        
    # cedula: text, NOT NULL
    cedula = "N/D" # Default placeholder
    
    # edad: integer, YES NULL
    edad_raw = item.get("age")
    edad = None
    if edad_raw is not None and str(edad_raw).strip() != "":
        try:
            edad = int(float(str(edad_raw).strip()))
        except ValueError:
            pass
            
    # ultima_ubicacion: text, YES NULL
    ultima_ubicacion = item.get("last_seen")
    if ultima_ubicacion:
        ultima_ubicacion = str(ultima_ubicacion).replace("\n", " ").strip()
    else:
        ultima_ubicacion = None
        
    # telefono_contacto: text, YES NULL
    telefono_contacto = item.get("contact")
    if telefono_contacto:
        telefono_contacto = str(telefono_contacto).replace("\n", " ").strip()
    else:
        telefono_contacto = None
        
    # observaciones: text, YES NULL
    observaciones = item.get("description")
    if observaciones:
        observaciones = str(observaciones).replace("\n", " ").strip()
    else:
        observaciones = None
        
    # estado: text, NOT NULL
    status = item.get("status")
    if status == "found":
        estado = "Localizado"
    else:
        estado = "Desaparecido"
        
    # ubicacion_encontrado, encontrado_por, encontrado_por_cedula: YES NULL
    ubicacion_encontrado = None
    encontrado_por = None
    encontrado_por_cedula = None
    
    # foto_url: text, YES NULL
    foto_url = item.get("photo_url")
    if foto_url:
        foto_url = str(foto_url).strip()
    else:
        foto_url = None
        
    # fecha_registro: timestamptz, NOT NULL
    fecha_registro = map_timestamp(item.get("ext_created"))
    
    # fecha_actualizacion: timestamptz, NOT NULL
    fecha_actualizacion = map_timestamp(item.get("synced_at"))
    if not item.get("synced_at"):
        fecha_actualizacion = fecha_registro
        
    # es_menor: boolean, NOT NULL
    es_menor = bool(item.get("is_child", False))
    
    return {
        "id": map_id(item.get("id")),
        "nombre": nombre,
        "cedula": cedula,
        "edad": edad,
        "ultima_ubicacion": ultima_ubicacion,
        "telefono_contacto": telefono_contacto,
        "observaciones": observaciones,
        "estado": estado,
        "ubicacion_encontrado": ubicacion_encontrado,
        "encontrado_por": encontrado_por,
        "encontrado_por_cedula": encontrado_por_cedula,
        "foto_url": foto_url,
        "fecha_registro": fecha_registro,
        "fecha_actualizacion": fecha_actualizacion,
        "es_menor": es_menor
    }

def fetch_chunk(status, offset, limit=1000):
    url = f"{SUPABASE_URL}/rest/v1/missing_persons?select=*&status=eq.{status}&order=ext_created.desc"
    # Set pagination headers
    req = urllib.request.Request(
        url,
        headers={
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {ANON_KEY}",
            "Range": f"{offset}-{offset + limit - 1}"
        }
    )
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
            return json.loads(content)
    except Exception as e:
        print(f"\nError fetching chunk starting at {offset}: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Exporta la lista de personas desaparecidas de Red Ayuda Venezuela y la adapta al esquema de base de datos.")
    parser.add_argument("--status", default="active", choices=["active", "found"], help="Estado de las personas a exportar (default: active).")
    parser.add_argument("--limit", type=int, default=None, help="Límite máximo de registros a descargar (para pruebas).")
    parser.add_argument("--output", default="desaparecidos", help="Nombre base de los archivos de salida sin extensión (default: desaparecidos).")
    args = parser.parse_args()

    # Determine base name for outputs
    output_base = args.output
    if output_base.endswith('.csv'):
        output_base = output_base[:-4]
    elif output_base.endswith('.json'):
        output_base = output_base[:-5]

    output_csv = f"{output_base}.csv"
    output_json = f"{output_base}.json"

    print("====================================================")
    print("      EXPORTADOR ADAPTADO A ESQUEMA BBDD            ")
    print("====================================================")
    print(f"Estado a descargar: {args.status}")
    print(f"Archivo CSV de salida: {output_csv}")
    print(f"Archivo JSON de salida: {output_json}")
    if args.limit:
        print(f"Límite de descarga: {args.limit} registros")
    print("----------------------------------------------------")

    offset = 0
    chunk_size = 1000
    total_written = 0
    all_rows = []
    
    headers = [
        "id", "nombre", "cedula", "edad", "ultima_ubicacion", 
        "telefono_contacto", "observaciones", "estado", 
        "ubicacion_encontrado", "encontrado_por", "encontrado_por_cedula", 
        "foto_url", "fecha_registro", "fecha_actualizacion", "es_menor"
    ]

    try:
        while True:
            # Check limit
            if args.limit and total_written >= args.limit:
                print(f"\nLímite de {args.limit} registros alcanzado.")
                break
                
            current_limit = chunk_size
            if args.limit and total_written + chunk_size > args.limit:
                current_limit = args.limit - total_written

            print(f"\rDescargando registros desde el índice {offset}... ", end="", flush=True)
            
            chunk = fetch_chunk(args.status, offset, current_limit)
            if chunk is None:
                # Retry once
                print("Reintentando en 3 segundos...")
                time.sleep(3)
                chunk = fetch_chunk(args.status, offset, current_limit)
                if chunk is None:
                    print("Error persistente. Deteniendo descarga.")
                    break

            if not chunk:
                print("\nNo hay más registros disponibles.")
                break

            for item in chunk:
                row = map_row(item)
                all_rows.append(row)
                total_written += 1

            offset += len(chunk)
            
            # Simple sleep to be polite with the server API
            time.sleep(0.1)

        # Write files if we have data
        if all_rows:
            # 1. Write CSV
            with open(output_csv, "w", newline="", encoding="utf-8-sig") as csv_file:
                csv_writer = csv.DictWriter(csv_file, fieldnames=headers, extrasaction="ignore")
                csv_writer.writeheader()
                csv_writer.writerows(all_rows)
            
            # 2. Write JSON
            with open(output_json, "w", encoding="utf-8") as json_file:
                json.dump(all_rows, json_file, indent=2, ensure_ascii=False)

            print(f"\nDescarga finalizada con éxito. Se guardaron {len(all_rows)} registros en:")
            print(f"  - CSV: '{output_csv}'")
            print(f"  - JSON: '{output_json}'")
        else:
            print("\nNo se encontraron registros para exportar.")

    except KeyboardInterrupt:
        print("\nDescarga cancelada por el usuario.")

if __name__ == "__main__":
    main()
