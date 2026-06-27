import json
import csv
import sys
import uuid
import hashlib
from datetime import datetime, timezone

def map_id(val):
    if not val:
        return 0
    try:
        return uuid.UUID(str(val)).int % 9223372036854775807
    except ValueError:
        h = hashlib.sha256(str(val).encode('utf-8')).hexdigest()
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
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except Exception:
        return str(val)

def clean_str(val):
    return str(val).replace("\n", " ").strip() if val else None

def main():
    input_path = "personas_desaparecidas_venezuela.json"
    output_csv = "personas_desaparecidas_venezuela_parsed.csv"
    output_json = "personas_desaparecidas_venezuela_parsed.json"

    print("====================================================")
    print("      PARSER DESAPARECIDOS TERREMOTO VENEZUELA      ")
    print("====================================================")
    print(f"Cargando {input_path}...")
    
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error al cargar el archivo JSON: {e}", file=sys.stderr)
        return

    print(f"Total registros cargados: {len(data)}")
    print("Procesando y mapeando al esquema BBDD...")

    headers = [
        "id", "nombre", "cedula", "edad", "ultima_ubicacion", 
        "telefono_contacto", "observaciones", "estado", 
        "ubicacion_encontrado", "encontrado_por", "encontrado_por_cedula", 
        "foto_url", "fecha_registro", "fecha_actualizacion", "es_menor"
    ]

    all_rows = []
    filtered_count = 0

    for item in data:
        # Filter out spam/reported content (reports >= 3 or reportada = True)
        if item.get("reportada", False) or item.get("reportes", 0) >= 3:
            filtered_count += 1
            continue

        nombre = clean_str(item.get("nombre"))
        if not nombre:
            nombre = "Desconocido"

        # Edad
        edad = None
        edad_raw = item.get("edad")
        if edad_raw is not None and str(edad_raw).strip() != "":
            try:
                edad = int(float(str(edad_raw).strip()))
            except ValueError:
                pass

        # Ultima ubicación
        ultima_ubicacion = clean_str(item.get("ubicacion"))
        
        # Telefono contacto
        telefono_contacto = clean_str(item.get("contacto"))

        # Observaciones (unir descripción, nota de localización y fecha indicada)
        obs_parts = []
        descripcion = clean_str(item.get("descripcion"))
        if descripcion:
            obs_parts.append(descripcion)
        
        localizado_nota = clean_str(item.get("localizadoNota"))
        if localizado_nota:
            obs_parts.append(f"Nota localización: {localizado_nota}")
            
        fecha_indicada = clean_str(item.get("fecha"))
        if fecha_indicada:
            obs_parts.append(f"Fecha del suceso: {fecha_indicada}")

        observaciones = ". ".join(obs_parts) + "." if obs_parts else None

        # Estado
        estado_raw = item.get("estado")
        if estado_raw == "localizado":
            estado = "Localizado"
            ubicacion_encontrado = ultima_ubicacion
            encontrado_por = clean_str(item.get("localizadoPor"))
        else:
            estado = "Desaparecido"
            ubicacion_encontrado = None
            encontrado_por = None

        encontrado_por_cedula = None
        foto_url = clean_str(item.get("foto"))
        fecha_registro = map_timestamp(item.get("createdAt"))
        fecha_actualizacion = map_timestamp(item.get("updatedAt"))

        # es_menor
        es_menor = False
        if edad is not None and edad < 18:
            es_menor = True

        row = {
            "id": map_id(item.get("id")),
            "nombre": nombre,
            "cedula": "N/D",
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
        all_rows.append(row)

    print(f"Registros omitidos (reportados/spam): {filtered_count}")
    print(f"Registros válidos a escribir: {len(all_rows)}")

    # Write CSV
    try:
        with open(output_csv, "w", newline="", encoding="utf-8-sig") as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=headers, extrasaction="ignore")
            csv_writer.writeheader()
            csv_writer.writerows(all_rows)
        print(f"Guardado CSV exitosamente en '{output_csv}'")
    except Exception as e:
        print(f"Error al escribir CSV: {e}", file=sys.stderr)

    # Write JSON
    try:
        with open(output_json, "w", encoding="utf-8") as json_file:
            json.dump(all_rows, json_file, indent=2, ensure_ascii=False)
        print(f"Guardado JSON exitosamente en '{output_json}'")
    except Exception as e:
        print(f"Error al escribir JSON: {e}", file=sys.stderr)

    print("----------------------------------------------------")
    print("Proceso completado exitosamente.")

if __name__ == "__main__":
    main()
