import json
from consolidator.lib.normalizar import split_multi_persona, dedup_por_nombre, normalizar_telefono, _split_nombre

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

print('\n--- Nombres con y en la muestra ---')
con_y = [r for r in muestra if ' y ' in str(r.get('nombre', '')).lower()]
print(f'Con y en muestra: {len(con_y)}')
for r in con_y[:10]:
    nombre = r['nombre']
    resultado = _split_nombre(nombre)
    print(f'  ORIGINAL: {nombre}')
    print(f'  SPLIT:    {resultado}')

print('\n--- Test telefonos ---')
casos = [
    "+58 414-3130578",
    "04128246667 o 04263644689",
    "Jesus Robles 04144023661",
    "Patricia · +56966276557",
    "Instagram: @xabylom",
    "Tia trina",
    "+5491123578475, +5491158253960",
    "Ginger +58 412-5859840 o Isbelys Torrealba 0414-0216432",
    "042494947699",
    "+1 (385) 490-9206",
    "0212-4728471",
    "0212-3316555 / 0212-3327394 / 0212-3329667",
]
for caso in casos:
    print(f"  '{caso}' -> '{normalizar_telefono(caso)}'")

print('\n--- Diagnostico telefonos prueba_input ---')
data2 = json.load(open('prueba_input.json', encoding='utf-8'))
con_tel = [r for r in data2 if r.get('telefono_contacto')]
print(f'Con telefono: {len(con_tel)}')

vaciados = 0
normalizados = 0
for r in con_tel:
    original = r['telefono_contacto']
    resultado = normalizar_telefono(original)
    if original and not resultado:
        vaciados += 1
    elif original != resultado:
        normalizados += 1

print(f'Total con telefono: {len(con_tel)}')
print(f'Normalizados (cambiaron): {normalizados}')
print(f'Vaciados (sin numero valido): {vaciados}')
print(f'Quedaron igual (ya validos): {len(con_tel) - normalizados - vaciados}')