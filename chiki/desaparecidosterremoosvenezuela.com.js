(async () => {
  console.log("Iniciando extracción de datos...");
  const RECAPTCHA_KEY = "6LeBfDUtAAAAAMw1Wtkd58bst6vEnLOi3_NAjGD0";
  const BASE_API = "https://desaparecidos-terremoto-api.theempire.tech/api";
  
  // Función para pedirle un token de reCAPTCHA v3 al navegador
  async function getRecaptchaToken(action) {
    return new Promise((resolve) => {
      window.grecaptcha.ready(() => {
        window.grecaptcha.execute(RECAPTCHA_KEY, { action }).then(resolve);
      });
    });
  }

  let page = 1;
  const pageSize = 50; // Extraemos de 50 en 50 para rapidez
  let allPeople = [];
  
  try {
    while (true) {
      console.log(`Descargando página ${page}...`);
      const token = await getRecaptchaToken("list_people");
      
      const res = await fetch(`${BASE_API}/personas?page=${page}&pageSize=${pageSize}`, {
        headers: {
          "Content-Type": "application/json",
          "x-recaptcha-token": token
        }
      });
      
      if (!res.ok) {
        throw new Error(`Error en API: ${res.status}`);
      }
      
      const data = await res.json();
      const items = data.items || [];
      allPeople = allPeople.concat(items);
      
      console.log(`Página ${page} completada. Total acumulado: ${allPeople.length}`);
      
      if (page >= (data.totalPages || 1) || items.length === 0) {
        break;
      }
      page++;
      // Pequeña espera para no saturar el backend
      await new Promise(r => setTimeout(r, 300));
    }
    
    console.log(`¡Extracción completada! Se obtuvieron ${allPeople.length} registros.`);
    
    // Descargar el archivo JSON directamente en el navegador del usuario
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(allPeople, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", "personas_desaparecidas_venezuela.json");
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    
  } catch (error) {
    console.error("Ocurrió un error al extraer los datos:", error);
  }
})();