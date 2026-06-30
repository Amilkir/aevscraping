import json
from consolidator.lib.normalizar import split_multi_persona, dedup_por_nombre

data = json.load(open('datos_consolidados/todos_registros.json', encoding='utf-8'))
muestra = data[:5000]

print(f'Registros originales: {len(muestra)}')
spliteados = split_multi_persona(muestra)
print(f'Despues del split: {len(spliteados)}')
deduped = dedup_por_nombre(spliteados)
print(f'Despues del dedup: {len(deduped)}')

print('\n--- Ejemplos de splits ---')
for r in spliteados:
    if '[Split de registro original' in str(r.get('observaciones', '')):
        print(f"  {r['nombre']}")
        # Diagnostico: ver cuales nombres tienen " y " en la muestra
print('\n--- Nombres con y en la muestra ---')
con_y = [r for r in muestra if ' y ' in str(r.get('nombre', '')).lower()]
print(f'Con y en muestra: {len(con_y)}')
for r in con_y[:10]:
    nombre = r['nombre']
    from consolidator.lib.normalizar import _split_nombre
    resultado = _split_nombre(nombre)
    print(f'  ORIGINAL: {nombre}')
    print(f'  SPLIT:    {resultado}')
    print()
    from consolidator.lib.normalizar import normalizar_telefono

print('\n--- Test teléfonos ---')
casos = [
    "+58 414-3130578",
    "04128246667 o 04263644689",
    "Jesus Robles 04144023661",
    "Patricia · +56966276557",
    "Instagram: @xabylom",
    "Tía trina",
    "+5491123578475, +5491158253960",
    "Ginger +58 412-5859840 o Isbelys Torrealba 0414-0216432",
    "042494947699",
    "+1 (385) 490-9206",
]
for caso in casos:
    print(f"  '{caso}' → '{normalizar_telefono(caso)}'")