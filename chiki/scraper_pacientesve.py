import urllib.request
import urllib.parse
import json
import csv
import time
import uuid
import hashlib
from datetime import datetime, timezone

import os
from dotenv import load_dotenv
load_dotenv()

API_KEY  = os.getenv("GOOGLE_API_KEY")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_TAB = "lista"

if not API_KEY or not SHEET_ID:
    print("Error: faltan GOOGLE_API_KEY o GOOGLE_SHEET_ID en el .env", file=sys.stderr)
    sys.exit(1)

def map_id(val):
    if not val:
        return 0
    try:
        return uuid.UUID(str(val)).int % 9223372036854775807
    except ValueError:
        h = hashlib.sha256(str(val).encode('utf-8')).hexdigest()
        return int(h, 16) % 9223372036854775807

def clean_str(val):
    return str(val).replace("\n", " ").strip() if val else None

def main():
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{urllib.parse.quote(SHEET_TAB)}?key={API_KEY}"
    
    # We must use the exact Referer header allowed by the Google Sheets API Key
    headers = {
        "Referer": "https://pacientesve.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("====================================================")
    print("      SCRAPER PACIENTESVE.COM -> ESQUEMA BBDD       ")
    print("====================================================")
    print("Conectando con Google Sheets API...")
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error al descargar los datos: {e}")
        return

    rows = res_data.get("values", [])
    if not rows:
        print("No se encontraron filas de datos.")
        return
        
    print(f"Descargados {len(rows)} registros (incluyendo cabecera). Procesando...")
    
    # Skip header row
    data_rows = rows[1:]
    all_rows = []
    
    # Schema headers
    headers_schema = [
        "id", "nombre", "cedula", "edad", "ultima_ubicacion", 
        "telefono_contacto", "observaciones", "estado", 
        "ubicacion_encontrado", "encontrado_por", "encontrado_por_cedula", 
        "foto_url", "fecha_registro", "fecha_actualizacion", "es_menor"
    ]
    
    default_date = datetime(2025, 6, 25, tzinfo=timezone.utc).isoformat()
    now_date = datetime.now(timezone.utc).isoformat()
    
    for r in data_rows:
        if not r or not r[0]:
            continue
            
        nombre = clean_str(r[0])
        cedula = clean_str(r[1]) if len(r) > 1 and r[1] else "N/D"
        
        # Edad
        edad = None
        if len(r) > 2 and r[2]:
            try:
                edad = int(float(clean_str(r[2])))
            except ValueError:
                pass
                
        hospital = clean_str(r[3]) if len(r) > 3 and r[3] else None
        estado_salud = clean_str(r[4]) if len(r) > 4 and r[4] else ""
        condicion = clean_str(r[5]) if len(r) > 5 and r[5] else ""
        notas = clean_str(r[6]) if len(r) > 6 and r[6] else ""
        
        # Construct observations
        obs_parts = []
        if estado_salud:
            obs_parts.append(f"Estado: {estado_salud}")
        if condicion:
            obs_parts.append(f"Condición: {condicion}")
        if notas:
            obs_parts.append(f"Notas: {notas}")
        observaciones = ". ".join(obs_parts) + "." if obs_parts else None
        
        # es_menor
        es_menor = False
        if edad is not None and edad < 18:
            es_menor = True
            
        unique_str = f"{nombre}_{cedula}_{hospital}"
        
        mapped = {
            "id": map_id(unique_str),
            "nombre": nombre,
            "cedula": cedula,
            "edad": edad,
            "ultima_ubicacion": hospital,
            "telefono_contacto": None,
            "observaciones": observaciones,
            "estado": "Localizado",  # Sigue en el hospital, por ende localizado
            "ubicacion_encontrado": hospital,
            "encontrado_por": None,
            "encontrado_por_cedula": None,
            "foto_url": None,
            "fecha_registro": default_date,
            "fecha_actualizacion": now_date,
            "es_menor": es_menor
        }
        all_rows.append(mapped)

    # Write files
    output_csv = "pacientes_hospitalizados.csv"
    output_json = "pacientes_hospitalizados.json"
    
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as csv_file:
        csv_writer = csv.DictWriter(csv_file, fieldnames=headers_schema, extrasaction="ignore")
        csv_writer.writeheader()
        csv_writer.writerows(all_rows)
        
    with open(output_json, "w", encoding="utf-8") as json_file:
        json.dump(all_rows, json_file, indent=2, ensure_ascii=False)
        
    print(f"\nProceso finalizado. Se guardaron {len(all_rows)} registros en:")
    print(f"  - CSV: '{output_csv}'")
    print(f"  - JSON: '{output_json}'")

if __name__ == "__main__":
    main()
