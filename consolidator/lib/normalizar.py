"""
normalizar.py

Utilidades de normalización previas al diff:
  1. split_multi_persona: detecta registros con 2+ personas en el campo
     'nombre' y los expande en registros individuales.
  2. dedup_por_nombre: dentro de un mismo lote, si la misma persona aparece
     con distinto estatus, conserva el más resuelto (Localizado > Desaparecido).
"""

import re
import unicodedata
import hashlib

# Palabras que indican que el "y" NO separa dos personas sino una referencia
PALABRAS_REFERENCIA = {
    "familia", "esposa", "esposo", "hijo", "hija", "hijos", "hijas",
    "bebes", "bebe", "niño", "niña", "niños", "niñas", "su", "sus",
    "primo", "prima", "tia", "tio", "sobrina", "sobrino", "madre",
    "padre", "abuela", "abuelo", "amigo", "amiga",
}

STOPWORDS = {"de", "la", "del", "los", "las", "el", "san", "santa"}

STATUS_PRIORITY = {
    "localizado": 4,
    "encontrado": 3,
    "hospitalizado": 3,
    "fallecido": 2,
    "desaparecido": 1,
}


def _normalizar_texto(texto):
    """Minúsculas, sin acentos."""
    s = unicodedata.normalize("NFD", str(texto or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


def _status_priority(estado):
    s = _normalizar_texto(estado or "")
    for key, val in STATUS_PRIORITY.items():
        if key in s:
            return val
    return 0


def _es_nombre_propio(texto):
    """Retorna True si el texto parece un nombre propio (no es palabra de referencia)."""
    palabras = _normalizar_texto(texto).split()
    # Si la primera palabra es una referencia, no es nombre propio
    if not palabras:
        return False
    if palabras[0] in PALABRAS_REFERENCIA:
        return False
    # Si contiene solo stopwords tampoco
    significativas = [p for p in palabras if p not in STOPWORDS and len(p) > 2]
    return len(significativas) > 0


def _generar_id_derivado(id_original, sufijo):
    """Genera un id numérico estable para los registros splitteados."""
    base = f"{id_original}_{sufijo}"
    h = hashlib.md5(base.encode()).hexdigest()
    # Convertir a entero de 64 bits con signo
    return int(h[:15], 16)


def _split_nombre(nombre):
    """
    Dado un nombre con múltiples personas, retorna lista de nombres individuales.
    Si una parte tiene solo 1 palabra, hereda el apellido de la última parte
    que tenga estructura completa (nombre + apellido).
    """
    partes = re.split(r'\s+y\s+|,\s*', nombre, flags=re.IGNORECASE)
    partes = [p.strip() for p in partes if p.strip()]

    if len(partes) < 2:
        return [nombre]

    # Si alguna parte empieza con palabra de referencia, no splitear
    for parte in partes:
        palabras = _normalizar_texto(parte).split()
        if palabras and palabras[0] in PALABRAS_REFERENCIA:
            return [nombre]

    # Buscar la última parte con más de 1 palabra (tiene apellido)
    parte_con_apellido = None
    for parte in reversed(partes):
        if len(parte.strip().split()) > 1:
            parte_con_apellido = parte.strip()
            break

    if not parte_con_apellido:
        return [nombre]

    # Extraer apellidos: todo menos la primera palabra
    palabras = parte_con_apellido.split()
    apellidos = ' '.join(palabras[1:])

    # Construir nombres completos heredando apellido donde falte
    nombres_finales = []
    for parte in partes:
        parte = parte.strip()
        if len(parte.split()) == 1 and apellidos:
            nombres_finales.append(f"{parte} {apellidos}")
        else:
            nombres_finales.append(parte)

    # Descartar partes con menos de 2 palabras
    nombres_finales = [n for n in nombres_finales if len(n.split()) >= 2]

    if len(nombres_finales) < 2:
        return [nombre]

    return nombres_finales


def split_multi_persona(records):
    """
    Expande registros con múltiples personas en el nombre.
    Retorna la lista completa con los registros originales reemplazados
    por sus versiones individuales donde aplique.
    """
    resultado = []
    spliteados = 0

    for rec in records:
        nombre = str(rec.get("nombre") or "")

        # Solo procesar si tiene " y " o coma
        if " y " not in nombre.lower() and "," not in nombre:
            resultado.append(rec)
            continue

        nombres = _split_nombre(nombre)

        if len(nombres) == 1:
            # No se pudo splitear con seguridad
            resultado.append(rec)
            continue

        # Generar un registro por cada nombre
        for i, nom in enumerate(nombres):
            nuevo = dict(rec)
            nuevo["nombre"] = nom.strip()
            nuevo["id"] = _generar_id_derivado(rec["id"], i)
            nuevo["observaciones"] = (
                f"[Split de registro original: '{nombre}'] "
                + str(rec.get("observaciones") or "")
            ).strip()
            resultado.append(nuevo)
            spliteados += 1

        spliteados -= 1  # descontar el original que se reemplazó

    print(f"   split_multi_persona: {spliteados} registros nuevos generados")
    return resultado


def _normalizar_nombre_key(nombre):
    """Nombre normalizado para comparar: sin acentos, minúsculas, sin espacios dobles."""
    s = _normalizar_texto(nombre)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def dedup_por_nombre(records):
    """
    Dentro del lote, si la misma persona (mismo nombre normalizado) aparece
    más de una vez, conserva la de mayor prioridad de estatus.
    En caso de igual prioridad, conserva la más reciente por fecha_actualizacion.
    """
    from collections import defaultdict

    grupos = defaultdict(list)
    for rec in records:
        key = _normalizar_nombre_key(str(rec.get("nombre") or ""))
        grupos[key].append(rec)

    resultado = []
    duplicados = 0

    for key, grupo in grupos.items():
        if len(grupo) == 1:
            resultado.append(grupo[0])
            continue

        # Ordenar: mayor prioridad primero, luego más reciente
        grupo.sort(key=lambda r: (
            -_status_priority(r.get("estado")),
            str(r.get("fecha_actualizacion") or ""),
        ), reverse=False)

        # El primero tras ordenar es el que tiene mayor prioridad
        grupo.sort(key=lambda r: -_status_priority(r.get("estado")))
        resultado.append(grupo[0])
        duplicados += len(grupo) - 1

    print(f"   dedup_por_nombre: {duplicados} duplicados eliminados")
    return resultado