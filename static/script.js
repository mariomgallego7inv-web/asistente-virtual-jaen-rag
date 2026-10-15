// State Management
let currentConversationId = null;
let activeView = 'welcome'; // 'welcome', 'chat', 'history'
let currentSources = [];

// DOM Elements
const sidebar = document.getElementById('sidebar');
const btnCollapse = document.getElementById('btn-collapse');
const btnExpand = document.getElementById('btn-expand');
const labelsPanel = document.getElementById('labels-panel');
const recentChatsList = document.getElementById('recent-chats-list');

const navNewChat = document.getElementById('nav-new-chat');
const navActiveChats = document.getElementById('nav-active-chats');
const navHistory = document.getElementById('nav-history');
const navSettings = document.getElementById('nav-settings');
const labelNewChat = document.getElementById('label-new-chat');

const welcomeView = document.getElementById('welcome-view');
const chatView = document.getElementById('chat-view');
const historyView = document.getElementById('history-view');
const visualizationPanel = document.getElementById('visualization-panel');

const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');

const historyItemsGrid = document.getElementById('history-items-grid');

// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    // Generate an initial conversation ID
    createNewSession();
    
    // Load sidebar history
    loadRecentChats();
    
    // Set up event listeners
    initEventListeners();
});

function createNewSession() {
    currentConversationId = 'chat-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

// ==========================================
// EVENT LISTENERS
// ==========================================
function initEventListeners() {
    // Sidebar Collapse / Expand
    btnCollapse.addEventListener('click', collapseSidebar);
    btnExpand.addEventListener('click', expandSidebar);
    
    // Navigation Action Buttons
    navNewChat.addEventListener('click', startNewChat);
    labelNewChat.addEventListener('click', startNewChat);
    
    navActiveChats.addEventListener('click', () => {
        setActiveTab(navActiveChats);
        if (activeView === 'history') {
            if (hasActiveConversationMessages()) {
                switchView('chat');
                setTimeout(scrollToBottom, 50);
            } else {
                switchView('welcome');
            }
        }
    });
    
    navHistory.addEventListener('click', () => {
        setActiveTab(navHistory);
        loadHistoryView();
    });
    
    navSettings.addEventListener('click', () => {
        alert('Ajustes del comparador:\n- Servidor: ADA (UJA)\n- Embeddings: dariolopez/bge-m3-es-legal-tmp-6\n- Modelo Llama: Llama-3.1-8B-Instruct\n- Modelo Salamandra: Salamandra-7B-It-legal-BSC');
    });
    
    // Main Chat Form Submission
    chatForm.addEventListener('submit', handleChatSubmit);
    
    // Enable enter key submission
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });
}

// ==========================================
// NAVIGATION & SIDEBAR VIEW CONTROLLER
// ==========================================
function collapseSidebar() {
    sidebar.classList.add('collapsed');
    document.querySelector('.app-container').classList.add('sidebar-collapsed');
    
    setTimeout(() => {
        btnExpand.classList.remove('hidden');
    }, 200);
}

function expandSidebar() {
    sidebar.classList.remove('collapsed');
    document.querySelector('.app-container').classList.remove('sidebar-collapsed');
    btnExpand.classList.add('hidden');
}

function setActiveTab(activeBtn) {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    activeBtn.classList.add('active');
}

function switchView(viewName) {
    activeView = viewName;
    
    welcomeView.classList.remove('active');
    chatView.classList.remove('active');
    historyView.classList.remove('active');
    
    if (viewName === 'welcome') {
        welcomeView.classList.add('active');
    } else if (viewName === 'chat') {
        chatView.classList.add('active');
    } else if (viewName === 'history') {
        historyView.classList.add('active');
    }
}

function hasActiveConversationMessages() {
    return chatView.querySelectorAll('.chat-exchange-row').length > 0;
}

function scrollToBottom() {
    visualizationPanel.scrollTop = visualizationPanel.scrollHeight;
}

function scrollToBottomIfNeeded() {
    const threshold = 150; // pixels from the bottom
    const isNearBottom = (visualizationPanel.scrollHeight - visualizationPanel.scrollTop - visualizationPanel.clientHeight) < threshold;
    if (isNearBottom) {
        visualizationPanel.scrollTop = visualizationPanel.scrollHeight;
    }
}

// ==========================================
// CHAT SESSION & RECENT CHATS CONTROLLER
// ==========================================
function startNewChat() {
    createNewSession();
    
    // Clear dynamic chat view
    chatView.innerHTML = '';
    
    // Update sidebar active selection
    document.querySelectorAll('.recent-chat-item').forEach(item => {
        item.classList.remove('active');
    });
    
    setActiveTab(navActiveChats);
    switchView('welcome');
    
    chatInput.value = '';
    chatInput.placeholder = "Escribe tu pregunta...";
    chatInput.focus();
}

async function loadRecentChats() {
    try {
        const res = await fetch('/api/conversations');
        if (!res.ok) throw new Error("Error loading chats");
        const conversations = await res.json();
        
        recentChatsList.innerHTML = '';
        if (conversations.length === 0) {
            recentChatsList.innerHTML = '<div class="no-chats-msg" style="font-size: 0.8rem; color: var(--text-muted); text-align: center; padding-top: 10px;">No hay consultas.</div>';
            return;
        }
        
        // Sort conversations chronologically (newest first)
        conversations.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        
        conversations.forEach(conv => {
            const div = document.createElement('div');
            div.className = `recent-chat-item ${conv.id === currentConversationId ? 'active' : ''}`;
            div.dataset.id = conv.id;
            div.textContent = conv.title || "Consulta sin título";
            
            div.addEventListener('click', () => {
                loadConversation(conv.id);
            });
            
            recentChatsList.appendChild(div);
        });
    } catch (e) {
        console.error(e);
        recentChatsList.innerHTML = '<div class="error-msg" style="font-size: 0.8rem; color: red; text-align: center;">Error.</div>';
    }
}

async function loadConversation(convId) {
    try {
        currentConversationId = convId;
        setActiveTab(navActiveChats);
        
        const res = await fetch(`/api/conversations/${convId}`);
        if (!res.ok) throw new Error("Conversation not found");
        const conv = await res.json();
        
        // Highlight active item in sidebar
        document.querySelectorAll('.recent-chat-item').forEach(item => {
            if (item.dataset.id === convId) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
        
        if (conv.messages && conv.messages.length > 0) {
            chatView.innerHTML = ''; // Clear current panels
            
            // Loop and render all exchanges in history sequence
            conv.messages.forEach((msg, idx) => {
                const exchangeRow = document.createElement('div');
                exchangeRow.className = 'chat-exchange-row';
                exchangeRow.id = `exchange-${idx}`;
                
                // Add user question bubble
                const userBubbleContainer = document.createElement('div');
                userBubbleContainer.className = 'user-bubble-container';
                const userMessageBubble = document.createElement('div');
                userMessageBubble.className = 'user-message-bubble';
                userMessageBubble.textContent = msg.question;
                userBubbleContainer.appendChild(userMessageBubble);
                exchangeRow.appendChild(userBubbleContainer);
                
                // Add comparison grid
                const grid = document.createElement('div');
                grid.className = 'comparison-grid';
                
                // Salamandra Column
                const colSalamandra = document.createElement('div');
                colSalamandra.className = 'comparison-column salamandra-card';
                colSalamandra.innerHTML = `
                    <div class="column-header">
                        <img src="/api/imagenes/salamandra.png" alt="Salamandra Icon" class="model-icon">
                        <h3 class="model-name">Salamandra (SINAI-UJA)</h3>
                    </div>
                    <div class="column-body markdown-content response-salamandra">
                        ${formatMarkdown(msg.salamandra.content)}
                    </div>
                    <div class="column-footer footer-salamandra">
                    </div>
                `;
                
                // Llama Column
                const colLlama = document.createElement('div');
                colLlama.className = 'comparison-column llama-card';
                colLlama.innerHTML = `
                    <div class="column-header">
                        <img src="/api/imagenes/llama.png" alt="Llama Icon" class="model-icon">
                        <h3 class="model-name">Llama 3.1 8B Instruct (Meta)</h3>
                    </div>
                    <div class="column-body markdown-content response-llama">
                        ${formatMarkdown(msg.llama.content)}
                    </div>
                    <div class="column-footer footer-llama">
                    </div>
                `;
                
                grid.appendChild(colSalamandra);
                grid.appendChild(colLlama);
                exchangeRow.appendChild(grid);
                chatView.appendChild(exchangeRow);
                
                // Render footers safely
                const footerSalamandra = colSalamandra.querySelector('.footer-salamandra');
                const footerLlama = colLlama.querySelector('.footer-llama');
                renderFooter(footerSalamandra, msg.salamandra.time ? msg.salamandra.time + 's' : '--', msg.sources);
                renderFooter(footerLlama, msg.llama.time ? msg.llama.time + 's' : '--', msg.sources);
            });
            
            switchView('chat');
            setTimeout(scrollToBottom, 50);
        } else {
            startNewChat();
            currentConversationId = convId;
        }
    } catch (e) {
        console.error(e);
        alert("No se pudo cargar la conversación seleccionada.");
    }
}

// ==========================================
// RENDER LOOP & FRAME-THROTTLING ENGINE
// ==========================================
let renderPending = false;
let salamandraPendingText = null;
let llamaPendingText = null;
let salamandraEl = null;
let llamaEl = null;

function queueRender(model, text, element) {
    if (model === 'salamandra') {
        salamandraPendingText = text;
        salamandraEl = element;
    } else if (model === 'llama') {
        llamaPendingText = text;
        llamaEl = element;
    }
    
    if (!renderPending) {
        renderPending = true;
        requestAnimationFrame(renderStep);
    }
}

function renderStep() {
    if (salamandraEl && salamandraPendingText !== null) {
        salamandraEl.innerHTML = formatMarkdown(salamandraPendingText);
        salamandraPendingText = null;
    }
    if (llamaEl && llamaPendingText !== null) {
        llamaEl.innerHTML = formatMarkdown(llamaPendingText);
        llamaPendingText = null;
    }
    
    // Proximity scroll execution synced with vertical re-paint
    const threshold = 150;
    const isNearBottom = (visualizationPanel.scrollHeight - visualizationPanel.scrollTop - visualizationPanel.clientHeight) < threshold;
    if (isNearBottom) {
        visualizationPanel.scrollTop = visualizationPanel.scrollHeight;
    }
    
    renderPending = false;
}

// ==========================================
// RAG STREAMING PIPELINE (SSE)
// ==========================================
async function handleChatSubmit(e) {
    if (e) e.preventDefault();
    
    const question = chatInput.value.trim();
    if (!question) return;
    
    // Reset rendering pipeline buffers
    renderPending = false;
    salamandraPendingText = null;
    llamaPendingText = null;
    salamandraEl = null;
    llamaEl = null;
    
    // 1. Prepare UI view states
    chatInput.value = '';
    
    if (activeView !== 'chat') {
        chatView.innerHTML = '';
        switchView('chat');
    }
    setActiveTab(navActiveChats);
    
    // 2. Append a new exchange row at the bottom
    const newIdx = chatView.querySelectorAll('.chat-exchange-row').length;
    const exchangeRow = document.createElement('div');
    exchangeRow.className = 'chat-exchange-row';
    exchangeRow.id = `exchange-${newIdx}`;
    
    // User Question Bubble
    const userBubbleContainer = document.createElement('div');
    userBubbleContainer.className = 'user-bubble-container';
    const userMessageBubble = document.createElement('div');
    userMessageBubble.className = 'user-message-bubble';
    userMessageBubble.textContent = question;
    userBubbleContainer.appendChild(userMessageBubble);
    exchangeRow.appendChild(userBubbleContainer);
    
    // Comparison Grid
    const grid = document.createElement('div');
    grid.className = 'comparison-grid';
    
    // Salamandra card
    const colSalamandra = document.createElement('div');
    colSalamandra.className = 'comparison-column salamandra-card';
    colSalamandra.innerHTML = `
        <div class="column-header">
            <img src="/api/imagenes/salamandra.png" alt="Salamandra Icon" class="model-icon">
            <h3 class="model-name">Salamandra (SINAI-UJA)</h3>
        </div>
        <div class="column-body markdown-content response-salamandra">
            ${createSkeleton()}
        </div>
        <div class="column-footer footer-salamandra">
            <span class="footer-time">Tiempo: Buscando...</span><span class="footer-source">Fuente: --</span>
        </div>
    `;
    
    // Llama card
    const colLlama = document.createElement('div');
    colLlama.className = 'comparison-column llama-card';
    colLlama.innerHTML = `
        <div class="column-header">
            <img src="/api/imagenes/llama.png" alt="Llama Icon" class="model-icon">
            <h3 class="model-name">Llama 3.1 8B Instruct (Meta)</h3>
        </div>
        <div class="column-body markdown-content response-llama">
            ${createSkeleton()}
        </div>
        <div class="column-footer footer-llama">
            <span class="footer-time">Tiempo: Buscando...</span><span class="footer-source">Fuente: --</span>
        </div>
    `;
    
    grid.appendChild(colSalamandra);
    grid.appendChild(colLlama);
    exchangeRow.appendChild(grid);
    chatView.appendChild(exchangeRow);
    
    // Auto-scroll to bottom immediately
    scrollToBottom();
    
    // Store references to the specific elements of this new exchange row
    const responseBodySalamandra = colSalamandra.querySelector('.response-salamandra');
    const responseBodyLlama = colLlama.querySelector('.response-llama');
    const footerElSalamandra = colSalamandra.querySelector('.footer-salamandra');
    const footerElLlama = colLlama.querySelector('.footer-llama');
    
    // Stream states
    let salamandraText = '';
    let llamaText = '';
    currentSources = [];
    
    let salamandraStarted = false;
    let llamaStarted = false;
    
    // Open EventSource SSE Stream
    const encodedPregunta = encodeURIComponent(question);
    const url = `/api/chat?pregunta=${encodedPregunta}&conv_id=${currentConversationId}`;
    
    const eventSource = new EventSource(url);
    
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'init') {
                currentSources = data.sources;
                renderFooter(footerElSalamandra, "Cargando...", currentSources);
                renderFooter(footerElLlama, "Cargando...", currentSources);
            } 
            else if (data.type === 'token') {
                if (data.model === 'salamandra') {
                    if (!salamandraStarted) {
                        salamandraStarted = true;
                        responseBodySalamandra.innerHTML = '';
                    }
                    salamandraText += data.text;
                    queueRender('salamandra', salamandraText, responseBodySalamandra);
                } 
                else if (data.model === 'llama') {
                    if (!llamaStarted) {
                        llamaStarted = true;
                        responseBodyLlama.innerHTML = '';
                    }
                    llamaText += data.text;
                    queueRender('llama', llamaText, responseBodyLlama);
                }
            } 
            else if (data.type === 'done') {
                if (data.model === 'salamandra') {
                    renderFooter(footerElSalamandra, data.time + 's', currentSources);
                } 
                else if (data.model === 'llama') {
                    renderFooter(footerElLlama, data.time + 's', currentSources);
                }
                // Queue a render step to verify final scroll alignment
                queueRender('', null, null);
            } 
            else if (data.type === 'error') {
                if (data.model === 'salamandra') {
                    responseBodySalamandra.innerHTML = `<span style="color:red; font-weight:500;">${data.text}</span>`;
                    renderFooter(footerElSalamandra, 'Error', currentSources);
                } 
                else if (data.model === 'llama') {
                    responseBodyLlama.innerHTML = `<span style="color:red; font-weight:500;">${data.text}</span>`;
                    renderFooter(footerElLlama, 'Error', currentSources);
                }
                queueRender('', null, null);
            }
        } catch (err) {
            console.error("SSE token error:", err);
        }
    };
    
    eventSource.onerror = (err) => {
        console.log("SSE Stream ended.");
        eventSource.close();
        
        // Skeletons fallback cleanup
        if (!salamandraStarted && responseBodySalamandra.querySelector('.skeleton-container')) {
            responseBodySalamandra.innerHTML = '<span style="color:var(--text-muted);">Sin respuesta o error del servidor ADA.</span>';
            renderFooter(footerElSalamandra, '--', currentSources);
        }
        if (!llamaStarted && responseBodyLlama.querySelector('.skeleton-container')) {
            responseBodyLlama.innerHTML = '<span style="color:var(--text-muted);">Sin respuesta o error del servidor ADA.</span>';
            renderFooter(footerElLlama, '--', currentSources);
        }
        
        scrollToBottomIfNeeded();
        loadRecentChats();
    };
}

// ==========================================
// RENDER HELPERS (SKELETONS, FOOTERS)
// ==========================================
function createSkeleton() {
    return `
        <div class="skeleton-container">
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line" style="width: 80%;"></div>
            <div class="skeleton-line" style="width: 50%;"></div>
        </div>
    `;
}

function renderFooter(footerEl, timeStr, sources) {
    let sourceHtml = 'Fuente: --';
    
    if (sources && sources.length > 0) {
        const links = sources.map(src => {
            if (src.url) {
                return `<a href="${src.url}" target="_blank" title="Abrir trámite municipal">${src.name}</a>`;
            } else {
                return `<span>${src.name}</span>`;
            }
        }).join(', ');
        sourceHtml = `Fuente: ${links}`;
    }
    
    footerEl.innerHTML = `
        <span class="footer-time">Tiempo: ${timeStr}</span>
        <span class="footer-source">${sourceHtml}</span>
    `;
}

// ==========================================
// HISTORY DASHBOARD VIEW
// ==========================================
async function loadHistoryView() {
    switchView('history');
    
    try {
        const res = await fetch('/api/conversations');
        if (!res.ok) throw new Error("Error fetching conversations");
        const conversations = await res.json();
        
        historyItemsGrid.innerHTML = '';
        
        if (conversations.length === 0) {
            historyItemsGrid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted); background: var(--bg-card); border-radius: 12px; border: 1px solid var(--border-color);">
                    No hay consultas registradas en el historial. ¡Realice su primera consulta!
                </div>
            `;
            return;
        }
        
        conversations.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        
        conversations.forEach(conv => {
            const card = document.createElement('div');
            card.className = 'history-card';
            
            const dateObj = new Date(conv.timestamp);
            const formattedDate = dateObj.toLocaleDateString('es-ES', {
                year: 'numeric', month: 'long', day: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });
            
            const lastMsgText = conv.messages && conv.messages.length > 0 
                ? conv.messages[0].question 
                : "Sin preguntas.";
                
            card.innerHTML = `
                <div class="history-card-info">
                    <h4 class="history-card-title">${conv.title || "Consulta"}</h4>
                    <span style="font-size: 0.85rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical;">
                        ${lastMsgText}
                    </span>
                    <span class="history-card-date">${formattedDate}</span>
                </div>
                <div class="history-card-actions">
                    <button class="btn-delete-history" title="Eliminar consulta" data-id="${conv.id}">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            `;
            
            card.addEventListener('click', (e) => {
                if (e.target.closest('.btn-delete-history')) {
                    return;
                }
                loadConversation(conv.id);
            });
            
            const deleteBtn = card.querySelector('.btn-delete-history');
            deleteBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm(`¿Está seguro de que desea eliminar la consulta "${conv.title}"?`)) {
                    await deleteConversation(conv.id);
                }
            });
            
            historyItemsGrid.appendChild(card);
        });
    } catch (e) {
        console.error("History view error:", e);
        historyItemsGrid.innerHTML = '<div style="color:red; text-align:center;">Error al cargar el historial.</div>';
    }
}

async function deleteConversation(convId) {
    try {
        const res = await fetch(`/api/conversations/${convId}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error("Delete failed");
        
        await loadRecentChats();
        await loadHistoryView();
        
        if (currentConversationId === convId) {
            startNewChat();
        }
    } catch (e) {
        console.error(e);
        alert("No se pudo eliminar la consulta.");
    }
}

// ==========================================
// LIGHTWEIGHT MARKDOWN TO HTML CONVERTER
// ==========================================
function formatMarkdown(text) {
    if (!text) return "";
    
    let html = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
        
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    const lines = html.split("\n");
    let inList = false;
    let listType = null;
    let result = [];
    
    for (let line of lines) {
        const olMatch = line.match(/^(\d+)\.\s+(.*)/);
        const ulMatch = line.match(/^[-*]\s+(.*)/);
        
        if (olMatch) {
            if (!inList || listType !== 'ol') {
                if (inList) result.push(`</${listType}>`);
                result.push("<ol>");
                inList = true;
                listType = 'ol';
            }
            result.push(`<li>${olMatch[2]}</li>`);
        } else if (ulMatch) {
            if (!inList || listType !== 'ul') {
                if (inList) result.push(`</${listType}>`);
                result.push("<ul>");
                inList = true;
                listType = 'ul';
            }
            result.push(`<li>${ulMatch[1]}</li>`);
        } else {
            if (inList) {
                result.push(`</${listType}>`);
                inList = false;
                listType = null;
            }
            const trimmed = line.trim();
            if (trimmed) {
                if (trimmed.startsWith('# ')) {
                    result.push(`<h4>${trimmed.substring(2)}</h4>`);
                } else if (trimmed.startsWith('## ')) {
                    result.push(`<h5>${trimmed.substring(3)}</h5>`);
                } else {
                    result.push(`<p>${trimmed}</p>`);
                }
            }
        }
    }
    
    if (inList) {
        result.push(`</${listType}>`);
    }
    
    return result.join("\n");
}
