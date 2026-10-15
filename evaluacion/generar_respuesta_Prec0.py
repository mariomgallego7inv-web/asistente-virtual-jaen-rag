# Este script es para hacer la generación de las respuesta cuando se recueran 3 documentos.
# ha diferencia del generación_multimodelo, este toma el archivo
# informe_documentos_fallidos_k3.json para que genere la respuesta solo de esos, que son los que tienen la precision 0 en gemma

# C:\Users\mario\Desktop\trabajoCodigo - copia\dataset_generado_multimodelo.json

import json
import torch
import os
import time
from openai import OpenAI
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

# ==========================================
# 1. CONFIGURACIÓN DE RUTAS (FAISS)
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
RUTA_FALLIDOS = os.path.join(RESULTS_DIR, "informe_documentos_fallidos_K3.json")
RUTA_CARPETA_FAISS = os.path.join(PROJECT_ROOT, "faiss_index_final")
MODELO_EMBEDDINGS = "dariolopez/bge-m3-es-legal-tmp-6"
ARCHIVO_SALIDA = os.path.join(RESULTS_DIR, "respuestas_sin_contexto_prec0.json")
K_DOCS = 3 

# ==========================================
# 2. CONFIGURACIÓN MULTI-NUBE (UJA + ALEMANIA)
# ==========================================
print("⏳ Conectando con los servidores (UJA y Alemania)...")

# CLIENTE 1: SERVIDOR ADA (UJA)
BASE_URL_ADA = "http://ada01.ujaen.es:8080/v1"
API_KEY_ADA = "5e50191a63bd60fc4eb9f534143fa2eca8887bc79a2a53d7e950f39c5dc9487ecbd801a56637c3e3a2f79d98d5e05119803981476b1121841d0f94a3a72a5379"
cliente_ada = OpenAI(api_key=API_KEY_ADA, base_url=BASE_URL_ADA, timeout=150.0)

# CLIENTE 2: SERVIDOR ALEMÁN
BASE_URL_ALEMAN = "https://api.helmholtz-blablador.fz-juelich.de/v1"
API_KEY_ALEMAN = "glpat-1rPKfrhog9o_zA4RoHq9aW86MQp1OnA3aQk.01.0z0q23tyk"
cliente_aleman = OpenAI(api_key=API_KEY_ALEMAN, base_url=BASE_URL_ALEMAN, timeout=150.0)

# LISTA INTELIGENTE DE MODELOS
MODELOS_A_EVALUAR = [
    {"nombre": "/mnt/beegfs/sinai-data/meta-llama/Llama-3.1-8B-Instruct", "cliente": cliente_ada, "alias": "Llama-3.1 (UJA)"},
    {"nombre": "Salamandra-7B-It-legal-BSC", "cliente": cliente_ada, "alias": "Salamandra (UJA)"},
    {"nombre": "alias-apertus", "cliente": cliente_aleman, "alias": "Apertus (Alemania)"}
]

# ==========================================
# 3. CARGAR EL BUSCADOR (FAISS)
# ==========================================
print("⏳ Cargando el Motor de Búsqueda Vectorial...")
device = 'cuda' if torch.cuda.is_available() else 'cpu'
embeddings = HuggingFaceEmbeddings(model_name=MODELO_EMBEDDINGS, model_kwargs={'device': device})
vectorstore = FAISS.load_local(folder_path=RUTA_CARPETA_FAISS, embeddings=embeddings, allow_dangerous_deserialization=True)

# ==========================================
# 4. DISEÑO DEL PROMPT
# ==========================================
def construir_prompt(pregunta, documentos):
    contexto_unido = "\n\n---\n\n".join(documentos)
    prompt = f"""Eres un asistente virtual experto del Ayuntamiento de Jaén. 
Tu objetivo es responder a las preguntas de los ciudadanos basándote ÚNICAMENTE en la información proporcionada en el "Contexto Oficial".

Reglas estrictas:
1. Responde de forma clara, concisa, directa y educada en perfecto español.
2. Si la información para responder a la pregunta NO está en el contexto, di textualmente: "Lo siento, no dispongo de información suficiente en los documentos oficiales para responder a esta consulta." No inventes nada.
3. Si el contexto menciona plazos, órganos gestores o documentos a presentar, inclúyelos en tu respuesta.

Contexto Oficial Recuperado:
{contexto_unido}

Pregunta del ciudadano: {pregunta}

Escribe tu respuesta a continuación:"""
    return prompt

# ==========================================
# 5. MOTOR DE GENERACIÓN MULTIMODELO
# ==========================================
def generar_respuestas():
    # 1. Cargar DIRECTAMENTE el archivo de fallidos
    if not os.path.exists(RUTA_FALLIDOS):
        print(f"❌ ERROR: No se encuentra el archivo en {RUTA_FALLIDOS}")
        return

    with open(RUTA_FALLIDOS, 'r', encoding='utf-8') as f:
        dataset_fallidos = json.load(f)

    print(f"📄 Se cargaron {len(dataset_fallidos)} preguntas directamente del archivo de fallidos.")

    dataset_generado = []
    empezar_desde = 0
    
    # 2. Controlar si ya existe el archivo de salida para reanudar
    if os.path.exists(ARCHIVO_SALIDA):
        with open(ARCHIVO_SALIDA, 'r', encoding='utf-8') as f:
            dataset_generado = json.load(f)
        empezar_desde = len(dataset_generado)
        print(f"🔄 Reanudando desde la pregunta {empezar_desde + 1}...")

    print("\n🚀 Iniciando Generación de Respuestas...\n")
    
    # 3. Bucle sobre las preguntas del archivo de fallidos
    for i, item in enumerate(dataset_fallidos[empezar_desde:], start=empezar_desde):
        # Extraemos las claves exactas de tu archivo informe_documentos_fallidos_K3.json
        id_real = item.get("id_pregunta", i + 1)
        pregunta = item.get("pregunta_ciudadano", "")
        respuesta_esperada = item.get("respuesta_esperada_ground_truth", "")
        
        print(f"[{i+1}/{len(dataset_fallidos)}] Procesando ID {id_real}: {pregunta[:50]}...")
        
        resultados = vectorstore.similarity_search(pregunta, k=K_DOCS)
        lista_textos_docs = [doc.page_content for doc in resultados]
        prompt_final = construir_prompt(pregunta, lista_textos_docs)
        
        respuestas_modelos = {}
        
        for config_modelo in MODELOS_A_EVALUAR:
            nombre_modelo = config_modelo["nombre"]
            cliente_actual = config_modelo["cliente"]
            alias_bonito = config_modelo["alias"]
            
            try:
                respuesta_api = cliente_actual.chat.completions.create(
                    model=nombre_modelo,
                    messages=[{"role": "user", "content": prompt_final}],
                    temperature=0.1, 
                    max_tokens=600
                )
                texto_generado = respuesta_api.choices[0].message.content.strip()
            except Exception as e:
                print(f"  🚨 Error con {alias_bonito}: {e}")
                texto_generado = f"ERROR_DE_GENERACION: {e}"
                
            respuestas_modelos[alias_bonito] = texto_generado
            
            # ⏱️ PAUSA DE SEGURIDAD
            if cliente_actual == cliente_aleman:
                time.sleep(1.01)

        # Guardamos la estructura final
        nuevo_item = {
            "id_pregunta": id_real,
            "pregunta": pregunta,
            "respuesta_esperada_ground_truth": respuesta_esperada,
            "documentos_recuperados_faiss": lista_textos_docs,
            "respuestas_generadas": respuestas_modelos
        }
        
        dataset_generado.append(nuevo_item)
        
        # Guardado progresivo
        with open(ARCHIVO_SALIDA, 'w', encoding='utf-8') as f:
            json.dump(dataset_generado, f, indent=4, ensure_ascii=False)

    print(f"\n✅ ¡Generación completada! Los resultados están en '{ARCHIVO_SALIDA}'.")

if __name__ == "__main__":
    generar_respuestas()