#Este scrip obtiene las palabras de los titulos de cada fila de los trámites, para así separar los chunks por filas.
import requests
from bs4 import BeautifulSoup
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURACIÓN ---
URL_CATALOGO = "https://sede.aytojaen.es/sta/CarpetaPublic/doEvent?APP_CODE=STA&PAGE_CODE=CATALOGO"
URL_DETALLE = URL_CATALOGO + "&DETALLE={id}"

def obtener_ids_tramites():
    """Obtiene la lista de IDs de trámites usando Selenium (necesario por JavaScript)"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)
    
    ids = []
    try:
        driver.get(URL_CATALOGO)
        wait.until(EC.presence_of_element_located((By.ID, "CATSERV_LISTA")))
        
        # Seleccionar "Todos" en el desplegable para ver la lista completa
        sel = Select(driver.find_element(By.NAME, "CATSERV_LISTA_length"))
        sel.select_by_value("-1")
        time.sleep(2) # Espera a que cargue la tabla completa
        
        rows = driver.find_elements(By.CSS_SELECTOR, "table#CATSERV_LISTA tbody tr")
        for r in rows:
            tid = r.get_attribute("id")
            if tid:
                ids.append(tid.strip())
        return ids
    finally:
        driver.quit()

def extraer_campos_unicos(lista_ids):
    """Entra en cada trámite y extrae los textos de <dt class='entry-label'>"""
    campos_unicos = set() # El set evita duplicados automáticamente
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (TFG Student Scraper)"})

    total = len(lista_ids)
    print(f"🔍 Analizando campos en {total} trámites...")

    for i, tid in enumerate(lista_ids, 1):
        url = URL_DETALLE.format(id=tid)
        try:
            r = session.get(url, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Buscamos la sección específica señalada por el profesor
            seccion_principal = soup.find("dl", class_="seccion section large")
            
            if seccion_principal:
                # Buscamos todos los <dt> con la clase entry-label
                etiquetas = seccion_principal.find_all("dt", class_="entry-label")
                
                for etiqueta in etiquetas:
                    texto_campo = etiqueta.get_text(strip=True)
                    if texto_campo:
                        # Limpiar posibles dos puntos al final o espacios raros
                        texto_campo = texto_campo.rstrip(":")
                        campos_unicos.add(texto_campo)
            
            if i % 10 == 0:
                print(f"⏳ Procesados {i}/{total} trámites. Campos únicos encontrados: {len(campos_unicos)}")
            
            # Respeto al servidor
            time.sleep(random.uniform(0.5, 1.0))
            
        except Exception as e:
            print(f"❌ Error en trámite {tid}: {e}")

    return sorted(list(campos_unicos))

# --- EJECUCIÓN ---
if __name__ == "__main__":
    print("🚀 Iniciando extracción de estructura de campos...")
    
    lista_ids = obtener_ids_tramites()
    print(f"✅ Se han detectado {len(lista_ids)} trámites en el catálogo.")
    
    campos_finales = extraer_campos_unicos(lista_ids)
    
    print("\n" + "="*40)
    print(f"📋 LISTA DE CAMPOS DETECTADOS ({len(campos_finales)} totales):")
    print("="*40)
    for campo in campos_finales:
        print(f"- {campo}")
    
    # Guardar en un txt para tu análisis estadístico posterior
    with open("campos_tramites_jaen.txt", "w", encoding="utf-8") as f:
        for campo in campos_finales:
            f.write(campo + "\n")
    print("\n✅ Lista guardada en 'campos_tramites_jaen.txt'")