"""
scraper_terremoto.py

Scraper automatizado para desaparecidosterremotovenezuela.com usando Playwright.
Abre la página real en modo headless, ejecuta la extracción en el contexto del
navegador (donde reCAPTCHA v3 ya está cargado), y captura los datos en Python.

Requiere: pip install playwright && playwright install chromium
Salida:   personas_desaparecidas_venezuela.json  (mismo directorio del script)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

RECAPTCHA_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")
if not RECAPTCHA_KEY:
    print("Error: falta RECAPTCHA_SITE_KEY en el .env", file=sys.stderr)
    sys.exit(1)

try:
    from playwright.async_api import async_playwright
except ImportError:
    print(
        "Error: Playwright no está instalado.\n"
        "Ejecuta: pip install playwright && playwright install chromium",
        file=sys.stderr
    )
    sys.exit(1)

OUTPUT_FILE = Path(__file__).parent / "personas_desaparecidas_venezuela.json"

# Versión modificada del script de browser original:
# en lugar de disparar una descarga, devuelve el array de datos directamente.
JS_EXTRACTOR = """
async () => {
    const RECAPTCHA_KEY = "__RECAPTCHA_KEY__";
    const BASE_API = "https://desaparecidos-terremoto-api.theempire.tech/api";

    async function getRecaptchaToken(action) {
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(
                () => reject(new Error("reCAPTCHA timeout (15s)")), 15000
            );
            window.grecaptcha.ready(() => {
                clearTimeout(timeout);
                window.grecaptcha.execute(RECAPTCHA_KEY, { action }).then(resolve).catch(reject);
            });
        });
    }

    let page = 1;
    const pageSize = 50;
    const allPeople = [];

    while (true) {
        const token = await getRecaptchaToken("list_people");
        const res = await fetch(
            `${BASE_API}/personas?page=${page}&pageSize=${pageSize}`,
            {
                headers: {
                    "Content-Type": "application/json",
                    "x-recaptcha-token": token
                }
            }
        );

        if (!res.ok) {
            throw new Error(`Error en API: ${res.status} ${res.statusText}`);
        }

        const data = await res.json();
        const items = data.items || [];
        allPeople.push(...items);

        if (page >= (data.totalPages || 1) || items.length === 0) {
            break;
        }
        page++;
        await new Promise(r => setTimeout(r, 300));
    }

    return allPeople;
}
""".replace("__RECAPTCHA_KEY__", RECAPTCHA_KEY)


async def scrape():
    print("====================================================")
    print("  SCRAPER TERREMOTO VENEZUELA (Playwright/headless) ")
    print("====================================================")
    print("Iniciando navegador headless...")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "CentralizadorHumanitario/1.0"
            )
        )
        page = await context.new_page()

        print("Abriendo desaparecidosterremotovenezuela.com...")
        try:
            await page.goto(
                "https://desaparecidosterremotovenezuela.com/",
                wait_until="networkidle",
                timeout=60_000
            )
        except Exception as e:
            print(f"Advertencia al esperar networkidle: {e}", file=sys.stderr)

        print("Esperando que reCAPTCHA esté disponible...")
        try:
            await page.wait_for_function(
                "typeof window.grecaptcha !== 'undefined' && "
                "typeof window.grecaptcha.ready === 'function'",
                timeout=30_000
            )
        except Exception as e:
            print(f"Error: reCAPTCHA no se cargó: {e}", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        print("Ejecutando extractor de datos en el navegador...")
        try:
            data = await page.evaluate(JS_EXTRACTOR)
        except Exception as e:
            print(f"Error durante la extracción JS: {e}", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        await browser.close()

    if not data:
        print("Error: No se obtuvieron datos.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracción completada: {len(data)} registros obtenidos.")

    OUTPUT_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"Guardado en: {OUTPUT_FILE}")
    return len(data)


def main():
    count = asyncio.run(scrape())
    print(f"Proceso finalizado. {count} registros guardados.")


if __name__ == "__main__":
    main()