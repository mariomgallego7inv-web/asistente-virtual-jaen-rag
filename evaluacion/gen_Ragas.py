# Evalua la generación de la respuesta (Relevancia y Fidelidad) usando Helmholtz Cloud

import json
import os
import asyncio 
import functools
import time

from openai import AsyncOpenAI 
from ragas.llms import llm_factory
from ragas.embeddings import HuggingFaceEmbeddings
from ragas.metrics.collections import AnswerRelevancy, Faithfulness

# ==========================================
# 1. CONFIGURACIÓN DE RUTAS LOCALES (WINDOWS)
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
ARCHIVO_ENTRADA = os.path.join(PROJECT_ROOT, "data", "dataset_generado_multimodelo.json")
ARCHIVO_SALIDA = os.path.join(PROJECT_ROOT, "results", "metricas_generadores.json")

# ==========================================
# 2. CONFIGURACIÓN DEL JUEZ (SERVIDOR HELMHOLTZ CLOUD)
# ==========================================
# Elegimos el modelo de 35B: Muy inteligente para ser juez, pero rápido al estar en la nube
NOMBRE_MODELO_JUEZ = "08 - Qwen3.6-35B-A3B-FP8 - Multimodal model from Apr 2026"

print(f"⏳ [CONFIGURACIÓN] Preparando Juez Evaluador: {NOMBRE_MODELO_JUEZ}...")

cliente = AsyncOpenAI(
    api_key="glpat-5oQKIZjGEEkgjU5ztez7CG86MQp1OnA3aQk.01.0z14ona1d", 
    base_url="https://api.helmholtz-blablador.fz-juelich.de/v1",
    timeout=180.0
)

# ── Monkey-patch: aumenta max_tokens para que Qwen pueda terminar el thinking ──
_original_create = cliente.chat.completions.create

@functools.wraps(_original_create)
async def _patched_create(*args, **kwargs):
    # Qwen gasta tokens en razonar antes del JSON → necesita más margen
    kwargs["max_tokens"] = 8192
    return await _original_create(*args, **kwargs)

cliente.chat.completions.create = _patched_create
# ────────────────────────────────────────────────────────────────────────────────

ragas_llm = llm_factory(model=NOMBRE_MODELO_JUEZ, client=cliente)

# ==========================================
# 3. INICIALIZAR MÉTRICAS Y EMBEDDINGS
# ==========================================
print("\n⏳ [LOCAL] Paso 1: Cargando modelo de Embeddings en tu PC...")

ragas_embeddings = HuggingFaceEmbeddings(model="dariolopez/bge-m3-es-legal-tmp-6")

print("✅ [LOCAL] Embeddings cargados correctamente en RAM.")

print("⏳ [LOCAL] Paso 2: Inicializando métricas de Ragas...")
evaluador_relevancia = AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings)
evaluador_fidelidad = Faithfulness(llm=ragas_llm)
print("✅ [LOCAL] Métricas listas. Arrancando motor de evaluación...")

# ==========================================
# 4. MOTOR DE EVALUACIÓN ASÍNCRONO
# ==========================================
async def evaluar_respuestas():
    with open(ARCHIVO_ENTRADA, 'r', encoding='utf-8') as f:
        dataset_generado = json.load(f)
        
    dataset_evaluado = []
    empezar_desde = 0
    
    # Reanudar si ya hay evaluaciones
    if os.path.exists(ARCHIVO_SALIDA):
        with open(ARCHIVO_SALIDA, 'r', encoding='utf-8') as f:
            dataset_evaluado = json.load(f)
        empezar_desde = len(dataset_evaluado)
        print(f"\n🔄 Reanudando evaluación desde la pregunta {empezar_desde + 1}...")

    print(f"\n🚀 Iniciando Evaluación Oficial en Helmholtz Cloud...\n")
    print("-" * 50)
    
    for i, item in enumerate(dataset_generado[empezar_desde:], start=empezar_desde):
        id_preg = item.get("id_pregunta")
        pregunta = item.get("pregunta", "")
        documentos = item.get("documentos_recuperados_faiss", [])
        respuestas_modelos = item.get("respuestas_generadas", {})
        
        print(f"\n[{i + 1}/{len(dataset_generado)}] Pregunta ID {id_preg}")
        
        resultados_pregunta = {
            "id_pregunta": id_preg,
            "pregunta": pregunta,
            "evaluacion_modelos": {}
        }
        
        for nombre_modelo, respuesta_texto in respuestas_modelos.items():
            print(f"   👉 Auditando a: {nombre_modelo}")
            
            try:
                # RELEVANCIA
                print(f"      📡 [HELMHOLTZ] Calculando Relevancia...")
                res_relevancia = await evaluador_relevancia.ascore(
                    user_input=pregunta,
                    response=respuesta_texto
                )
                time.sleep(1)
                relevancia_score = res_relevancia.value if hasattr(res_relevancia, 'value') else float(res_relevancia)
                print(f"      📥 [HELMHOLTZ] Recibido -> Rel: {relevancia_score:.4f}")
                
                # FIDELIDAD
                print(f"      📡 [HELMHOLTZ] Calculando Fidelidad (leyendo contextos)...")
                res_fidelidad = await evaluador_fidelidad.ascore(
                    user_input=pregunta,
                    response=respuesta_texto,
                    retrieved_contexts=documentos
                )
                fidelidad_score = res_fidelidad.value if hasattr(res_fidelidad, 'value') else float(res_fidelidad)
                print(f"      📥 [HELMHOLTZ] Recibido -> Fid: {fidelidad_score:.4f}")

                time.sleep(1)
                
            except Exception as e:
                print(f"      🚨 [ERROR HELMHOLTZ]: {e}")
                relevancia_score = "ERROR"
                fidelidad_score = "ERROR"
            
            resultados_pregunta["evaluacion_modelos"][nombre_modelo] = {
                "respuesta_generada": respuesta_texto,
                "Answer_Relevancy": relevancia_score,
                "Faithfulness": fidelidad_score
            }
        
        dataset_evaluado.append(resultados_pregunta)
        
        # Guardado físico en tu disco duro tras cada pregunta
        with open(ARCHIVO_SALIDA, 'w', encoding='utf-8') as f:
            json.dump(dataset_evaluado, f, indent=4, ensure_ascii=False)
            
        print("-" * 50)

    print(f"\n🎉 ¡Evaluación completada con éxito conectando con Alemania!")

# ==========================================
# 5. DISPARADOR DE EJECUCIÓN PARA WINDOWS
# ==========================================
if __name__ == "__main__":
    # Esto es vital para ejecutar asyncio fuera de Colab/Jupyter
    asyncio.run(evaluar_respuestas())