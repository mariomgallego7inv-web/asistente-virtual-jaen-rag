import os
# Con este código compruebo que documentos se obtienen con faiss donde la precisión es 0
# Este obtiene "Análisis manual gemma.txt" lo que pasa que despues lo ponemos "bonito" en "Tipo de errores.txt"

import json
import re
import torch

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

# ==========================================
# 1. CONFIGURACIÓN (SOLO FAISS, SIN IA)
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DATASET_PATH = os.path.join(PROJECT_ROOT, "data", "dataset_evaluacion.json")
RUTA_CARPETA_FAISS = os.path.join(PROJECT_ROOT, "faiss_index_final")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
RUTA_RESUMEN_TOP3 = os.path.join(RESULTS_DIR, "metricas_recuperador.json") if os.path.exists(os.path.join(RESULTS_DIR, "metricas_recuperador.json")) else os.path.join(RESULTS_DIR, "resumen_ragas_avanzado_Top3.json")
MODELO_EMBEDDINGS = "dariolopez/bge-m3-es-legal-tmp-6"
K_DOCS = 3 

print("⏳ Cargando Motor de Búsqueda (FAISS)...")
device = 'cuda' if torch.cuda.is_available() else 'cpu'
embeddings = HuggingFaceEmbeddings(model_name=MODELO_EMBEDDINGS, model_kwargs={'device': device})
vectorstore = FAISS.load_local(folder_path=RUTA_CARPETA_FAISS, embeddings=embeddings, allow_dangerous_deserialization=True)

# ==========================================
# 2. GENERACIÓN DEL INFORME
# ==========================================
def auditar_documentos_cero():
    # 1. Leemos el archivo donde están las notas para sacar los IDs con 0.0
    with open(RUTA_RESUMEN_TOP3, 'r', encoding='utf-8') as f:
        datos_resultados = json.load(f)
    
    ids_con_cero = []
    for item in datos_resultados.get("historial_pregunta_a_pregunta", []):
        if item.get("votos", {}).get("Gemma", {}).get("Precision") == 0.0:
            ids_con_cero.append(item["id_pregunta"])
            
    print(f"🎯 Se han encontrado {len(ids_con_cero)} preguntas con Precisión 0.0.")

    # 2. Leemos el dataset original
    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        dataset_completo = json.load(f)
        
    informe_final = []
    
    print("\n🚀 Recuperando documentos fallidos...")
    
    # 3. Filtramos y buscamos
    for idx, item in enumerate(dataset_completo):
        id_real = idx + 1
        if id_real in ids_con_cero:
            pregunta = item.get("pregunta", "")
            respuesta_esperada = item.get("respuesta", "")
            pasaje = item.get("pasaje", "")
            
            # Extraer Trámite
            match_tramite = re.search(r"Trámite:\s*([^\n]+)", pasaje, re.IGNORECASE)
            expected_tramite = match_tramite.group(1).strip() if match_tramite else "DESCONOCIDO"
            
            # Extraer Campo
            lineas = pasaje.split("\n")
            expected_campo = lineas[1].split(":")[0].strip() if len(lineas) > 1 else "DESCONOCIDO"

            # Recuperar los 3 documentos exactos que devolvió FAISS
            resultados = vectorstore.similarity_search(pregunta, k=K_DOCS)
            lista_textos_docs = [doc.page_content for doc in resultados]
            
            # Guardar en la estructura final
            informe_final.append({
                "id_pregunta": id_real,
                "pregunta_ciudadano": pregunta,
                "respuesta_esperada_ground_truth": respuesta_esperada,
                "tramite_esperado": expected_tramite,
                "campo_esperado": expected_campo,
                "documentos_recuperados_faiss": lista_textos_docs
            })
            
    # 4. Volcar todo a un JSON limpio
    nombre_archivo = os.path.join(RESULTS_DIR, "informe_documentos_fallidos_K3.json")
    with open(nombre_archivo, 'w', encoding='utf-8') as f:
        json.dump(informe_final, f, indent=4, ensure_ascii=False)

    print(f"\n✅ ¡Listo! El archivo '{nombre_archivo}' se ha generado correctamente.")

if __name__ == "__main__":
    auditar_documentos_cero()