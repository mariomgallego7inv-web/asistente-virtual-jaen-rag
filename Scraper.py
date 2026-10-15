#Creo que es este
import os
import re
import time
import random
import csv
import unicodedata
from urllib.parse import urljoin
from io import BytesIO

import requests
import urllib3
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ----------------- CONEXIÓN A DRIVE -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.path.exists('/content/drive'):
    try:
        from google.colab import drive
        drive.mount('/content/drive')
        OUTPUT_DIR = "/content/drive/MyDrive/Tramites_Jaen_Final_Corregido"
    except Exception:
        OUTPUT_DIR = os.path.join(BASE_DIR, "data", "tramites_txt")
else:
    OUTPUT_DIR = os.path.join(BASE_DIR, "data", "tramites_txt")

os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_CATALOG_URL = "https://sede.aytojaen.es/sta/CarpetaPublic/doEvent?APP_CODE=STA&PAGE_CODE=CATALOGO"
DETALLE_URL = BASE_CATALOG_URL + "&DETALLE={id}"
INDEX_CSV = os.path.join(OUTPUT_DIR, "indice_tramites.csv")

TITULOS_VALIDOS = [
    "Descripción",
    "Documentos a Presentar",
    "Efecto del silencio Administrativo",
    "Finalidad",
    "Información Adicional",
    "Modelos de solicitud",
    "Nivel de identificación en trámitación online",
    "Normativa básica",
    "Organo Gestor",
    "Pago de tasas",
    "Plazo de resolución",
    "Plazos de Presentación",
    "Presentación",
    "Quien lo puede Presentar",
    "Recursos"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

SLEEP_BETWEEN_REQUESTS = (0.5, 1.0)
SLEEP_BETWEEN_TRAMITES = (0.8, 1.5)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ----------------- FUNCIONES -----------------

def get_colab_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    return driver

def limpiar_nombre(name):
    """Limpieza de nombre de archivo segura"""
    s = str(name).strip()
    s = s.replace("/", "-").replace("\\", "-")
    s = s.replace(":", " -")
    s = s.replace('"', '').replace("'", "")
    s = s.replace("*", "").replace("?", "").replace("<", "").replace(">", "").replace("|", "")
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    s = " ".join(s.split())
    s = s.rstrip(".")
    return s[:150]

def path_unica(base_name, id_tramite):
    clean_name = limpiar_nombre(base_name)
    if not clean_name:
        clean_name = f"Tramite_{id_tramite}"
    filename = f"{clean_name}.txt"
    full_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(full_path):
        filename = f"{clean_name} ({id_tramite}).txt"
        full_path = os.path.join(OUTPUT_DIR, filename)
    return full_path

def extraer_pdf(content):
    try:
        reader = PdfReader(BytesIO(content))
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        return text
    except:
        return "[PDF ilegible o protegido]"

def intentar_peticion(session, url):
    try:
        r = session.get(url, headers=HEADERS, timeout=15, stream=True, verify=False)
        if r.status_code in [404, 403, 500, 502] and url.startswith("http:"):
            url_segura = url.replace("http:", "https:")
            r = session.get(url_segura, headers=HEADERS, timeout=15, stream=True, verify=False)
        return r
    except Exception as e:
        if url.startswith("http:"):
            try:
                url_segura = url.replace("http:", "https:")
                r = session.get(url_segura, headers=HEADERS, timeout=15, stream=True, verify=False)
                return r
            except:
                return None
        return None

def descargar_recurso(session, url, base_url):
    full_url = url.strip()
    if not full_url.lower().startswith("http"):
        full_url = urljoin(base_url, full_url)

    if "javascript:" in full_url.lower() or full_url.endswith("#"):
        return "", "restricted"

    r = intentar_peticion(session, full_url)

    if r is None:
        return "", "error_conexion"

    if r.status_code != 200:
        return "", f"error_{r.status_code}"

    try:
        content_type = r.headers.get("Content-Type", "").lower()
        es_pdf = "application/pdf" in content_type or full_url.lower().endswith(".pdf")

        if es_pdf:
            return extraer_pdf(r.content), "pdf"
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            main = soup.find("main") or soup.find("body") or soup
            for script in main(["script", "style", "nav", "footer"]):
                script.decompose()
            texto = main.get_text(separator="\n", strip=True)
            return texto[:40000], "html"

    except Exception as e:
        return "", "error_procesado"

# ----------------- MAIN -----------------
def main():
    print("--- 1. OBTENIENDO LISTA DE TRÁMITES ---")
    driver = get_colab_driver()
    tramites = []

    try:
        driver.get(BASE_CATALOG_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "CATSERV_LISTA")))
        try:
            driver.execute_script("document.getElementsByName('CATSERV_LISTA_length')[0].value='-1';")
            driver.execute_script("document.getElementsByName('CATSERV_LISTA_length')[0].dispatchEvent(new Event('change'));")
            time.sleep(3)
        except: pass

        filas = driver.find_elements(By.CSS_SELECTOR, "#CATSERV_LISTA tbody tr")
        print(f"-> Filas detectadas: {len(filas)}")
        for f in filas:
            tid = f.get_attribute("id")
            cols = f.find_elements(By.TAG_NAME, "td")
            nombre = cols[0].text.strip() if cols else tid
            if tid: tramites.append((tid, nombre))
    finally:
        driver.quit()

    print(f"\n--- 2. PROCESANDO {len(tramites)} TRÁMITES ---")
    session = requests.Session()

    with open(INDEX_CSV, "w", newline="", encoding="utf-8") as f_csv:
        writer = csv.writer(f_csv)
        writer.writerow(["ID", "Nombre", "Archivo", "URL", "Estado"])

        for idx, (tid, nombre) in enumerate(tramites, start=1):
            print(f"[{idx}/{len(tramites)}] {nombre[:50]}...")

            url_detalle = DETALLE_URL.format(id=tid)
            contenido_txt = []
            status = "ok"

            contexto_tramite = (
                f"\nEste campo pertenece al tramite:\n"
                f"NOMBRE_TRAMITE: {nombre}\n"
                f"URL_ORIGEN: {url_detalle}\n"
            )

            try:
                r = session.get(url_detalle, headers=HEADERS, timeout=10, verify=False)
                soup = BeautifulSoup(r.text, "html.parser")

                dl = soup.find("dl")
                if not dl:
                    div = soup.find("main", id="contenedorWebapps")
                    if div: dl = div.find("dl")

                if dl:
                    dts = dl.find_all("dt")
                    for dt in dts:
                        clases = dt.get("class", [])
                        if "entry-label" not in clases: continue

                        titulo_campo = dt.get_text(strip=True).rstrip(":")
                        if titulo_campo not in TITULOS_VALIDOS: continue

                        dd = dt.find_next_sibling("dd")

                        if dd:
                            # 2.1 Limpieza
                            for svg in dd.find_all("svg"): svg.decompose()

                            # 2.2 Enlaces
                            lista_adjuntos_str = ""
                            links = dd.find_all("a", href=True)
                            for a in links:
                                link_text = a.get_text(strip=True)
                                url_destino = a['href']
                                for p in dd.find_all("p"):
                                    if a in p.descendants: continue
                                    if p.get_text(strip=True) == link_text: p.decompose()

                                c_res, tipo = descargar_recurso(session, url_destino, url_detalle)
                                if "error" not in tipo and "restricted" not in tipo and c_res.strip():
                                    c_indent = c_res.replace("\n", "\n    ")
                                    lista_adjuntos_str += (
                                        f"\n - [ENLACE/DOC] {link_text}\n"
                                        f"    >>> CONTENIDO ({tipo}):\n"
                                        f"    {c_indent}\n"
                                        f"    <<< FIN CONTENIDO\n"
                                    )
                                a.unwrap()
                                time.sleep(0.1)

                            # -------------------------------------------------------------
                            # 2.5 LISTAS FORMATEADAS (VERSIÓN CORREGIDA - SIN DUPLICADOS)
                            # -------------------------------------------------------------
                            # En lugar de buscar listas dentro de listas, buscamos directamente
                            # los elementos DT dentro del DD. Así solo los procesamos una vez.
                            for sub_dt in dd.find_all("dt"):
                                # Verificamos si ya le hemos puesto el guion (por seguridad)
                                if sub_dt.get_text(strip=True).startswith("-"):
                                    continue

                                # Si es un título de sección dentro de la lista (level0)
                                if "level0" in sub_dt.get("class", []):
                                    sub_dt.insert_after("|||TOKEN|||")
                                else:
                                    # Si es un item normal, ponemos guion y salto
                                    sub_dt.insert(0, " - ")
                                    sub_dt.insert_after("|||TOKEN|||")
                            # -------------------------------------------------------------

                            # 3. LOGICA DE TEXTO
                            etiquetas_bloque = ['p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'dt']
                            for bloque in dd.find_all(etiquetas_bloque):
                                if "|||TOKEN|||" not in str(bloque.next_sibling):
                                    bloque.insert_after("|||TOKEN|||")
                                if bloque.name == "br": bloque.decompose()

                            # 4. Extracción
                            texto_sucio = dd.get_text(separator=" ", strip=True)

                            # 5. Limpieza
                            texto_limpio = texto_sucio.replace("|||TOKEN|||", "\n")
                            texto_limpio = re.sub(r' +', ' ', texto_limpio)
                            texto_limpio = re.sub(r'\s+([:;,.])', r'\1', texto_limpio)
                            texto_limpio = re.sub(r'\n+', '\n', texto_limpio)

                            texto_acumulado = texto_limpio.strip()
                            if lista_adjuntos_str:
                                texto_acumulado += "\n" + lista_adjuntos_str

                            bloque = (
                                f"### {titulo_campo}:\n"
                                f"{texto_acumulado}\n"
                                f"{contexto_tramite}\n"
                            )
                            contenido_txt.append(bloque)
                else:
                    raw = soup.get_text(separator="\n", strip=True)
                    contenido_txt.append(f"### Contenido General:\n{raw}\n{contexto_tramite}\n")

            except Exception as e:
                contenido_txt.append(f"Error procesando: {e}")
                status = "error_contenido"

            path = path_unica(nombre, tid)

            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(contenido_txt))
            except OSError:
                print(f"⚠️ Nombre complejo '{os.path.basename(path)}', intentando simplificar...")
                nombre_simple = "".join(c for c in nombre if c.isalnum() or c in " .-_")
                nombre_simple = " ".join(nombre_simple.split())
                path_simple = path_unica(nombre_simple, tid)
                try:
                    with open(path_simple, "w", encoding="utf-8") as f:
                        f.write("\n".join(contenido_txt))
                    path = path_simple
                except:
                    print(f"❌ IMPOSIBLE GUARDAR: {nombre}")
                    status = "error_escritura"

            writer.writerow([tid, nombre, os.path.basename(path), url_detalle, status])
            time.sleep(random.uniform(*SLEEP_BETWEEN_TRAMITES))

    print(f"\n¡HECHO! Todo limpio y con un solo guion por elemento.")

if __name__ == "__main__":
    main()