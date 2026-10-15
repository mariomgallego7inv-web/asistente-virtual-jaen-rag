import json
import asyncio
import httpx
import os
import shutil
import functools  # Añadido para el monkey-patch
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.embeddings import HuggingFaceEmbeddings
from ragas.metrics.collections import Faithfulness, AnswerRelevancy

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
ARCHIVO_ORIGINAL = os.path.join(PROJECT_ROOT, "results", "metricas_generadores.json")
ARCHIVO_CONTEXTOS = os.path.join(PROJECT_ROOT, "data", "dataset_generado_multimodelo.json")

TOKEN_HELMHOLTZ = "glpat-rz7Ib1qkwxeDC2czD9d2BG86MQp1OnA3aQk.01.0z0jpk46r"

async def rescatar_y_actualizar():
    print("🚀 Iniciando actualización del archivo original...")

    # 1. Preparar el cliente con el parche SSL (verify=False)
    cliente_inseguro = httpx.AsyncClient(verify=False)
    cliente = AsyncOpenAI(
        api_key=TOKEN_HELMHOLTZ,
        base_url="https://api.helmholtz-blablador.fz-juelich.de/v1",
        timeout=600.0,
        http_client=cliente_inseguro
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

    # 2. Inicializar Juez y Embeddings
    print("⏳ Cargando modelos de evaluación...")
    juez_llm = llm_factory("08 - Qwen3.6-35B-A3B-FP8 - Multimodal model from Apr 2026", client=cliente)
    embeddings_legales = HuggingFaceEmbeddings(model="dariolopez/bge-m3-es-legal-tmp-6")
    
    metrica_fidelidad = Faithfulness(llm=juez_llm)
    metrica_relevancia = AnswerRelevancy(llm=juez_llm, embeddings=embeddings_legales)

    # 3. Cargar ambos JSON
    try:
        with open(ARCHIVO_ORIGINAL, "r", encoding="utf-8") as f:
            datos_evaluacion = json.load(f)
            
        with open(ARCHIVO_CONTEXTOS, "r", encoding="utf-8") as f:
            datos_contextos = json.load(f)
    except FileNotFoundError as e:
        print(f"🚨 Error: No se encontró uno de los archivos: {e}")
        return

    # 4. Mapa de contextos por ID de pregunta
    mapa_contextos = {item.get("id_pregunta"): item.get("documentos_recuperados_faiss", []) for item in datos_contextos if "id_pregunta" in item}

    # ==========================================
    # PASADA PREVIA PARA CONTAR ERRORES
    # ==========================================
    total_errores_a_corregir = 0
    for item in datos_evaluacion:
        modelos = item.get("evaluacion_modelos", {})
        for _, datos_modelo in modelos.items():
            if datos_modelo.get("Answer_Relevancy") == "ERROR" or datos_modelo.get("Faithfulness") == "ERROR":
                total_errores_a_corregir += 1

    if total_errores_a_corregir == 0:
        print("\n✅ El archivo está limpio. No se detectaron valores 'ERROR' para corregir.")
        return

    print(f"\n🎯 Se han detectado {total_errores_a_corregir} evaluaciones con errores. ¡Empezamos el rescate con Qwen desatado!")

    # 5. Procesar y corregir "ERROR"
    errores_procesados = 0
    cambios_realizados = 0

    for item in datos_evaluacion:
        id_pregunta = item.get("id_pregunta")
        pregunta_texto = item.get("pregunta", "")
        contexto_texto = mapa_contextos.get(id_pregunta, [])
        
        modelos = item.get("evaluacion_modelos", {})
        
        for nombre_modelo, datos_modelo in modelos.items():
            relevancia_val = datos_modelo.get("Answer_Relevancy")
            fidelidad_val = datos_modelo.get("Faithfulness")

            if relevancia_val == "ERROR" or fidelidad_val == "ERROR":
                errores_procesados += 1
                print(f"\n🛠️ [{errores_procesados}/{total_errores_a_corregir}] Corrigiendo [Pregunta {id_pregunta}] - Modelo: {nombre_modelo}")
                respuesta_texto = datos_modelo.get("respuesta_generada", "")

                try:
                    if relevancia_val == "ERROR":
                        print("   📡 Calculando Relevancia...")
                        res_rel = await metrica_relevancia.ascore(user_input=pregunta_texto, response=respuesta_texto)
                        datos_modelo["Answer_Relevancy"] = round(res_rel.value, 4)
                        cambios_realizados += 1

                    if fidelidad_val == "ERROR":
                        print("   📡 Calculando Fidelidad...")
                        res_fid = await metrica_fidelidad.ascore(
                            user_input=pregunta_texto,
                            response=respuesta_texto,
                            retrieved_contexts=contexto_texto
                        )
                        datos_modelo["Faithfulness"] = round(res_fid.value, 4)
                        cambios_realizados += 1
                        
                except Exception as e:
                    # ESTO ES NUEVO: Imprimimos el tipo de error exacto
                    print(f"   🚨 ERROR DETALLADO: {type(e).__name__} -> {str(e)}")

    # 6. Guardar cambios en el archivo ORIGINAL
    if cambios_realizados > 0:
        shutil.copy2(ARCHIVO_ORIGINAL, ARCHIVO_ORIGINAL + ".bak")
        print(f"\n💾 Backup creado en: {ARCHIVO_ORIGINAL}.bak")

        with open(ARCHIVO_ORIGINAL, "w", encoding="utf-8") as f:
            json.dump(datos_evaluacion, f, ensure_ascii=False, indent=4)
        
        print(f"✅ ¡Archivo actualizado! Se han corregido {cambios_realizados} métricas individuales.")

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    asyncio.run(rescatar_y_actualizar())