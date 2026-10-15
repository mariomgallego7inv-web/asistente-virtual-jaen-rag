  #Este código usa la tarjeta gráfica GPU T4 y lo uso para crear los índeces de los embeddings, MODELO_EMBEDDINGS:
#     - dariolopez/bge-m3-es-legal-tmp-6
#     - dariolopez/roberta-base-bne-finetuned-msmarco-qa-es-mnrl-mn
#     - hiiamsid/sentence_similarity_spanish_es
import os
import pickle
import re
import sys
import torch
from tqdm import tqdm

try:
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS
except ImportError as e:
    print(f"❌ ERROR CRÍTICO: Falta la librería '{e.name}'.")
    sys.exit()

# ----------------- CONFIGURACIÓN -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.path.exists('/content/drive'):
    RUTA_INPUT = "/content/drive/MyDrive/Tramites_Jaen_Final_Corregido"
    RUTA_OUTPUT = "/content/drive/MyDrive/bge-m3-es-legal-tmp-6/Tramites_Jaen_Indices_GPU_bge"
else:
    RUTA_INPUT = os.path.join(BASE_DIR, "data", "tramites_txt")
    RUTA_OUTPUT = os.path.join(BASE_DIR, "faiss_index_final")

os.makedirs(RUTA_OUTPUT, exist_ok=True)

NOMBRE_FAISS = "faiss_index_final"
NOMBRE_CHUNKS = "bm25_chunks_final.pkl"
#MODELO_EMBEDDINGS = "hiiamsid/sentence_similarity_spanish_es"
#MODELO_EMBEDDINGS = "dariolopez/bge-m3-es-legal-tmp-6"
#MODELO_EMBEDDINGS = "dariolopez/roberta-base-bne-finetuned-msmarco-qa-es-mnrl-mn"
MODELO_EMBEDDINGS = "wilfredomartel/bge-m3-es-legal-v3"

# ----------------- FUNCIONES -----------------

def chunking_estructural(docs):
    all_splits = []
    # Splitter para trocear si un campo es gigante
    safety_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200, chunk_overlap=200, separators=["\n\n", "\n", ". ", " ", ""]
    )

    print(f"Procesando {len(docs)} documentos...")

    for doc in docs:
        texto_completo = doc.page_content
        fuente = doc.metadata.get("source", "desconocido")

        # 1. Dividimos por los bloques que generó el scraping
        bloques = texto_completo.split("### ")

        for bloque in bloques:
            if not bloque.strip(): continue

            # 2. Separamos título (ej: Organo Gestor) del contenido
            partes = bloque.split("\n", 1)
            titulo_linea = partes[0].strip()
            contenido_resto = partes[1].strip() if len(partes) > 1 else ""

            # --- EXTRACCIÓN INTELIGENTE DE METADATOS ---

            # Nombre del trámite
            match_nombre = re.search(r"NOMBRE_TRAMITE:\s*(.+)", contenido_resto)
            nombre_tramite = match_nombre.group(1).strip() if match_nombre else "Trámite General"

            # URL y ID (Aquí corregimos el fallo de tu código anterior)
            match_url = re.search(r"URL_ORIGEN:\s*(.+)", contenido_resto)
            url_origen = match_url.group(1).strip() if match_url else ""

            id_tramite = "N/A"
            if url_origen:
                # Sacamos el número después de DETALLE=
                match_id = re.search(r"DETALLE=(\d+)", url_origen)
                if match_id: id_tramite = match_id.group(1)

            # Limpiamos el footer repetitivo del texto visible
            if "Este campo pertenece al tramite:" in contenido_resto:
                contenido_limpio = contenido_resto.split("Este campo pertenece al tramite:")[0].strip()
            else:
                contenido_limpio = contenido_resto

            # ---------------------------------------------------------
            # 🔥 INYECCIÓN DE CONTEXTO (CLAVE PARA BM25) 🔥
            # Ponemos el nombre del trámite AL PRINCIPIO del texto del chunk.
            # Así, aunque el campo sea "Organo Gestor", BM25 sabe de qué trámite habla.
            # ---------------------------------------------------------
            texto_final = (
                f"TRAMITE: {nombre_tramite}\n"
                f"CAMPO: {titulo_linea}\n"
                f"{contenido_limpio}"
            )

            metadata = {
                "source": fuente,
                "campo": titulo_linea.replace(":", ""),
                "nombre_tramite": nombre_tramite,
                "id_tramite": id_tramite, # ID real sacado de la URL
                "url": url_origen
            }

            # Guardamos
            if len(texto_final) > 2000:
                subs = safety_splitter.split_text(texto_final)
                for s in subs:
                    all_splits.append(Document(page_content=s, metadata=metadata))
            else:
                all_splits.append(Document(page_content=texto_final, metadata=metadata))

    return all_splits

def crear_indices():
    if not os.path.exists(RUTA_INPUT):
        print(f"❌ ERROR: No existe la carpeta {RUTA_INPUT}")
        return

    archivos = [f for f in os.listdir(RUTA_INPUT) if f.endswith(".txt")]
    print(f"📂 Cargando {len(archivos)} archivos...")

    docs = []
    for archivo in tqdm(archivos):
        path = os.path.join(RUTA_INPUT, archivo)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                docs.append(Document(page_content=f.read(), metadata={"source": archivo}))
        except: pass

    print("\n✂️  Dividiendo documentos...")
    splits = chunking_estructural(docs)
    print(f"📊 Total chunks generados: {len(splits)}")

    # Verificación visual para que veas que ahora sí pilla el ID
    if len(splits) > 0:
        print(f"\n🔎 Ejemplo Metadatos: {splits[0].metadata}")
        print(f"👀 Ejemplo Texto Inyectado:\n{splits[0].page_content[:150]}...")

    print(f"\n🧠 Cargando Embeddings: {MODELO_EMBEDDINGS}")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    embeddings = HuggingFaceEmbeddings(
        model_name=MODELO_EMBEDDINGS,
        model_kwargs={'device': device},
        encode_kwargs={'normalize_embeddings': True}
    )

    print("\n⚡ Creando índice FAISS...")
    vectorstore = FAISS.from_documents(splits, embeddings)

    print(f"\n💾 Guardando índices en {RUTA_OUTPUT}...")
    vectorstore.save_local(os.path.join(RUTA_OUTPUT, NOMBRE_FAISS))

    with open(os.path.join(RUTA_OUTPUT, NOMBRE_CHUNKS), "wb") as f:
        pickle.dump(splits, f)

    print("\n✅ ¡ÉXITO! Índices listos para el RAG Híbrido.")

if __name__ == "__main__":
    crear_indices()