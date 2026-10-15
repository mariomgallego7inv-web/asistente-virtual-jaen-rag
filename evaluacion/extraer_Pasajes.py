from bs4 import BeautifulSoup
import re

def extraer_pasajes_estructurados(html_content, nombre_tramite_fallback):
    """
    Extrae la información iterando por bloques <div class="section-entry">.
    Características:
    1. Formato natural: "Nombre del Campo: Contenido"
    2. FILTRO: Ignora explícitamente las filas con título "Descripción".
    """
    soup = BeautifulSoup(html_content, "html.parser")
    pasajes = []

    # 1. OBTENER NOMBRE EXACTO DEL TRÁMITE
    div_titulo = soup.find("div", class_="detail-title large")
    if div_titulo:
        nombre_oficial = div_titulo.get_text(strip=True)
    else:
        nombre_oficial = nombre_tramite_fallback

    # 2. LOCALIZAR LA TABLA DE DATOS
    lista_datos = soup.find("dl", class_="seccion section large")

    if not lista_datos:
        return []

    # 3. ITERAR POR CADA FILA
    filas = lista_datos.find_all("div", class_="section-entry")

    for fila in filas:
        dt = fila.find("dt")
        dd = fila.find("dd")
        
        if dt and dd:
            # Nombre del campo (ej: "Plazos")
            nombre_campo = dt.get_text(strip=True).replace(":", "")
            
            # --- FILTRO DE EXCLUSIÓN ---
            # Si el título contiene "Descripción", pasamos al siguiente sin guardar nada
            if "descripci" in nombre_campo.lower():
                continue
            
            # Contenido
            contenido_completo = dd.get_text(separator="\n", strip=True)
            contenido_limpio = re.sub(r'\n+', '\n', contenido_completo).strip()
            
            if len(contenido_limpio) > 2:
                # --- FORMATO NATURAL ---
                # Ejemplo: "Trámite: X \n Plazos de presentación: 01/01/2025..."
                chunk = f"Trámite: {nombre_oficial}\n{nombre_campo}: {contenido_limpio}"
                pasajes.append(chunk)

    return pasajes