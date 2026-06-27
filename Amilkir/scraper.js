/**
 * scraper.js
 * 
 * Extractor eficiente e incremental para la plataforma venezuelatebusca.com.
 * Consume el endpoint optimizado de datos (.data) sin levantar navegadores pesados.
 * 
 * Caracteristicas:
 * - Conexiones persistentes mediante Fetch API nativa.
 * - Delays aleatorios de cortesia (1.5s promedio) para proteger el servidor del sitio.
 * - Control de errores y reintentos automaticos con exponencial backoff.
 * - Deserializacion del flujo turbo-stream de React Router v7.
 * - Modo Test (descarga rapida) y Modo Incremental (sincronizacion delta).
 * 
 * Requisitos: Node.js v18+ (instalado: v24.13.0)
 * Uso:
 *   - Modo Test (3 paginas):  node scraper.js --test
 *   - Modo Completo (Todo):   node scraper.js --full
 *   - Modo Actualizar:        node scraper.js --update
 */

const fs = require('fs');
const path = require('path');

// CONFIGURACION DE PARAMETROS
const CONFIG = {
    urlBase: 'https://venezuelatebusca.com/.data',
    outputFile: path.join(__dirname, 'personas_venezuela.json'),
    outputFileCsv: path.join(__dirname, 'personas_venezuela.csv'),
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) CentralizadorHumanitario/1.0 (Contacto: ayuda-humanitaria@ejemplo.com)',
    delayMinMs: 1000,
    delayMaxMs: 2000,
    maxRetries: 3,
    backoffBaseMs: 2000
};

// ==========================================
// 1. MOTOR DE DESERIALIZACION (REACT ROUTER v7)
// ==========================================
function deserialize(root) {
    const cache = new Map();

    function resolve(val) {
        if (val === -7) return null;
        if (val === -5) return undefined;
        if (typeof val === 'number') {
            if (val < 0) return null;
            return deserializeNode(val);
        }
        return val;
    }

    function deserializeNode(index) {
        if (cache.has(index)) {
            return cache.get(index);
        }

        const val = root[index];
        if (val === null || typeof val !== 'object') {
            return val;
        }

        if (Array.isArray(val)) {
            const arr = [];
            cache.set(index, arr);
            for (const item of val) {
                arr.push(resolve(item));
            }
            return arr;
        }

        const obj = {};
        cache.set(index, obj);
        for (const key of Object.keys(val)) {
            if (key.startsWith('_')) {
                const propIndex = parseInt(key.slice(1), 10);
                const propName = root[propIndex];
                const propValueRef = val[key];
                obj[propName] = resolve(propValueRef);
            } else {
                obj[key] = resolve(val[key]);
            }
        }
        return obj;
    }

    return deserializeNode(0);
}

// Helper para retardos asincronos
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Helper para obtener delay aleatorio
const getRandomDelay = () => {
    return Math.floor(Math.random() * (CONFIG.delayMaxMs - CONFIG.delayMinMs + 1) + CONFIG.delayMinMs);
};

// ==========================================
// 2. FUNCION DE EXTRACCION DE PAGINA INDIVIDUAL
// ==========================================
async function fetchPage(pageNumber) {
    const url = `${CONFIG.urlBase}?page=${pageNumber}`;
    let attempt = 0;
    
    while (attempt < CONFIG.maxRetries) {
        try {
            const res = await fetch(url, {
                headers: {
                    'User-Agent': CONFIG.userAgent,
                    'Accept': 'text/x-turbo-stream'
                }
            });

            if (res.status === 429) {
                const retryAfter = res.headers.get('Retry-After') || 5;
                console.warn(`[!] Advertencia: Codigo 429 (Too Many Requests). Esperando ${retryAfter} segundos antes de reintentar...`);
                await sleep(retryAfter * 1000);
                attempt++;
                continue;
            }

            if (!res.ok) {
                throw new Error(`HTTP Error: ${res.status} ${res.statusText}`);
            }

            const text = await res.text();
            const firstLine = text.split('\n')[0];
            const rootArray = JSON.parse(firstLine);
            
            // Deserializar la respuesta estructurada
            const tree = deserialize(rootArray);
            
            // Extraer registros del nodo correspondiente
            const pageData = tree['routes/_index']?.data;
            if (!pageData) {
                throw new Error('No se encontro la seccion de datos en la estructura deserializada.');
            }

            return {
                persons: pageData.persons || [],
                hasMore: pageData.pagination?.hasMore ?? false,
                totalCount: pageData.stats?.totalCount ?? 34000
            };

        } catch (err) {
            attempt++;
            const backoffTime = CONFIG.backoffBaseMs * Math.pow(2, attempt);
            console.error(`[Error] Fallo la descarga de la pagina ${pageNumber} (Intento ${attempt}/${CONFIG.maxRetries}): ${err.message}`);
            
            if (attempt >= CONFIG.maxRetries) {
                throw new Error(`Excedido el numero maximo de reintentos para la pagina ${pageNumber}. Deteniendo extractor.`);
            }
            
            console.log(`Esperando ${backoffTime / 1000} segundos antes de reintentar...`);
            await sleep(backoffTime);
        }
    }
}

// ==========================================
// 2.5. FUNCIONES DE MAPEADO Y ESQUEMA BBDD
// ==========================================
function uuidToBigInt(uuid) {
    if (typeof uuid !== 'string') return 0;
    let hash = 0;
    for (let i = 0; i < uuid.length; i++) {
        hash = (hash * 31 + uuid.charCodeAt(i)) % 9007199254740991;
    }
    return hash;
}

function mapToSchema(person) {
    const nombre = ((person.firstName || '') + (person.lastName ? ' ' + person.lastName : '')).trim() || 'No disponible';
    const cedula = (person.idNumber || '').trim() || 'No registrado';
    
    let estado = 'Desaparecido';
    if (person.status === 'found') estado = 'Localizado';
    else if (person.status === 'deceased') estado = 'Fallecido';
    
    let foto_url = null;
    if (person.photoUrl) {
        foto_url = person.photoUrl.startsWith('/') 
            ? `https://venezuelatebusca.com${person.photoUrl}` 
            : person.photoUrl;
    }

    const edad = typeof person.age === 'number' ? person.age : null;
    const es_menor = edad !== null && edad < 18;

    return {
        id: uuidToBigInt(person.id),
        nombre: nombre,
        cedula: cedula,
        edad: edad,
        ultima_ubicacion: person.lastSeen || null,
        telefono_contacto: person.reporter?.phone || null,
        observaciones: person.description || null,
        estado: estado,
        ubicacion_encontrado: null,
        encontrado_por: person.finder || null,
        encontrado_por_cedula: null,
        foto_url: foto_url,
        fecha_registro: person.createdAt || new Date().toISOString(),
        fecha_actualizacion: person.updatedAt || person.lastActivityAt || person.createdAt || new Date().toISOString(),
        es_menor: es_menor
    };
}

// ==========================================
// 2.7. CONVERSOR A FORMATO CSV
// ==========================================
function convertToCSV(data) {
    const headers = [
        'id', 'nombre', 'cedula', 'edad', 'ultima_ubicacion', 'telefono_contacto', 
        'observaciones', 'estado', 'ubicacion_encontrado', 'encontrado_por', 
        'encontrado_por_cedula', 'foto_url', 'fecha_registro', 'fecha_actualizacion', 'es_menor'
    ];

    const escapeValue = (val) => {
        if (val === null || val === undefined) {
            return '';
        }
        if (typeof val === 'boolean') {
            return val ? 'true' : 'false';
        }
        const str = String(val);
        if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
            return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
    };

    const rows = [headers.join(',')];
    for (const row of data) {
        const values = headers.map(header => escapeValue(row[header]));
        rows.push(values.join(','));
    }
    return rows.join('\r\n');
}

// ==========================================
// 3. FLUJO PRINCIPAL Y MODOS DE EJECUCION
// ==========================================
async function run() {
    const mode = process.argv[2] || '--test';
    
    console.log('====================================================');
    console.log('      EXTRACTOR HUMANITARIO VENEZUELA TE BUSCA       ');
    console.log('====================================================');
    console.log(`Modo seleccionado: ${mode}`);
    console.log(`Archivo de salida: ${CONFIG.outputFile}\n`);

    let existingData = [];
    let existingIds = new Set();

    // Cargar datos existentes para de-duplicacion y modo incremental
    if (fs.existsSync(CONFIG.outputFile)) {
        try {
            existingData = JSON.parse(fs.readFileSync(CONFIG.outputFile, 'utf-8'));
            existingIds = new Set(existingData.map(p => p.id));
            console.log(`Base de datos local cargada: ${existingData.length} registros existentes.`);
        } catch (err) {
            console.warn(`Advertencia: No se pudo parsear ${CONFIG.outputFile}, se iniciara una base de datos nueva.`, err.message);
        }
    } else {
        console.log('No se detecto base de datos previa. Se creara un archivo nuevo.');
    }

    let page = 1;
    let hasMore = true;
    let newRecords = [];
    let stoppedByIncremental = false;

    // Determinar limite de paginas en modo test
    const isTestMode = mode === '--test';
    const isUpdateMode = mode === '--update';
    const isFullMode = mode === '--full';

    if (!isTestMode && !isUpdateMode && !isFullMode) {
        console.error('Error: Parametro no reconocido. Usa uno de los siguientes:');
        console.error('  node scraper.js --test    (Descarga rapida de prueba, 3 paginas)');
        console.error('  node scraper.js --full    (Descarga completa respetuosa de toda la base de datos)');
        console.error('  node scraper.js --update  (Actualizacion rapida de registros nuevos)');
        process.exit(1);
    }

    try {
        while (hasMore) {
            if (isTestMode && page > 5) {
                console.log('\n[Modo Test] Limite de 5 paginas (100 registros) alcanzado de forma exitosa.');
                break;
            }

            console.log(`[Pagina ${page}] Descargando registros...`);
            const startTime = Date.now();
            
            const result = await fetchPage(page);
            const downloadTime = ((Date.now() - startTime) / 1000).toFixed(2);
            
            console.log(`  -> Descargados ${result.persons.length} registros en ${downloadTime}s (Total global reportado: ${result.totalCount}).`);

            let pageNewCount = 0;
            
            for (const person of result.persons) {
                const mappedPerson = mapToSchema(person);
                if (existingIds.has(mappedPerson.id)) {
                    // Si estamos en modo actualizacion, nos detenemos al encontrar el primer ID que ya poseemos
                    if (isUpdateMode) {
                        stoppedByIncremental = true;
                    }
                } else {
                    newRecords.push(mappedPerson);
                    existingIds.add(mappedPerson.id);
                    pageNewCount++;
                }
            }

            if (pageNewCount > 0) {
                console.log(`  -> ${pageNewCount} nuevos registros agregados de esta pagina.`);
            }

            if (stoppedByIncremental) {
                console.log('\n[Modo Incremental] Se detectaron registros previamente almacenados. Sincronizacion completada.');
                break;
            }

            hasMore = result.hasMore;
            
            if (hasMore) {
                const delay = getRandomDelay();
                console.log(`  -> Respetando servidor: Esperando ${delay / 1000}s para la siguiente pagina...`);
                await sleep(delay);
                page++;
            }
        }

        // Consolidar y guardar resultados
        if (newRecords.length > 0 || (existingData.length > 0 && !fs.existsSync(CONFIG.outputFileCsv))) {
            const finalData = [...newRecords, ...existingData];
            
            // Guardar JSON
            fs.writeFileSync(CONFIG.outputFile, JSON.stringify(finalData, null, 2), 'utf-8');
            
            // Guardar CSV
            const csvContent = convertToCSV(finalData);
            fs.writeFileSync(CONFIG.outputFileCsv, csvContent, 'utf-8');
            
            console.log('\n====================================================');
            console.log(`PROCESO FINALIZADO CON EXITO.`);
            console.log(`Nuevos registros guardados: ${newRecords.length}`);
            console.log(`Total registros en base de datos consolidada: ${finalData.length}`);
            console.log(`Archivos generados:`);
            console.log(`  -> JSON: ${CONFIG.outputFile}`);
            console.log(`  -> CSV:  ${CONFIG.outputFileCsv}`);
            console.log('====================================================');
        } else {
            console.log('\n====================================================');
            console.log('Sincronizacion finalizada: No se encontraron registros nuevos.');
            console.log(`Total de registros en base de datos: ${existingData.length}`);
            console.log('====================================================');
        }

    } catch (err) {
        console.error('\n[Error Critico] El proceso de scraping se detuvo de forma inesperada:', err.message);
        
        // Guardar lo que se haya logrado extraer antes del fallo
        if (newRecords.length > 0) {
            const finalData = [...newRecords, ...existingData];
            fs.writeFileSync(CONFIG.outputFile, JSON.stringify(finalData, null, 2), 'utf-8');
            
            const csvContent = convertToCSV(finalData);
            fs.writeFileSync(CONFIG.outputFileCsv, csvContent, 'utf-8');
            
            console.log(`[Seguridad] Se guardaron de forma segura ${newRecords.length} registros extraidos antes del error.`);
        }
    }
}

run();
