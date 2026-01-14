// Data Center News Chatbot - Frontend JavaScript

const API_BASE = window.location.origin;

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const audienceSelect = document.getElementById('audience-select');
const newChatBtn = document.getElementById('new-chat-btn');
const totalArticles = document.getElementById('total-articles');
const indexedArticles = document.getElementById('indexed-articles');
const providerInfo = document.getElementById('provider-info');
const refreshBtn = document.getElementById('refresh-btn');
const scrapeBtn = document.getElementById('scrape-btn');
const sampleBtns = document.querySelectorAll('.sample-btn');

// State
let isLoading = false;
let hasShownWelcome = false;
let conversationId = localStorage.getItem('conversation_id') || null;
let audience = localStorage.getItem('audience') || 'Exec';
let transcript = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    setupEventListeners();
    restoreAudience();
    restoreTranscript();
});

// Event Listeners
function setupEventListeners() {
    // Chat form submission
    chatForm.addEventListener('submit', handleChatSubmit);
    
    // Sample question buttons
    sampleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.dataset.question;
            if (question) {
                chatInput.value = question;
                handleChatSubmit(new Event('submit'));
            }
        });
    });
    
    // Refresh stats button
    refreshBtn.addEventListener('click', () => {
        fetchStats();
        showToast('Stats refreshed!', 'success');
    });
    
    // Manual scrape button
    scrapeBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`${API_BASE}/api/scrape`, { method: 'POST' });
            if (response.ok) {
                showToast('Scraping started! Check back in a few minutes.', 'success');
            } else {
                showToast('Could not start scraping', 'error');
            }
        } catch (error) {
            showToast('Error triggering scrape', 'error');
        }
    });
    
    // Auto-refresh stats every 60 seconds
    setInterval(fetchStats, 60000);

    if (audienceSelect) {
        audienceSelect.addEventListener('change', () => {
            audience = audienceSelect.value || 'Exec';
            localStorage.setItem('audience', audience);
        });
    }

    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => {
            startNewChat();
        });
    }
}

function restoreAudience() {
    if (!audienceSelect) return;
    audienceSelect.value = audience || 'Exec';
}

function restoreTranscript() {
    try {
        const raw = localStorage.getItem('chat_transcript');
        transcript = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(transcript) || transcript.length === 0) return;

        // Remove welcome message and re-render transcript
        const welcomeMsg = chatMessages.querySelector('.welcome-message');
        if (welcomeMsg) welcomeMsg.remove();
        hasShownWelcome = true;

        for (const m of transcript) {
            addMessage(m.content, m.role, m.sources || [], m.followups || [], m.meta || null);
        }
    } catch (e) {
        transcript = [];
    }
}

function persistTranscriptItem(item) {
    try {
        transcript.push(item);
        // Keep it bounded so localStorage doesn't explode
        if (transcript.length > 60) transcript = transcript.slice(transcript.length - 60);
        localStorage.setItem('chat_transcript', JSON.stringify(transcript));
    } catch (e) {
        // ignore
    }
}

function startNewChat() {
    conversationId = null;
    localStorage.removeItem('conversation_id');
    transcript = [];
    localStorage.removeItem('chat_transcript');
    chatMessages.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">🏢</div>
            <h3>Welcome to the Data Center News Chatbot!</h3>
            <p>I can answer questions about:</p>
            <ul>
                <li>📰 Latest data center news and developments</li>
                <li>🏗️ Construction and expansion projects</li>
                <li>💼 M&A activity and market trends</li>
                <li>🌱 Sustainability initiatives</li>
                <li>⚡ Technology innovations (cooling, power, AI)</li>
            </ul>
            <p class="welcome-tip">Try one of the sample questions or ask your own!</p>
        </div>
    `;
    hasShownWelcome = false;
    chatInput.focus();
}

// Fetch and display stats
async function fetchStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        if (!response.ok) throw new Error('Failed to fetch stats');
        
        const data = await response.json();
        
        totalArticles.textContent = data.total_articles || 0;
        // In lightweight mode, embeddings are disabled and "Indexed" would always show 0.
        // Show a clearer indicator instead of implying something is broken.
        if ((data.embedding_provider || '').toLowerCase() === 'none') {
            indexedArticles.textContent = '—';
        } else {
            indexedArticles.textContent = data.articles_with_embeddings || 0;
        }
        
        if ((data.embedding_provider || '').toLowerCase() === 'none') {
            providerInfo.textContent = `Provider: ${data.ai_provider || 'unknown'} (keyword mode)`;
            providerInfo.classList.remove('free');
        } else if (data.is_free) {
            providerInfo.textContent = '✅ Using free AI providers + embeddings';
            providerInfo.classList.add('free');
        } else {
            providerInfo.textContent = `Provider: ${data.ai_provider || 'unknown'}`;
            providerInfo.classList.remove('free');
        }
    } catch (error) {
        console.error('Error fetching stats:', error);
        totalArticles.textContent = '-';
        indexedArticles.textContent = '-';
    }
}

// Handle chat form submission
async function handleChatSubmit(e) {
    e.preventDefault();
    
    const query = chatInput.value.trim();
    if (!query || isLoading) return;
    
    // Clear welcome message on first query
    if (!hasShownWelcome) {
        const welcomeMsg = chatMessages.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }
        hasShownWelcome = true;
    }
    
    // Add user message
    addMessage(query, 'user');
    persistTranscriptItem({ role: 'user', content: query, sources: [], followups: [] });
    chatInput.value = '';
    
    // Show loading
    isLoading = true;
    sendBtn.disabled = true;
    const loadingEl = addLoadingMessage();
    
    try {
        const response = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query,
                audience,
                conversation_id: conversationId,
            }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();

        if (data && data.conversation_id) {
            conversationId = data.conversation_id;
            localStorage.setItem('conversation_id', conversationId);
        }
        
        // Remove loading
        loadingEl.remove();
        
        // Add assistant message
        addMessage(data.answer, 'assistant', data.sources, data.suggested_followups || [], data.meta || null);
        persistTranscriptItem({
            role: 'assistant',
            content: data.answer,
            sources: data.sources || [],
            followups: data.suggested_followups || [],
            meta: data.meta || null,
        });
        
    } catch (error) {
        console.error('Error sending message:', error);
        loadingEl.remove();
        addErrorMessage('Sorry, there was an error processing your request. Please try again.');
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

// Add a message to the chat
function addMessage(content, role, sources = [], followups = [], meta = null) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;
    
    let formattedContent = '';

    if (role === 'assistant') {
        formattedContent = renderAssistantMarkdown(content);
    } else {
        // User messages: keep simple + safe
        formattedContent = content
            .split('\n')
            .filter(p => p.trim())
            .map(p => `<p>${escapeHtml(p)}</p>`)
            .join('');
    }
    
    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        // IMPORTANT: do NOT dedupe/reorder/cap in the UI. Backend controls source ordering and cap,
        // so citations like [6] always map to the 6th source shown here.
        sourcesHtml = `
            <div class="sources">
                <div class="sources-header">
                    <span>Sources</span>
                    <span class="sources-count">${sources.length}</span>
                </div>
                <div class="sources-list">
                    ${sources.map((source, idx) => `
                        <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer" class="source-item">
                            <span class="source-idx">[${idx + 1}]</span>
                            <span class="source-title">${escapeHtml(source.title)}</span>
                            <span class="source-name">${escapeHtml(source.source)}</span>
                        </a>
                    `).join('')}
                </div>
            </div>
        `;
    }

    let followupsHtml = '';
    if (role === 'assistant' && followups && followups.length > 0) {
        followupsHtml = `
            <div class="followups">
                ${followups.slice(0, 4).map((t) => `
                    <button type="button" class="followup-chip" data-followup="${escapeHtml(String(t))}">
                        ${escapeHtml(String(t))}
                    </button>
                `).join('')}
            </div>
        `;
    }
    
    let metaHtml = '';
    if (role === 'assistant' && meta) {
        const days = meta.time_window_days ? `last ${meta.time_window_days} days` : 'unknown';
        const used = (typeof meta.sources_used === 'number') ? meta.sources_used : (sources ? sources.length : 0);
        const thin = !!meta.coverage_thin;
        const widened = meta.widened_to_days;
        const note = thin && widened ? `Coverage is thin; widened to ${widened} days.` : '';

        metaHtml = `
            <div class="answer-meta">
                <span class="meta-pill">Time window: ${escapeHtml(days)}</span>
                <span class="meta-pill">Sources used: ${escapeHtml(String(used))}</span>
                ${note ? `<span class="meta-pill warn">${escapeHtml(note)}</span>` : ''}
            </div>
        `;
    }

    messageEl.innerHTML = `
        ${metaHtml}
        <div class="message-content">
            ${formattedContent}
        </div>
        ${sourcesHtml}
        ${followupsHtml}
    `;
    
    chatMessages.appendChild(messageEl);

    // Wire up follow-up chip clicks
    if (role === 'assistant') {
        const chips = messageEl.querySelectorAll('.followup-chip');
        chips.forEach((btn) => {
            btn.addEventListener('click', () => {
                const text = btn.getAttribute('data-followup') || '';
                if (!text) return;
                chatInput.value = text;
                chatInput.focus();
                chatForm.dispatchEvent(new Event('submit'));
            });
        });
    }
    scrollToBottom();
}

// Add loading message
function addLoadingMessage() {
    const loadingEl = document.createElement('div');
    loadingEl.className = 'message assistant loading';
    loadingEl.innerHTML = `
        <div class="loading">
            <span>Searching knowledge base</span>
            <div class="loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(loadingEl);
    scrollToBottom();
    return loadingEl;
}

// Add error message
function addErrorMessage(message) {
    const errorEl = document.createElement('div');
    errorEl.className = 'error-message';
    errorEl.textContent = message;
    chatMessages.appendChild(errorEl);
    scrollToBottom();
}

// Scroll to bottom of chat
function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Show toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderAssistantMarkdown(text) {
    const raw = (text || '').toString();

    // Markdown-lite renderer (no CDN deps, safe by default)
    const lines = raw.split(/\r?\n/);
    let html = '';
    let inUl = false;
    let inOl = false;

    const closeLists = () => {
        if (inUl) {
            html += '</ul>';
            inUl = false;
        }
        if (inOl) {
            html += '</ol>';
            inOl = false;
        }
    };

    for (const originalLine of lines) {
        const line = (originalLine || '').replace(/\s+$/, '');
        const trimmed = line.trim();

        if (!trimmed) {
            closeLists();
            // Preserve section breaks between blocks
            html += '<div class="md-break"></div>';
            continue;
        }

        // Headings
        const h3 = trimmed.match(/^##\s+(.*)$/);
        const h4 = trimmed.match(/^###\s+(.*)$/);
        if (h4) {
            closeLists();
            html += `<h3>${renderInline(h4[1])}</h3>`;
            continue;
        }
        if (h3) {
            closeLists();
            html += `<h2>${renderInline(h3[1])}</h2>`;
            continue;
        }

        // Bullets (accept '-' '*' and '•')
        const ul = trimmed.match(/^[-*•]\s+(.*)$/);
        if (ul) {
            if (inOl) {
                html += '</ol>';
                inOl = false;
            }
            if (!inUl) {
                html += '<ul>';
                inUl = true;
            }
            html += `<li>${renderInline(ul[1])}</li>`;
            continue;
        }

        // Numbered list
        const ol = trimmed.match(/^\d+\.\s+(.*)$/);
        if (ol) {
            if (inUl) {
                html += '</ul>';
                inUl = false;
            }
            if (!inOl) {
                html += '<ol>';
                inOl = true;
            }
            html += `<li>${renderInline(ol[1])}</li>`;
            continue;
        }

        closeLists();
        html += `<p>${renderInline(trimmed)}</p>`;
    }

    closeLists();
    return html;
}

function renderInline(raw) {
    // 1) Handle inline code by splitting on backticks
    const parts = String(raw || '').split('`');
    let out = '';
    for (let i = 0; i < parts.length; i++) {
        const escaped = escapeHtml(parts[i]);
        if (i % 2 === 1) {
            out += `<code>${escaped}</code>`;
        } else {
            out += escaped;
        }
    }

    // 2) Bold **text**
    out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // 3) Style citations like [1]
    out = out.replace(/\[(\d+)\]/g, '<span class="cite">[$1]</span>');

    return out;
}

// Handle Enter key in input
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});
