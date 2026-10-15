import os
import sys
import time
import json
import asyncio
import mimetypes
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import torch

import threading
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse # <-- Añadimos HTMLResponse

# (Tus otras importaciones y variables base se quedan igual)

# Initialize OpenAI Clients and FAISS Vector DB
vectorstore = None
async_cliente_ada = None
is_loading = True # <-- NUEVA VARIABLE para controlar la pantalla de carga

# Configure mimetypes to ensure CSS is served correctly on Windows
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

app = FastAPI(title="Jaen AI: Comparador Administrativo")

# Enable CORS for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants & Paths
MODELO_EMBEDDINGS = "dariolopez/bge-m3-es-legal-tmp-6"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ANTES
RUTA_INDICE_FAISS = os.path.join(BASE_DIR, "faiss_index_final")

# DESPUÉS
RUTA_INDICE_FAISS = os.path.join(BASE_DIR, "faiss_index_final")
# Y en cargar_faiss(), añade esta línea antes del FAISS.load_local:
print(f"Buscando índice en: {RUTA_INDICE_FAISS}")
BASE_URL_ADA = "http://ada01.ujaen.es:8080/v1"
API_KEY_ADA = "5e50191a63bd60fc4eb9f534143fa2eca8887bc79a2a53d7e950f39c5dc9487ecbd801a56637c3e3a2f79d98d5e05119803981476b1121841d0f94a3a72a5379"
DIR_IMAGENES = os.path.join(BASE_DIR, "imagenes")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "conversations.json")

# Initialize OpenAI Clients and FAISS Vector DB
vectorstore = None
async_cliente_ada = None

# Initialize AsyncOpenAI client
from openai import AsyncOpenAI
async_cliente_ada = AsyncOpenAI(api_key=API_KEY_ADA, base_url=BASE_URL_ADA, timeout=150.0)

# Helper function to load FAISS
def cargar_faiss():
    global vectorstore
    print("Cargando el Motor de Busqueda Vectorial (FAISS)...")
    try:
        from langchain_community.vectorstores import FAISS
        from langchain_community.embeddings import HuggingFaceEmbeddings
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"BGE Embeddings loading on: {device}")
        embeddings = HuggingFaceEmbeddings(model_name=MODELO_EMBEDDINGS, model_kwargs={'device': device})
        vectorstore = FAISS.load_local(
            folder_path=RUTA_INDICE_FAISS, 
            embeddings=embeddings, 
            allow_dangerous_deserialization=True
        )
        print("FAISS Vector DB loaded successfully!")
    except Exception as e:
        print("Error loading FAISS vector store:", e)

def cargar_faiss_background():
    global is_loading
    cargar_faiss() # Llama a tu función original
    is_loading = False # Cuando termina, avisa de que ya ha cargado

@app.on_event("startup")
def startup_event():
    # Inicia la carga en un hilo secundario para no bloquear la web
    hilo_carga = threading.Thread(target=cargar_faiss_background)
    hilo_carga.start()

# Local JSON History Helpers
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Error reading history JSON:", e)
        return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error writing history JSON:", e)

def save_chat_message(conv_id, question, salamandra_res, llama_res, sources):
    history = load_history()
    found = False
    
    # Format message structure
    message_pair = {
        "question": question,
        "salamandra": salamandra_res,
        "llama": llama_res,
        "sources": sources
    }
    
    for conv in history:
        if conv["id"] == conv_id:
            conv["messages"].append(message_pair)
            # Update title from default if it's the first real question
            if conv["title"] == "Nuevo Chat" or not conv["title"]:
                title = question[:35] + "..." if len(question) > 35 else question
                conv["title"] = title
            found = True
            break
            
    if not found:
        # Create a new conversation if it wasn't pre-initialized
        title = question[:35] + "..." if len(question) > 35 else question
        history.append({
            "id": conv_id,
            "title": title,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "messages": [message_pair]
        })
    save_history(history)

# Endpoints
LOADING_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Cargando Jaén AI...</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', sans-serif;
      min-height: 100vh;
      background: #f4f4f6;
      display: flex;
      overflow: hidden;
    }

    .sidebar {
      width: 270px;
      min-height: 100vh;
      background: #fff;
      border-right: 1px solid #e8e8ec;
      display: flex;
      flex-direction: column;
      padding: 0;
      flex-shrink: 0;
    }

    .sidebar-header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 18px 20px 16px;
      border-bottom: 1px solid #f0f0f4;
    }

    .logo-circle {
      width: 34px;
      height: 34px;
      border-radius: 50%;
      background: linear-gradient(135deg, #7c5cbf, #9b7de0);
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .logo-circle svg { width: 18px; height: 18px; }

    .sidebar-title {
      font-size: 15px;
      font-weight: 600;
      color: #1a1a2e;
    }

    .sidebar-btn {
      margin: 14px 16px 0;
      padding: 9px 14px;
      border: 1px solid #e0e0e8;
      border-radius: 8px;
      font-size: 13px;
      color: #888;
      background: #fff;
      text-align: left;
    }

    .sidebar-section-label {
      font-size: 11px;
      font-weight: 600;
      color: #aaa;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      padding: 18px 20px 8px;
    }

    .sidebar-item {
      padding: 9px 20px;
      font-size: 13px;
      color: #bbb;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sidebar-footer {
      margin-top: auto;
      padding: 16px 20px;
      border-top: 1px solid #f0f0f4;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: #7c5cbf;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 600;
      color: #fff;
    }

    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
    }

    .topbar {
      height: 56px;
      background: #fff;
      border-bottom: 1px solid #e8e8ec;
      display: flex;
      align-items: center;
      padding: 0 28px;
    }

    .topbar-title {
      font-size: 15px;
      font-weight: 700;
      color: #1a1a2e;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .topbar-logos {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .logo-placeholder {
      height: 28px;
      border-radius: 4px;
      background: #f0f0f4;
    }

    .content {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .loading-card {
      background: #fff;
      border-radius: 16px;
      border: 1px solid #e8e8ec;
      padding: 52px 56px 48px;
      width: 420px;
      text-align: center;
    }

    .icon-wrap {
      width: 56px;
      height: 56px;
      margin: 0 auto 24px;
      background: #f3effe;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      animation: icon-breathe 2.5s ease-in-out infinite;
    }

    @keyframes icon-breathe {
      0%, 100% { box-shadow: 0 0 0 0 rgba(124,92,191,0.15); }
      50% { box-shadow: 0 0 0 10px rgba(124,92,191,0); }
    }

    .icon-wrap svg { width: 26px; height: 26px; }

    .card-title {
      font-size: 20px;
      font-weight: 600;
      color: #1a1a2e;
      margin-bottom: 6px;
    }

    .card-sub {
      font-size: 13px;
      color: #a0a0b0;
      margin-bottom: 32px;
      line-height: 1.5;
    }

    .status-text {
      font-size: 13px;
      color: #8070aa;
      margin-bottom: 12px;
      min-height: 18px;
      transition: opacity 0.4s;
    }

    .track {
      width: 100%;
      height: 5px;
      background: #ededf2;
      border-radius: 999px;
      overflow: hidden;
      margin-bottom: 22px;
    }

    .bar {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #9b7de0, #7c5cbf);
      border-radius: 999px;
      animation: load-fake 15s cubic-bezier(0.4,0,0.2,1) forwards;
      position: relative;
    }

    .bar::after {
      content: '';
      position: absolute;
      right: 0; top: 0; bottom: 0;
      width: 30px;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.45));
      animation: shimmer 1.4s ease-in-out infinite;
    }

    @keyframes shimmer {
      0%, 100% { opacity: 0; }
      50% { opacity: 1; }
    }

    @keyframes load-fake {
      0%   { width: 5%; }
      20%  { width: 30%; }
      50%  { width: 57%; }
      80%  { width: 81%; }
      100% { width: 93%; }
    }

    .dots {
      display: flex;
      justify-content: center;
      gap: 6px;
    }

    .dot {
      width: 5px; height: 5px;
      border-radius: 50%;
      background: #c5b8e8;
      animation: dot-pulse 1.8s ease-in-out infinite;
    }
    .dot:nth-child(2) { animation-delay: 0.3s; }
    .dot:nth-child(3) { animation-delay: 0.6s; }

    @keyframes dot-pulse {
      0%, 100% { background: #ddd8f0; transform: scale(0.8); }
      50%       { background: #7c5cbf; transform: scale(1.2); }
    }
  </style>
</head>
<body>

  <div class="sidebar">
    <div class="sidebar-header">
      <div class="logo-circle">
        <svg viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8" stroke="rgba(255,255,255,0.6)" stroke-width="1.5"/>
          <path d="M6 10 C6 7.8 7.8 6 10 6 C12.2 6 14 7.8 14 10" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
      <span class="sidebar-title">Chat AI</span>
    </div>
    <div class="sidebar-btn">Nuevo Chat</div>
    <div class="sidebar-section-label">Conversaciones</div>
    <div class="sidebar-item" style="color:#555;">frfwweef</div>
    <div class="sidebar-item">¿A qué departamento d…</div>
    <div class="sidebar-item">pepepepepepepe</div>
    <div class="sidebar-item">como obtengo el bonob…</div>
    <div class="sidebar-footer">
      <div class="avatar">U</div>
    </div>
  </div>

  <div class="main">
    <div class="topbar">
      <span class="topbar-title">Jaén AI: Comparador Administrativo</span>
      <div class="topbar-logos">
        <div class="logo-placeholder" style="width:32px; border-radius:50%;"></div>
        <div class="logo-placeholder" style="width:52px;"></div>
        <div class="logo-placeholder" style="width:64px;"></div>
      </div>
    </div>

    <div class="content">
      <div class="loading-card">
        <div class="icon-wrap">
          <svg viewBox="0 0 26 26" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M8 13 C8 9.7 10.2 7 13 7 C15.8 7 18 9.7 18 13 C18 16.3 15.8 19 13 19 C10.2 19 8 16.3 8 13Z" stroke="#7c5cbf" stroke-width="1.5"/>
            <path d="M13 7 C13 5 14 3.5 15.5 3" stroke="#7c5cbf" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M13 7 C12 4.5 10.5 3.5 9 4" stroke="#9b7de0" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="card-title">Jaén AI</div>
        <div class="card-sub">Conectando con la base de datos vectorial<br>y modelos de lenguaje…</div>

        <div class="status-text" id="status-msg">Iniciando servicios…</div>

        <div class="track">
          <div class="bar"></div>
        </div>

        <div class="dots">
          <div class="dot"></div>
          <div class="dot"></div>
          <div class="dot"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const msgs = [
      "Iniciando servicios…",
      "Conectando con la base de datos vectorial…",
      "Inicializando modelos de lenguaje…",
      "Cargando normativa administrativa…",
      "Casi listo…"
    ];
    let mi = 0;
    const el = document.getElementById("status-msg");
    setInterval(() => {
      mi = (mi + 1) % msgs.length;
      el.style.opacity = 0;
      setTimeout(() => { el.textContent = msgs[mi]; el.style.opacity = 1; }, 300);
    }, 3000);

    setInterval(async () => {
      try {
        let res = await fetch('/api/status');
        let data = await res.json();
        if (!data.loading) { window.location.reload(); }
      } catch(e) {}
    }, 2000);
  </script>
</body>
</html>
"""

@app.get("/")
def get_index():
    if is_loading:
        return HTMLResponse(content=LOADING_HTML)
    return FileResponse(os.path.join(os.path.dirname(__file__), "templates", "index.html"))

@app.get("/api/status")
def get_status():
    return {"loading": is_loading}

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Image serving endpoint to avoid local path browser security blocks
@app.get("/api/imagenes/{filename}")
def serve_image(filename: str):
    full_path = os.path.join(DIR_IMAGENES, filename)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    
    # Determine correct media type
    media_type, _ = mimetypes.guess_type(full_path)
    if not media_type:
        media_type = "image/png"
    return FileResponse(full_path, media_type=media_type)

# History Endpoints
@app.get("/api/conversations")
def get_conversations():
    return load_history()

@app.post("/api/conversations")
def create_conversation(data: dict):
    conv_id = data.get("id")
    title = data.get("title", "Nuevo Chat")
    if not conv_id:
        raise HTTPException(status_code=400, detail="Conversation ID is required")
    
    history = load_history()
    # Check if exists
    for conv in history:
        if conv["id"] == conv_id:
            return conv
            
    new_conv = {
        "id": conv_id,
        "title": title,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "messages": []
    }
    history.append(new_conv)
    save_history(history)
    return new_conv

@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str):
    history = load_history()
    for conv in history:
        if conv["id"] == conv_id:
            return conv
    raise HTTPException(status_code=404, detail="Conversación no encontrada")

@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    history = load_history()
    new_history = [c for c in history if c["id"] != conv_id]
    save_history(new_history)
    return {"status": "success"}

# RAG & Concurrent OpenAI completion streaming
@app.get("/api/chat")
async def chat_stream(pregunta: str = Query(...), conv_id: str = Query(...)):
    if not vectorstore:
        # If vector DB failed to load, return mock retrieval
        contexto_unido = "No hay contexto disponible de FAISS."
        sources = [{"name": "Error de Base de Datos Vectorial", "url": ""}]
    else:
        try:
            # Perform FAISS search (k=3 as standard)
            docs_and_scores = vectorstore.similarity_search_with_score(pregunta, k=3)
            contexto_unido = "\n\n".join([doc.page_content for doc, score in docs_and_scores])
            
            sources = []
            seen = set()
            for doc, score in docs_and_scores:
                name = doc.metadata.get("nombre_tramite") or doc.metadata.get("source") or "Trámite Municipal"
                if name.endswith('.txt'):
                    name = name[:-4]
                url = doc.metadata.get("url") or ""
                if name not in seen:
                    seen.add(name)
                    sources.append({"name": name, "url": url})
        except Exception as e:
            print("FAISS similarity search error:", e)
            contexto_unido = "Error al buscar en la base de datos."
            sources = [{"name": "Error de Búsqueda", "url": ""}]

    async def event_generator():
        # SSE streams require client-side parsing. We yield JSON chunks.
        
        # 1. Yield init message containing sources
        yield f"data: {json.dumps({'type': 'init', 'sources': sources})}\n\n"
        await asyncio.sleep(0.02) # Soft yield to ensure order

        # 2. Concurrency queue
        queue = asyncio.Queue()

        # Prompt construction
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

        # Worker for individual LLM streaming
        async def fetch_llm(model_name: str, alias_key: str):
            t_start = time.time()
            full_response = ""
            try:
                # Direct call to ADA server via AsyncOpenAI
                response = await async_cliente_ada.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    temperature=0.0
                )
                async for chunk in response:
                    if len(chunk.choices) > 0:
                        token = chunk.choices[0].delta.content
                        if token:
                            full_response += token
                            await queue.put({
                                "type": "token",
                                "model": alias_key,
                                "text": token
                            })
                elapsed = time.time() - t_start
                await queue.put({
                    "type": "done",
                    "model": alias_key,
                    "text": full_response,
                    "time": round(elapsed, 2)
                })
            except Exception as ex:
                elapsed = time.time() - t_start
                await queue.put({
                    "type": "error",
                    "model": alias_key,
                    "text": f"Error: No se pudo conectar con el modelo ({str(ex)})",
                    "time": round(elapsed, 2)
                })

        # Spawn both tasks in the background concurrently
        task_llama = asyncio.create_task(fetch_llm(
            "/mnt/beegfs/sinai-data/meta-llama/Llama-3.1-8B-Instruct", 
            "llama"
        ))
        task_salamandra = asyncio.create_task(fetch_llm(
            "Salamandra-7B-It", 
            "salamandra"
        ))

        # Yield messages from queue as they arrive
        active_tasks = 2
        salamandra_final = {"content": "", "time": 0.0}
        llama_final = {"content": "", "time": 0.0}

        while active_tasks > 0:
            msg = await queue.get()
            yield f"data: {json.dumps(msg)}\n\n"
            
            if msg["type"] in ["done", "error"]:
                if msg["model"] == "salamandra":
                    salamandra_final = {"content": msg["text"], "time": msg["time"]}
                else:
                    llama_final = {"content": msg["text"], "time": msg["time"]}
                active_tasks -= 1

        # Wait for coroutines to complete fully
        await task_llama
        await task_salamandra

        # 3. Save conversation history
        save_chat_message(conv_id, pregunta, salamandra_final, llama_final, sources)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Mount Static Folder (styles, scripts, assets)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    # Allow running directly for development
    uvicorn.run(app, host="127.0.0.1", port=8000)
