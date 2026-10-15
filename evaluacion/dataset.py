# bloque 1 de Otorgamiento de la representación
import json
import os
import csv
import time
import shutil
import requests
import sys
import traceback

from langchain_core.prompts import PromptTemplate 
# NUEVO: Importamos ChatOllama para ejecución local
from langchain_ollama import ChatOllama
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.output_parsers import StrOutputParser

# Asumo que tienes este archivo localmente
from extraer_Pasajes import extraer_pasajes_estructurados

# --- CONFIGURACIÓN LOCAL ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIR_INDICE_PERSONAHUB = os.path.join(BASE_DIR, "faiss_personas_index")
DIR_TEMPORAL_SEGURA = os.path.join(os.path.expanduser("~"), "faiss_temp_read")
ARCHIVO_CSV = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "tramites_index2026.csv")) 
ARCHIVO_SALIDA = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "dataset_evaluacion.json"))

MODELO_EMBEDDING = "hiiamsid/sentence_similarity_spanish_es"

# NUEVO: Nombre del modelo que tienes en Ollama (ej: "llama3.1", "llama3", etc.)
MODELO_LLM_LOCAL = "llama3.1" 

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# --- LISTA LOCAL JAÉN ---
perfiles_usuario_jaen = [
    "Agricultor propietario de fincas de olivar en la provincia",
    "Presidente de una cofradía religiosa de la ciudad de Jaén",
    "Estudiante universitario de la Universidad de Jaén (UJA)",
    "Madre de familia numerosa residente en Jaén",
    "Dueño de un bar de hostelería en el centro de la ciudad",
    "Vecino residente en el casco histórico de Jaén",
    "Dueño de un perro de raza potencialmente peligrosa (PPP)",
    "Pareja joven residente en Jaén con planes de futuro",
    "Conductor habitual que circula por la ciudad",
    "Arquitecto colegiado realizando proyectos de obra",
    "Vendedor ambulante con licencia de puesto en mercadillo",
    "Persona jubilada mayor de 65 años",
    "Mujer trabajadora en banca de mediana edad",
    "Organizador de eventos deportivos y culturales locales",
    "Empresario local del sector servicios"
]

def limpiar_json_string(texto):
    try:
        texto = texto.replace("```json", "").replace("```", "")
        inicio = texto.find('{')
        fin = texto.rfind('}')
        if inicio == -1 or fin == -1: return None
        return json.loads(texto[inicio:fin+1])
    except: return None

def main():
    print(f"--> Directorio base: {BASE_DIR}")
    
    embeddings = HuggingFaceEmbeddings(model_name=MODELO_EMBEDDING)
    
    print(" 🤖 Inicializando modelos locales con Ollama...")
    
    llm_ciudadano = ChatOllama(
        model=MODELO_LLM_LOCAL,
        temperature=0.2,
    )

    llm_asistente = ChatOllama(
        model=MODELO_LLM_LOCAL, 
        temperature=0.0,
        format="json" 
    )

    vectorstore_personahub = None
    if os.path.exists(DIR_TEMPORAL_SEGURA): shutil.rmtree(DIR_TEMPORAL_SEGURA)
    try:
        shutil.copytree(DIR_INDICE_PERSONAHUB, DIR_TEMPORAL_SEGURA)
        vectorstore_personahub = FAISS.load_local(DIR_TEMPORAL_SEGURA, embeddings, allow_dangerous_deserialization=True)
        print("   ✅ PersonaHub cargado.")
    except: print("   ⚠️ Error cargando PersonaHub. Se usará la Lista de Jaén.")

    vectorstore_jaen = FAISS.from_texts(perfiles_usuario_jaen, embeddings)
    print("   ✅ Lista Jaén cargada.")

    # NUEVO: Diccionario para guardar traducciones y no repetir trabajo LLM
    cache_traducciones = {}

    prompt_traductor = PromptTemplate(
        input_variables=["perfil_ingles"],
        template="""ADAPTA este perfil a JAÉN (España) y SIMPLIFÍCALO.
        PERFIL ORIGINAL: "{perfil_ingles}"
        INSTRUCCIONES: Traduce al español, elimina referencias extranjeras.
        SOLO EL TEXTO DEL PERFIL."""
    )

    # ... (TUS PROMPTS SE MANTIENEN IGUAL) ...
    prompt_ciudadano = PromptTemplate(
        input_variables=["pasaje", "persona", "nombre_tramite"],
        template="""
        ROL: Eres un ciudadano ({persona}) interesado en el trámite "{nombre_tramite}".
        TEXTO: "{pasaje}"
        
        TAREA: Haz UNA SOLA pregunta PRÁCTICA basada EXACTAMENTE en la información que ves en el texto. 
        Tu pregunta debe simular una consulta ciudadana real, buscando utilidad para resolver un problema o duda que tendrías en tu situación.
        
        Preguntas que no incluyan, "según el texto", "del texto", etc, ya que el ciudadano pregunta sin saber el texto.

        NUNCA inventes, solo información del texto.
        
        MAPA DE PREGUNTAS (Identifica de qué trata el texto y adáptalo a tu perfil):
        - Si es "Descripción" -> Pregunta en qué consiste de forma práctica este trámite para alguien en tu situación.
        - Si es "Finalidad" -> Pregunta para qué sirve o en qué casos específicos de tu día a día debes solicitarlo.
        - Si es "Documentos a Presentar" -> Pregunta qué papeles, anexos o documentación exacta tienes que ir preparando.
        - Si es "Efecto del silencio Administrativo" -> Pregunta con preocupación qué pasa con tu caso si el Ayuntamiento no te contesta a tiempo.
        - Si es "Información Adicional" -> Pregunta cómo funciona el proceso detalladamente para organizarte.
        - Si es "Modelos de solicitud" -> Pregunta si hay algún impreso oficial que debas descargar.
        - Si es "Nivel de identificación en trámitación online" -> Pregunta qué necesitas para entrar en la sede electrónica desde tu ordenador.
        - Si es "Normativa básica" -> Pregunta bajo qué ley o normativa se regula esto.
        - Si es "Organo Gestor" -> Pregunta a qué departamento del Ayuntamiento debes dirigirte.
        - Si es "Pago de tasas" -> Pregunta cuánto dinero te va a costar esta gestión.
        - Si es "Plazo de resolución" -> Pregunta cuánto tiempo máximo van a tardar en darte una respuesta definitiva.
        - Si es "Plazos de Presentación" -> Pregunta hasta qué día tienes de plazo para entregarlo.
        - Si es "Presentación" -> Pregunta dónde o por qué vías (presencial o sede electrónica) debes entregarlo.
        - Si es "Quien lo puede Presentar" -> Pregunta si tú, con tus características específicas, cumples los requisitos legales para iniciarlo.
        - Si es "Recursos" -> Pregunta cómo puedes reclamar si te dicen que no.
        
        SALIDA: Solo la pregunta redactada de forma natural y directa.
        """
    )

    prompt_asistente = PromptTemplate(
        input_variables=["pasaje", "pregunta", "persona", "nombre_tramite"],
        template="""
        ROL: Asistente Virtual del Ayuntamiento de Jaén. Eres amable, claro y profesional.
        INFORMACIÓN: "{pasaje}"
        PREGUNTA DEL CIUDADANO: "{pregunta}"
        
        TAREA: Responde a la pregunta de forma NATURAL y CONVERSACIONAL, como si estuvieras hablando con el ciudadano, pero basándote ÚNICA Y EXCLUSIVAMENTE en la INFORMACIÓN proporcionada.
        Tu respuesta debe ser clara, completa y formal, como si la diera la administración pública.
        
        REGLAS DE ORO ANTI-ALUCINACIÓN (CRÍTICA):
        1. NO hagas un "copia y pega" literal y robótico. Construye frases completas.
        2. NO te inventes ningún dato, plazo, precio o lugar que no esté en el texto.
        3. Si la respuesta a la pregunta no aparece literalmente en la INFORMACIÓN, tu respuesta DEBE ser EXACTAMENTE esta frase: "Esa información no está disponible en este apartado."
        
        SALIDA JSON:
        {{
            "contexto": "{persona}",
            "pregunta": "{pregunta}",
            "respuesta": "[Tu respuesta oficial, formal y basada 100% en el texto]"
        }}
        """
    )

    tripletas_totales = []
    
    if os.path.exists(ARCHIVO_SALIDA):
        try:
            with open(ARCHIVO_SALIDA, "r", encoding="utf-8") as f:
                tripletas_totales = json.load(f)
            print(f"   🔄 Se ha cargado un JSON anterior con {len(tripletas_totales)} registros. Se añadirán los nuevos.")
        except: pass

    with open(ARCHIVO_CSV, "r", encoding="utf-8-sig") as f:
        primera_linea = f.readline()
        f.seek(0)
        delimitador = ';' if ';' in primera_linea else ','
        reader = csv.DictReader(f, delimiter=delimitador)
        filas_csv = list(reader)

    print(f"--> Procesando {len(filas_csv)} trámites...")
    
    for i, row in enumerate(filas_csv[63:]): 
        row_limpio = {str(k).strip().lower(): str(v).strip() for k, v in row.items() if k}
        
        nombre = row_limpio.get("nombre", "Trámite") 
        url = row_limpio.get("url", "")

        if not url or "http" not in url: 
            continue

        print(f"\n🌐 [{i+1}/{len(filas_csv)}] {nombre}")
        
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            pasajes = extraer_pasajes_estructurados(resp.text, nombre)
            if not pasajes: continue

            print(f"Pasajes {len(pasajes)}")
            for idx_p, p in enumerate(pasajes):
                sys.stdout.write(f"      ⚡ Bloque {idx_p + 1}...")
                sys.stdout.flush() 
                
                docs_jaen = vectorstore_jaen.similarity_search_with_score(p, k=1)
                score_jaen = docs_jaen[0][1]
                
                score_hub = 999
                if vectorstore_personahub:
                    docs_hub = vectorstore_personahub.similarity_search_with_score(p, k=1)
                    score_hub = docs_hub[0][1]

                perfil_final = ""
                origen = ""

                if score_jaen < (score_hub + 0.05): 
                    perfil_final = docs_jaen[0][0].page_content
                    origen = "Lista Jaén"
                else:
                    if vectorstore_personahub:
                        perfil_ingles = docs_hub[0][0].page_content
                        # NUEVO: Comprobamos si ya hemos traducido este perfil
                        if perfil_ingles in cache_traducciones:
                            perfil_final = cache_traducciones[perfil_ingles]
                        else:
                            chain_trad = prompt_traductor | llm_ciudadano 
                            res_trad = chain_trad.invoke({"perfil_ingles": perfil_ingles})
                            perfil_final = res_trad.content.strip()
                            # Guardamos la traducción en memoria
                            cache_traducciones[perfil_ingles] = perfil_final
                        origen = "PersonaHub (Adaptado)"
                    else:
                        perfil_final = docs_jaen[0][0].page_content
                        origen = "Lista Jaén (Fallback)"

                intentos = 0
                while intentos < 2:
                    try:
                        p_clean = p.replace('"', "'").replace('\n', ' ')

                        chain_ciudadano = prompt_ciudadano | llm_ciudadano | StrOutputParser()
                        pregunta_generada = chain_ciudadano.invoke({"pasaje": p_clean, "persona": perfil_final, "nombre_tramite": nombre})
                        pregunta_generada = pregunta_generada.strip().replace('"', '')

                        chain_asistente = prompt_asistente | llm_asistente | StrOutputParser()
                        json_str = chain_asistente.invoke({"pasaje": p_clean, "pregunta": pregunta_generada, "persona": perfil_final, "nombre_tramite": nombre})
                        data = limpiar_json_string(json_str)

                        if data and data.get("respuesta"):
                            respuesta = data.get("respuesta")
                            es_correcta = (len(respuesta) > 10 and "no está disponible" not in respuesta.lower() and "no se encuentra" not in respuesta.lower())

                            if es_correcta:
                                item = {
                                    "pasaje": p,
                                    "contexto": perfil_final,
                                    "pregunta": pregunta_generada,
                                    "respuesta": respuesta,
                                    "origen_perfil": origen
                                }
                                tripletas_totales.append(item)
                                print(" ✅") 
                                break
                            else:
                                sys.stdout.write(" ♻️") 
                                sys.stdout.flush()
                        else:
                            sys.stdout.write(" ♻️") 
                            sys.stdout.flush()
                        
                        intentos += 1

                    except Exception as e:
                        print(f"\n      ❌ ERROR EN IA LOCAL: {e}")
                        break
                
                if intentos >= 2: print("") 

        except Exception as e:
            print(f"\n   ❌ ERROR FATAL EN TRÁMITE: {e}")
            traceback.print_exc()

        if tripletas_totales:
            with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
                json.dump(tripletas_totales, f, ensure_ascii=False, indent=4)

    print(f"\n🎉 PROCESO COMPLETADO Y GUARDADO: {ARCHIVO_SALIDA}")

if __name__ == "__main__":
    main()