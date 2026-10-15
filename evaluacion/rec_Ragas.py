import json
import time
import torch
import os 
from openai import AsyncOpenAI

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from ragas.llms import llm_factory
from ragas.metrics.collections import ContextPrecision, ContextRecall

# ==========================================
# 1. CONFIGURACIÓN DE LOS CLIENTES OPENAI ASÍNCRONOS
# ==========================================
print("⏳ Conectando con los servidores...")

BASE_URL_ADA = "http://ada01.ujaen.es:8080/v1"
API_KEY_ADA = "5e50191a63bd60fc4eb9f534143fa2eca8887bc79a2a53d7e950f39c5dc9487ecbd801a56637c3e3a2f79d98d5e05119803981476b1121841d0f94a3a72a5379"
cliente_ada = AsyncOpenAI(api_key=API_KEY_ADA, base_url=BASE_URL_ADA, timeout=300.0)

BASE_URL_ALEMAN = "https://api.helmholtz-blablador.fz-juelich.de/v1"
API_KEY_ALEMAN = "glpat-LR4u37GYb4Ucvd1PqG_lHG86MQp1OnA3aQk.01.0z0min5ze"
cliente_aleman = AsyncOpenAI(api_key=API_KEY_ALEMAN, base_url=BASE_URL_ALEMAN, timeout=120.0)

# ==========================================
# 2. CONFIGURACIÓN DE LOS JUECES CON LLM_FACTORY
# ==========================================
print("⏳ Configurando los jueces oficiales de Ragas...")

K_DOCS = 5  

llm_gemma = llm_factory(model="/mnt/beegfs/sinai-data/google/gemma-3-12b-it", client=cliente_ada)


juez_ragas = {
    "Gemma": {"precision": ContextPrecision(llm=llm_gemma), "recall": ContextRecall(llm=llm_gemma)}

}

# ==========================================
# 3. CONFIGURACIÓN DEL RAG (FAISS)
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DATASET_PATH = os.path.join(PROJECT_ROOT, "data", "dataset_evaluacion.json")
RUTA_CARPETA_FAISS = os.path.join(PROJECT_ROOT, "faiss_index_final")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
MODELO_EMBEDDINGS = "dariolopez/bge-m3-es-legal-tmp-6"

print("⏳ Cargando Base de Datos Vectorial...")
device = 'cuda' if torch.cuda.is_available() else 'cpu'
embeddings = HuggingFaceEmbeddings(model_name=MODELO_EMBEDDINGS, model_kwargs={'device': device}, encode_kwargs={'normalize_embeddings': True})
vectorstore = FAISS.load_local(folder_path=RUTA_CARPETA_FAISS, embeddings=embeddings, allow_dangerous_deserialization=True)

# ==========================================
# 4. SISTEMA DE GUARDADO PROGRESIVO Y REANUDACIÓN
# ==========================================
def evaluar():
    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        dataset_completo = json.load(f)

    nombre_archivo = os.path.join(RESULTS_DIR, "metricas_recuperador.json") if os.path.exists(os.path.join(RESULTS_DIR, "metricas_recuperador.json")) else os.path.join(RESULTS_DIR, f"resumen_ragas_avanzado_Top{K_DOCS}.json")
    
    # Valores por defecto si empezamos desde cero
    sumas = {
        "Gemma": {"p_score": 0.0, "r_score": 0.0, "p_ok": 0, "p_fallo": 0, "r_ok": 0, "r_fallo": 0}
    }
    historial_preguntas = []
    empezar_desde = 0

    # COMPROBAR SI HAY UNA PARTIDA GUARDADA
    if os.path.exists(nombre_archivo):
        print(f"\n🔄 ARCHIVO DE GUARDADO DETECTADO: '{nombre_archivo}'")
        try:
            with open(nombre_archivo, 'r', encoding='utf-8') as f:
                datos_previos = json.load(f)
                
            empezar_desde = datos_previos.get("preguntas_evaluadas_hasta_ahora", 0)
            sumas = datos_previos.get("estado_interno_sumas", sumas)
            historial_preguntas = datos_previos.get("historial_pregunta_a_pregunta", [])
            print(f"▶️ Reanudando la evaluación desde la pregunta {empezar_desde + 1} de {len(dataset_completo)}...")
        except Exception as e:
            print("⚠️ El archivo de guardado está corrupto. Empezando desde cero...")
            empezar_desde = 0

    print("\n" + "=" * 50)
    
    # El bucle ahora empieza desde donde se quedó (start=empezar_desde)
    for i, item in enumerate(dataset_completo[empezar_desde:], start=empezar_desde): 
        pregunta = item.get("pregunta", "")
        respuesta_esperada = item.get("respuesta", "")
        
        print(f"\n📝 [{i+1}/{len(dataset_completo)}] Evaluando: {pregunta[:60]}...")
        
        resultados = vectorstore.similarity_search(pregunta, k=K_DOCS)
        lista_textos_docs = [doc.page_content for doc in resultados]
        
        # Diccionario para guardar lo que pasa en ESTA pregunta específica
        registro_actual = {
            "id_pregunta": i + 1,
            "pregunta": pregunta,
            "votos": {}
        }
        
        for nombre, metricas in juez_ragas.items():
            if nombre == "Alemán":
                time.sleep(1.5)

            p_final, r_final = 0.0, 0.0
            error_p, error_r = False, False
            
            # --- EVALUAMOS PRECISION ---
            try:
                p_score_raw = metricas["precision"].score(
                    user_input=pregunta, reference=respuesta_esperada, retrieved_contexts=lista_textos_docs
                )
                p_final = float(p_score_raw) if p_score_raw is not None else 0.0
                sumas[nombre]["p_score"] += p_final
                sumas[nombre]["p_ok"] += 1
            except Exception as e:
                print(f"      🚨 {nombre} falló el formato en Precision.")
                sumas[nombre]["p_fallo"] += 1
                error_p = True
                
            # --- EVALUAMOS RECALL ---
            try:
                r_score_raw = metricas["recall"].score(
                    user_input=pregunta, reference=respuesta_esperada, retrieved_contexts=lista_textos_docs
                )
                r_final = float(r_score_raw) if r_score_raw is not None else 0.0
                sumas[nombre]["r_score"] += r_final
                sumas[nombre]["r_ok"] += 1
            except Exception as e:
                print(f"      🚨 {nombre} falló el formato en Recall.")
                sumas[nombre]["r_fallo"] += 1
                error_r = True
            
            print(f"   🤖 [{nombre}] Precision@{K_DOCS}: {p_final:.2f} | Recall: {r_final:.2f}")
            
            # Guardamos los resultados individuales de este modelo en esta pregunta
            registro_actual["votos"][nombre] = {
                "Precision": p_final if not error_p else "ERROR_FORMATO",
                "Recall": r_final if not error_r else "ERROR_FORMATO"
            }
            
        # Añadimos la pregunta al historial
        historial_preguntas.append(registro_actual)
        preguntas_totales_evaluadas = i + 1

        # ==========================================
        # GUARDADO PROGRESIVO (Se ejecuta en cada vuelta del bucle)
        # ==========================================
        reporte_progresivo = {
            "configuracion": f"Top-{K_DOCS} Oficial Ragas",
            "preguntas_evaluadas_hasta_ahora": preguntas_totales_evaluadas,
            "total_preguntas_dataset": len(dataset_completo),
            "estado_interno_sumas": sumas, 
            "resultados_globales_por_modelo": {},
            "historial_pregunta_a_pregunta": historial_preguntas
        }

        for nombre in juez_ragas.keys():
            datos = sumas[nombre]
            
            # 1. Media Real (Lo inteligente que es cuando no falla)
            media_p_real = (datos["p_score"] / datos["p_ok"] * 100) if datos["p_ok"] > 0 else 0.0
            media_r_real = (datos["r_score"] / datos["r_ok"] * 100) if datos["r_ok"] > 0 else 0.0
            
            # 2. NUEVO: Media Estricta con Fallos (Rendimiento global penalizando errores de formato)
            media_p_con_fallos = (datos["p_score"] / preguntas_totales_evaluadas) * 100
            media_r_con_fallos = (datos["r_score"] / preguntas_totales_evaluadas) * 100
            
            # Tasas de fallo
            tasa_fallo_p = (datos["p_fallo"] / preguntas_totales_evaluadas) * 100
            tasa_fallo_r = (datos["r_fallo"] / preguntas_totales_evaluadas) * 100
            
            reporte_progresivo["resultados_globales_por_modelo"][nombre] = {
                "Context_Precision": {
                    "Nota_Media_Real_Sin_Fallos": f"{media_p_real:.2f}%",
                    "Nota_Media_Estricta_Con_Fallos": f"{media_p_con_fallos:.2f}%",
                    "Aciertos_Formato": datos["p_ok"],
                    "Errores_Formato": datos["p_fallo"],
                    "Tasa_Fallo": f"{tasa_fallo_p:.2f}%"
                },
                "Context_Recall": {
                    "Nota_Media_Real_Sin_Fallos": f"{media_r_real:.2f}%",
                    "Nota_Media_Estricta_Con_Fallos": f"{media_r_con_fallos:.2f}%",
                    "Aciertos_Formato": datos["r_ok"],
                    "Errores_Formato": datos["r_fallo"],
                    "Tasa_Fallo": f"{tasa_fallo_r:.2f}%"
                }
            }

        # Sobreescribimos el archivo con los nuevos datos actualizados
        with open(nombre_archivo, 'w', encoding='utf-8') as f:
            json.dump(reporte_progresivo, f, indent=4, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("✅ ¡EVALUACIÓN COMPLETADA AL 100%! 🎉")
    print(f"💾 Todos los datos y el historial están guardados en '{nombre_archivo}'")

if __name__ == "__main__":
    evaluar()