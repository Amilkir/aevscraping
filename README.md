# AEV Scraping — Centralizador Humanitario de Personas Desaparecidas

Pipeline de datos humanitarios que **scrapea reportes de personas desaparecidas**
desde varios sitios venezolanos independientes, **normaliza cada fuente a un único
esquema compartido**, los **consolida** en un store incremental y los **sube como
XLSX** a la API de `aquiestoyvenezuela.com`.

No hay sistema de build ni manifiesto de dependencias: es un conjunto de scrapers
independientes orquestados por `run_daily.py`.

## Gobernanza del fork Open-Vzla-SOS

Este repositorio es un **fork operativo mantenido por Open-Vzla-SOS**.

- Repositorio original upstream: [`Amilkir/aevscraping`](https://github.com/Amilkir/aevscraping).
- Función dentro del ecosistema: captura, scraping y consolidación inicial de información.
- La rama `main` se reserva para sincronización con upstream.
- La rama `develop` es la rama de integración de Open-Vzla-SOS.
- Todo cambio propio debe realizarse en ramas `feature/*`, `fix/*`, `docs/*`, `test/*` o `chore/*`.
- Los cambios propios deben llegar a `develop` mediante pull request.
- No deben ejecutarse scrapers, notebooks o procesos que utilicen datos reales, llamen servicios externos, escriban en APIs o afecten ambientes de producción sin autorización explícita. Las pruebas locales y aisladas deberán utilizar datos ficticios o anonimizados.
- Se identificaron riesgos heredados del upstream que deberán gestionarse mediante tareas separadas por los responsables correspondientes; su remediación queda fuera de este cambio.

---

## El esquema unificado es el contrato

Todo scraper, sin importar cómo luzca la fuente, debe emitir registros con los
**mismos 16 campos**. Cambiar este esquema implica tocar todos los scrapers y
`generate_xlsx.py`. Refleja la tabla Postgres/Supabase `missing_persons`
(ver `chiki/esquema-bbdd-sos-json (1).json`).

```
id, nombre, cedula, edad, ultima_ubicacion, telefono_contacto, observaciones,
estado, ubicacion_encontrado, encontrado_por, encontrado_por_cedula, foto_url,
fecha_registro, fecha_actualizacion, es_menor, fuente
```

Restricciones notables (NOT NULL): `id` (bigint), `nombre`, `cedula`, `estado`
(default `"Desaparecido"`), `fecha_registro`, `fecha_actualizacion`, `es_menor`.
De ahí los defaults (`"Desconocido"`, `"N/D"`, hora actual). `fuente` etiqueta qué
scraper produjo la fila y es parte de la clave de dedup `(id, fuente)`.

Helpers compartidos (duplicados por scraper, ver cada uno):
- `map_id` / `uuidToBigInt`: UUID de origen → entero estable de 64 bits con signo.
- `map_timestamp`: ms-epoch / ISO / sufijo `Z` → ISO-8601.

> Los `id` solo son estables **dentro de una fuente**, no entre fuentes (la versión
> JS usa otro algoritmo que la de Python).

---

## Webs que scrapeamos y quién se encarga

| Web | Script responsable | Estado | Mecanismo |
|---|---|---|---|
| sosvenezuela2026.com | `scrapers/sosvenezuela2026/scraper.py` | 🆕 Nuevo | API REST JSON paginada |
| venezuelatebusca.com | `Amilkir/scraper.js` | ✅ Activo | Turbo-stream `.data` (React Router v7) |
| redayudavenezuela.com | `chiki/scraper.py` | ✅ Activo | Supabase REST (anon key); el script pega directo a Supabase |
| desaparecidosterremotovenezuela.com | `chiki/scraper_terremoto.py` + `chiki/parse_desaparecidos.py` | ✅ Activo | API gated por reCAPTCHA v3 (vía Playwright) |
| venezuelareporta.org | `scrapers/venezuelareporta/scraper.py` | 🆕 Nuevo | SSR + sitemap enumerable (incremental con store JSON propio) |

**Fuera del pipeline diario:**
- `chiki/scraper_pacientesve.py` (+ `chiki/index.html/js/css`) — herramienta de
  pacientes hospitalizados, no forma parte del pipeline de desaparecidos.
- `consolidator/` — WIP hacia un esquema más amplio y nuevas fuentes; aún no
  cableado en `run_daily.py`.

---

## Pipeline (`run_daily.py`)

`run_daily.py` es el orquestador: ejecuta cada scraper en orden, consolida,
exporta y sube. El orden importa (cada paso depende de salidas anteriores):

1. `Amilkir/scraper.js --update` → `personas_venezuela.json`
2. `chiki/scraper.py --status active --output desaparecidos_redayudavenezuela`
3. `chiki/scraper.py --status found --output localizados_redayudavenezuela`
4. `chiki/scraper_terremoto.py` → `personas_desaparecidas_venezuela.json` (raw)
5. `chiki/parse_desaparecidos.py` → `..._parsed.json` (solo si el paso 4 tuvo éxito)
6. `merge_all()` → `datos_consolidados/todos_registros.json` (upsert por `(id, fuente)`)
7. `generate_xlsx.py` → `datos_consolidados/todos_registros.xlsx`
8. `send_to_api.py` (solo si el paso 7 tuvo éxito)

Logs se anexan a `logs/YYYY-MM-DD.log`. Programación diaria solo en Windows vía
`setup_tarea_diaria.ps1` (Task Scheduler, 02:00). En Linux se corre manualmente.

> ⚠️ `scrapers/sosvenezuela2026/` **aún no está cableado** en `run_daily.py`.

---

## Cómo correr

La vía recomendada es el **`Makefile`** (detecta el SO: Linux/macOS o Windows con
GNU make). Corre `make help` para ver todos los targets:

```bash
make install     # crea .venv e instala dependencias (openpyxl, requests)
make test        # corre TODOS los tests unitarios en un solo proceso (scripts/run_tests.py)
make scrape-sos  # corre el scraper de sosvenezuela2026
make scrape-vr   # venezuelareporta incremental (solo nuevos) · backfill-vr para --full
make consolidate # corre el consolidador (run_consolidacion.py)
make clean       # borra __pycache__, artefactos _smoke y el .venv
```

Equivalentes manuales (sin make):

```bash
# Pipeline diario completo
python run_daily.py

# Scrapers individuales (el cwd importa: escriben con rutas relativas a su dir)
cd scrapers/sosvenezuela2026 && python scraper.py --limit 5 --output _smoke
cd Amilkir                   && node scraper.js --test
cd chiki                     && python scraper.py --status active --limit 100 --output test_out
cd chiki                     && python scraper_terremoto.py && python parse_desaparecidos.py

# Exportar + subir desde el store consolidado (desde la raíz)
python generate_xlsx.py
python send_to_api.py

# Todos los tests unitarios en un solo proceso (equivale a `make test`)
.venv/bin/python scripts/run_tests.py
```

Dependencias (sin manifiesto, instalar a demanda):
`pip install requests openpyxl playwright && playwright install chromium`. Node 18+
para el scraper de venezuelatebusca.

---

# Scrapers

Cada scraper documenta su funcionamiento **completo** en el README de su directorio.
Aquí solo el índice con una línea de resumen y el enlace:

| Fuente | Resumen | Documentación |
|---|---|---|
| **sosvenezuela2026.com** | API REST JSON paginada (solo-listado). | [scrapers/sosvenezuela2026/README.md](scrapers/sosvenezuela2026/README.md) |
| **venezuelareporta.org** | SSR + sitemap (~53k páginas); incremental con store JSON propio + `--full`. | [scrapers/venezuelareporta/README.md](scrapers/venezuelareporta/README.md) |
| **venezuelatebusca.com** | Turbo-stream `.data` (React Router v7); Node. | [Amilkir/README.md](Amilkir/README.md) |
| **redayudavenezuela.com** | Supabase REST (`missing_persons`, anon key). | [chiki/README.md](chiki/README.md) |
| **desaparecidosterremotovenezuela.com** | API reCAPTCHA v3 vía Playwright + parse. | [chiki/README.md](chiki/README.md) |

> Los scrapers nuevos (`scrapers/`) traen documentación detallada. Los anteriores
> (`Amilkir/`, `chiki/`) tienen un README inicial; su dev responsable completa el detalle.
