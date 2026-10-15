import os
import json
import pickle
import csv
import asyncio
from typing import List

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

# ==========================================
# IMPORTACIONES DE RAGAS (NON-LLM)
# ==========================================
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import NonLLMContextRecall, NonLLMContextPrecisionWithReference

# ==========================================
# CONFIGURACIÓN
# ==========================================
#RUTA_INDICES = r"C:\Users\mario\Desktop\trabajoCodigo - copia\.a\indices\sentence_similarity_spanish_es\Tramites_Jaen_Indices_GPU"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
RUTA_INDICES = os.path.join(PROJECT_ROOT, "faiss_index_final")
RUTA_JSON = os.path.join(PROJECT_ROOT, "data", "dataset_evaluacion.json")

NOMBRE_FAISS = "."
NOMBRE_BM25 = "bm25_chunks_final.pkl"
#MODELO_EMBEDDINGS = "hiiamsid/sentence_similarity_spanish_es"
MODELO_EMBEDDINGS = "dariolopez/bge-m3-es-legal-tmp-6"
#MODELO_EMBEDDINGS = "dariolopez/roberta-base-bne-finetuned-msmarco-qa-es-mnrl-mn"
#MODELO_EMBEDDINGS = "wilfredomartel/bge-m3-es-legal-v3"
# ==========================================
# FUNCIONES DE CARGA Y BÚSQUEDA HÍBRIDA
# ==========================================
def algoritmo_rrf(docs_bm25: List[Document], docs_faiss: List[Document], k=60):
    rrf_score = {}
    doc_map = {} 
    
    for rank, doc in enumerate(docs_bm25):
        id_tramite = doc.metadata.get("id_tramite", "N/A")
        clave = f"{doc.page_content}____{id_tramite}"
        doc_map[clave] = doc
        rrf_score[clave] = rrf_score.get(clave, 0) + 1 / (k + rank + 1)
    
    for rank, doc in enumerate(docs_faiss):
        id_tramite = doc.metadata.get("id_tramite", "N/A")
        clave = f"{doc.page_content}____{id_tramite}"
        if clave not in doc_map: 
            doc_map[clave] = doc
        rrf_score[clave] = rrf_score.get(clave, 0) + 1 / (k + rank + 1)
    
    resultados_ordenados = sorted(rrf_score.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[clave] for clave, score in resultados_ordenados]

def cargar_sistema():
    ruta_faiss = os.path.join(RUTA_INDICES, NOMBRE_FAISS)
    ruta_bm25 = os.path.join(RUTA_INDICES, NOMBRE_BM25)

    embeddings = HuggingFaceEmbeddings(
        model_name=MODELO_EMBEDDINGS,
        model_kwargs={'device': 'cpu'}
    )
    vectorstore = FAISS.load_local(ruta_faiss, embeddings, allow_dangerous_deserialization=True)
    faiss_retriever = vectorstore.as_retriever(search_kwargs={"k": 15})

    with open(ruta_bm25, "rb") as f:
        splits = pickle.load(f)
    bm25_retriever = BM25Retriever.from_documents(splits)
    bm25_retriever.k = 15

    return bm25_retriever, faiss_retriever

# ==========================================
# 🎯 MOTOR DE EVALUACIÓN OFICIAL DE RAGAS (TRIPLE)
# ==========================================

async def evaluar_con_ragas():
    # 1. Cargamos datos
    with open(RUTA_JSON, 'r', encoding='utf-8') as f:
        eval_dataset = json.load(f)
        
    bm25, faiss = cargar_sistema()
    total_queries = len(eval_dataset)
    
    # 2. Inicializamos las métricas de RAGAS
    metric_recall = NonLLMContextRecall()
    metric_precision = NonLLMContextPrecisionWithReference()
    
    # Contadores de puntuación acumulada para los 3 sistemas
    suma_rec_bm25, suma_prec_bm25 = 0, 0
    suma_rec_faiss, suma_prec_faiss = 0, 0
    suma_rec_hib, suma_prec_hib = 0, 0

    print(f"\n🚀 Iniciando Evaluación TRIPLE con RAGAS Non-LLM ({total_queries} preguntas)...")

    for i, item in enumerate(eval_dataset):
        pregunta = item.get("pregunta", "")
        pasaje_referencia = item.get("pasaje", "") # Lo que espera RAGAS
        
        # Búsquedas
        docs_bm25 = bm25.invoke(pregunta)
        docs_faiss = faiss.invoke(pregunta)
        best_docs = algoritmo_rrf(docs_bm25, docs_faiss, k=60)
        
        # Extraemos solo el texto de los 5 primeros chunks recuperados
        textos_BM25 = [doc.page_content for doc in docs_bm25[:5]]
        textos_Faiss = [doc.page_content for doc in docs_faiss[:5]]
        textos_Hibrido = [doc.page_content for doc in best_docs[:5]]
        
        # 3. Creamos TRES objetos "Sample" para Ragas
        sample_bm25 = SingleTurnSample(retrieved_contexts=textos_BM25, reference_contexts=[pasaje_referencia])
        sample_faiss = SingleTurnSample(retrieved_contexts=textos_Faiss, reference_contexts=[pasaje_referencia])
        sample_hib = SingleTurnSample(retrieved_contexts=textos_Hibrido, reference_contexts=[pasaje_referencia])
        
        # 4. Calculamos puntuación con Ragas para cada uno
        # --- BM25 ---
        r_bm25 = await metric_recall.single_turn_ascore(sample_bm25)
        p_bm25 = await metric_precision.single_turn_ascore(sample_bm25)
        suma_rec_bm25 += r_bm25; suma_prec_bm25 += p_bm25
        
        # --- FAISS ---
        r_faiss = await metric_recall.single_turn_ascore(sample_faiss)
        p_faiss = await metric_precision.single_turn_ascore(sample_faiss)
        suma_rec_faiss += r_faiss; suma_prec_faiss += p_faiss
        
        # --- HÍBRIDO ---
        r_hib = await metric_recall.single_turn_ascore(sample_hib)
        p_hib = await metric_precision.single_turn_ascore(sample_hib)
        suma_rec_hib += r_hib; suma_prec_hib += p_hib

        # Print por pantalla (mostramos solo el Híbrido para no saturar, pero calcula todo)
        print(f"[{i+1}/{total_queries}] Evaluando... | Híbrido -> Recall: {r_hib:.2f} | Precision: {p_hib:.2f}")

    # ==========================================
    # 📈 RESULTADOS FINALES (Medias en Porcentaje)
    # ==========================================
    media_rec_bm25 = (suma_rec_bm25 / total_queries) * 100
    media_prec_bm25 = (suma_prec_bm25 / total_queries) * 100
    
    media_rec_faiss = (suma_rec_faiss / total_queries) * 100
    media_prec_faiss = (suma_prec_faiss / total_queries) * 100
    
    media_rec_hib = (suma_rec_hib / total_queries) * 100
    media_prec_hib = (suma_prec_hib / total_queries) * 100

    print("\n" + "="*60)
    print("📊 RESULTADOS RAGAS (NON-LLM) TOP 5 - COMPARATIVA COMPLETA")
    print("="*60)
    print(f"Modelo: {MODELO_EMBEDDINGS}\n")
    print(f"BM25 Solo:     Recall: {media_rec_bm25:.2f}% | Precision: {media_prec_bm25:.2f}%")
    print(f"FAISS Solo:    Recall: {media_rec_faiss:.2f}% | Precision: {media_prec_faiss:.2f}%")
    print(f"HÍBRIDO (RRF): Recall: {media_rec_hib:.2f}% | Precision: {media_prec_hib:.2f}%")
    
    # ==========================================
    # 💾 GUARDADO EN CSV
    # ==========================================
    archivo_csv = os.path.join(PROJECT_ROOT, "results", "evaluacion_determinista_recuperador.csv")
    existe = os.path.isfile(archivo_csv)
    
    # Función rápida para el Excel en español
    def a_es(numero): return str(round(numero, 2)).replace('.', ',')

    with open(archivo_csv, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        if not existe:
            writer.writerow([
                "Modelo", 
                "BM25_Recall@5", "BM25_Precision@5", 
                "FAISS_Recall@5", "FAISS_Precision@5", 
                "Hibrido_Recall@5", "Hibrido_Precision@5"
            ])
        writer.writerow([
            MODELO_EMBEDDINGS, 
            a_es(media_rec_bm25), a_es(media_prec_bm25),
            a_es(media_rec_faiss), a_es(media_prec_faiss),
            a_es(media_rec_hib), a_es(media_prec_hib)
        ])
        
    print(f"\n✅ Datos guardados en {archivo_csv}. ¡Listo para Excel!")

if __name__ == "__main__":
    # Como Ragas usa funciones async/await, arrancamos el código así:
    asyncio.run(evaluar_con_ragas())