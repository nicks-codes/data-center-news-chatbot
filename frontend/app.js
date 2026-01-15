// Data Center News Chatbot - Frontend JavaScript

const API_BASE = window.location.origin;

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const audienceSelect = document.getElementById('audience-select');
const audiencePill = document.getElementById('audience-pill');
const newChatBtn = document.getElementById('new-chat-btn');
const sidebarNewChatBtn = document.getElementById('sidebar-new-chat-btn');
const conversationList = document.getElementById('conversation-list');
const totalArticles = document.getElementById('total-articles');
const indexedArticles = document.getElementById('indexed-articles');
const providerInfo = document.getElementById('provider-info');
const refreshBtn = document.getElementById('refresh-btn');
const scrapeBtn = document.getElementById('scrape-btn');
const sampleBtns = document.querySelectorAll('.sample-btn');
const helperChips = document.querySelectorAll('.helper-chip');

// State
let isLoading = false;
let hasShownWelcome = false;
let conversationId = localStorage.getItem('conversation_id') || null;
let audience = localStorage.getItem('audience') || 'Exec';
let transcript = [];
let conversations = [];
let activeStream = null;
let autoScroll = true;
let localMessageId = 0;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    setupEventListeners();
    restoreAudience();
    loadConversations();
    restoreConversation();
    autoGrowInput();
});

// Event Listeners
function setupEventListeners() {
    // Chat form submission
    chatForm.addEventListener('submit', handleChatSubmit);

    if (stopBtn) {
        stopBtn.addEventListener('click', stopStreaming);
    }
    
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
            updateAudiencePill();
        });
    }

    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => {
            startNewChat();
        });
    }

    if (sidebarNewChatBtn) {
        sidebarNewChatBtn.addEventListener('click', () => {
            startNewChat();
        });
    }

    helperChips.forEach((chip) => {
        chip.addEventListener('click', () => {
            const insert = chip.getAttribute('data-insert') || '';
            if (!insert) return;
            const current = chatInput.value.trim();
            chatInput.value = current ? `${current} ${insert}` : insert;
            chatInput.focus();
            autoGrowInput();
        });
    });

    if (chatMessages) {
        chatMessages.addEventListener('scroll', () => {
            const distance = chatMessages.scrollHeight - (chatMessages.scrollTop + chatMessages.clientHeight);
            autoScroll = distance < 140;
        });

        chatMessages.addEventListener('click', handleMessageActionClick);
    }

    if (conversationList) {
        conversationList.addEventListener('click', (e) => {
            const item = e.target.closest('.conversation-item');
            if (!item) return;
            const id = item.getAttribute('data-conversation-id');
            if (!id || id === conversationId) return;
            loadConversation(id);
        });
    }
}

function restoreAudience() {
    if (!audienceSelect) return;
    audienceSelect.value = audience || 'Exec';
    updateAudiencePill();
}

function updateAudiencePill() {
    if (audiencePill) {
        audiencePill.textContent = audience || 'Exec';
    }
}

function nextLocalId() {
    localMessageId += 1;
    return `m_${localMessageId}`;
}

function pushTranscriptItem(item) {
    const entry = { ...item, localId: item.localId || nextLocalId() };
    transcript.push(entry);
    return entry;
}

function updateTranscriptItem(localId, updates) {
    const idx = transcript.findIndex((m) => m.localId === localId);
    if (idx >= 0) {
        transcript[idx] = { ...transcript[idx], ...updates };
    }
}

async function loadConversations() {
    if (!conversationList) return;
    try {
        const response = await fetch(`${API_BASE}/api/conversations`);
        if (!response.ok) throw new Error('Failed to fetch conversations');
        const data = await response.json();
        conversations = Array.isArray(data.conversations) ? data.conversations : [];
        renderConversationList(conversations);
    } catch (e) {
        renderConversationList([]);
    }
}

function renderConversationList(items) {
    if (!conversationList) return;
    if (!items || items.length === 0) {
        conversationList.innerHTML = `<div class="conversation-updated">No chats yet</div>`;
        return;
    }
    conversationList.innerHTML = items.map((c) => {
        const title = escapeHtml(c.title || 'New chat');
        const time = formatRelativeTime(c.updated_at);
        const activeClass = c.id === conversationId ? 'active' : '';
        return `
            <button class="conversation-item ${activeClass}" data-conversation-id="${escapeHtml(c.id)}">
                <span class="conversation-title">${title}</span>
                <span class="conversation-updated">${escapeHtml(time)}</span>
            </button>
        `;
    }).join('');
}

async function restoreConversation() {
    if (conversationId) {
        await loadConversation(conversationId);
    }
}

async function loadConversation(id) {
    if (!id) return;
    try {
        stopStreaming();
        const response = await fetch(`${API_BASE}/api/conversations/${id}`);
        if (!response.ok) throw new Error('Failed to fetch conversation');
        const data = await response.json();
        conversationId = data.id;
        localStorage.setItem('conversation_id', conversationId);
        transcript = [];
        localMessageId = 0;
        chatMessages.innerHTML = '';
        hasShownWelcome = true;
        if (!data.messages || data.messages.length === 0) {
            hasShownWelcome = false;
            startNewChat();
            return;
        }
        for (const m of data.messages) {
            const entry = pushTranscriptItem({
                role: m.role,
                content: m.content,
                messageId: m.id,
            });
            addMessage(m.content, m.role, {
                messageId: m.id,
                localId: entry.localId,
            });
        }
        renderConversationList(conversations);
        scrollToBottom();
    } catch (e) {
        console.error('Error loading conversation:', e);
    }
}

function startNewChat() {
    stopStreaming();
    conversationId = null;
    localStorage.removeItem('conversation_id');
    transcript = [];
    localMessageId = 0;
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
    loadConversations();
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

    chatInput.value = '';
    autoGrowInput();
    await sendMessage({ query, regenerate: false });
}

// Add a message to the chat
function addMessage(content, role, options = {}) {
    const messageEl = document.createElement('div');
    const localId = options.localId || nextLocalId();
    messageEl.dataset.localId = localId;
    messageEl.dataset.role = role;
    messageEl.dataset.raw = content || '';
    if (options.messageId) {
        messageEl.dataset.messageId = String(options.messageId);
    }

    if (role === 'assistant') {
        renderAssistantMessage(messageEl, {
            content,
            sources: options.sources || [],
            followups: options.followups || [],
            quickReplies: options.quickReplies || [],
            meta: options.meta || null,
            isStreaming: !!options.isStreaming,
        });
    } else {
        messageEl.className = `message ${role}`;
        const safe = content
            .split('\n')
            .filter(p => p.trim())
            .map(p => `<p>${escapeHtml(p)}</p>`)
            .join('');
        messageEl.innerHTML = `<div class="message-content">${safe}</div>`;
    }

    chatMessages.appendChild(messageEl);
    scrollToBottom();
    return messageEl;
}

function renderAssistantMessage(messageEl, { content, sources, followups, quickReplies, meta, isStreaming }) {
    const hasClarifier = meta && meta.clarifying_question;
    messageEl.className = `message assistant${hasClarifier ? ' clarifier' : ''}`;
    messageEl.dataset.raw = content || '';
    messageEl.dataset.streaming = isStreaming ? 'true' : 'false';

    const formattedContent = renderAssistantMarkdown(content || '');
    const metaHtml = renderMetaHtml(meta, sources);
    const actionsHtml = renderActionsHtml(isStreaming);
    const sourcesHtml = renderSourcesHtml(sources);
    const quickRepliesHtml = renderQuickRepliesHtml(quickReplies);
    const followupsHtml = renderFollowupsHtml(followups);

    messageEl.innerHTML = `
        ${metaHtml}
        <div class="message-content">${formattedContent}</div>
        ${actionsHtml}
        ${sourcesHtml}
        ${quickRepliesHtml}
        ${followupsHtml}
    `;
}

function renderActionsHtml(isStreaming) {
    const disabled = isStreaming ? 'disabled' : '';
    return `
        <div class="message-actions">
            <button class="msg-action" data-action="copy" ${disabled}>Copy</button>
            <button class="msg-action" data-action="regenerate" ${disabled}>Regenerate</button>
            <button class="msg-action" data-action="thumbs-up" ${disabled}>👍</button>
            <button class="msg-action" data-action="thumbs-down" ${disabled}>👎</button>
        </div>
    `;
}

function renderSourcesHtml(sources = []) {
    if (!sources || sources.length === 0) return '';
    return `
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

function renderFollowupsHtml(followups = []) {
    if (!followups || followups.length === 0) return '';
    return `
        <div class="followups">
            ${followups.slice(0, 4).map((t) => `
                <button type="button" class="followup-chip" data-followup="${escapeHtml(String(t))}">
                    ${escapeHtml(String(t))}
                </button>
            `).join('')}
        </div>
    `;
}

function renderQuickRepliesHtml(replies = []) {
    if (!replies || replies.length === 0) return '';
    return `
        <div class="quick-replies">
            ${replies.slice(0, 3).map((t) => `
                <button type="button" class="quick-reply-chip" data-quick-reply="${escapeHtml(String(t))}">
                    ${escapeHtml(String(t))}
                </button>
            `).join('')}
        </div>
    `;
}

function renderMetaHtml(meta, sources = []) {
    if (!meta) return '';
    if (meta.clarifying_question) return '';
    const days = meta.time_window_days ? `last ${meta.time_window_days} days` : 'unknown';
    const used = (typeof meta.sources_used === 'number') ? meta.sources_used : (sources ? sources.length : 0);
    const thin = !!meta.coverage_thin;
    const widened = meta.widened_to_days;
    const note = thin && widened ? `Coverage is thin; widened to ${widened} days.` : '';

    return `
        <div class="answer-meta">
            <span class="meta-pill">Time window: ${escapeHtml(days)}</span>
            <span class="meta-pill">Sources used: ${escapeHtml(String(used))}</span>
            ${note ? `<span class="meta-pill warn">${escapeHtml(note)}</span>` : ''}
        </div>
    `;
}

function setLoadingState(loading) {
    isLoading = loading;
    sendBtn.disabled = loading;
    if (stopBtn) {
        stopBtn.hidden = !loading;
    }
}

function stopStreaming() {
    if (activeStream) {
        activeStream.abort();
        activeStream = null;
    }
    const streamingEl = chatMessages.querySelector('.message.assistant[data-streaming="true"]');
    if (streamingEl) {
        renderAssistantMessage(streamingEl, {
            content: streamingEl.dataset.raw || '',
            sources: [],
            followups: [],
            quickReplies: [],
            meta: null,
            isStreaming: false,
        });
    }
    setLoadingState(false);
}

function autoGrowInput() {
    if (!chatInput) return;
    chatInput.style.height = 'auto';
    const next = Math.min(chatInput.scrollHeight, 220);
    chatInput.style.height = `${next}px`;
}

async function sendMessage({ query, regenerate }) {
    if (!query || isLoading) return;

    // Clear welcome message on first query
    if (!hasShownWelcome) {
        const welcomeMsg = chatMessages.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }
        hasShownWelcome = true;
    }

    if (!regenerate) {
        const userEntry = pushTranscriptItem({ role: 'user', content: query });
        addMessage(query, 'user', { localId: userEntry.localId });
    }

    const assistantEntry = pushTranscriptItem({ role: 'assistant', content: '' });
    const assistantEl = addMessage('', 'assistant', {
        localId: assistantEntry.localId,
        isStreaming: true,
        sources: [],
        followups: [],
        meta: null,
    });

    setLoadingState(true);

    try {
        await streamResponse({
            query,
            regenerate,
            assistantEl,
            assistantEntry,
        });
    } catch (error) {
        if (error && error.name === 'AbortError') {
            return;
        }
        console.error('Error sending message:', error);
        addErrorMessage('Sorry, there was an error processing your request. Please try again.');
    } finally {
        setLoadingState(false);
        chatInput.focus();
    }
}

async function streamResponse({ query, regenerate, assistantEl, assistantEntry }) {
    const controller = new AbortController();
    activeStream = controller;
    let buffer = '';
    let fullText = '';
    try {
        const response = await fetch(`${API_BASE}/api/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',
            },
            body: JSON.stringify({
                query,
                audience,
                conversation_id: conversationId,
                regenerate: !!regenerate,
            }),
            signal: controller.signal,
        });

        if (!response.ok || !response.body) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        const handleEvent = (eventType, data) => {
            if (eventType === 'token') {
                const text = (data && data.text) ? String(data.text) : '';
                if (!text) return;
                fullText += text;
                updateAssistantContent(assistantEl, fullText, assistantEntry.localId);
            }
            if (eventType === 'done') {
                if (data && data.error) {
                    addErrorMessage('Sorry, there was an error generating the response.');
                    return;
                }
                const finalText = (data && data.final_text) ? String(data.final_text) : fullText;
                fullText = finalText;

                if (data && data.conversation_id) {
                    conversationId = data.conversation_id;
                    localStorage.setItem('conversation_id', conversationId);
                }

                if (data && data.message_id) {
                    assistantEl.dataset.messageId = String(data.message_id);
                    updateTranscriptItem(assistantEntry.localId, { messageId: data.message_id });
                }
                updateTranscriptItem(assistantEntry.localId, { content: fullText });

                const meta = data.meta || null;
                const quickReplies = meta && Array.isArray(meta.quick_replies) ? meta.quick_replies : [];
                renderAssistantMessage(assistantEl, {
                    content: fullText,
                    sources: data.sources || [],
                    followups: data.suggested_followups || [],
                    quickReplies,
                    meta,
                    isStreaming: false,
                });
                loadConversations();
            }
        };

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop();
            for (const part of parts) {
                const lines = part.split('\n');
                let eventType = 'message';
                let dataStr = '';
                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        eventType = line.slice(6).trim();
                    } else if (line.startsWith('data:')) {
                        dataStr += line.slice(5).trim();
                    }
                }
                if (!dataStr) continue;
                try {
                    const data = JSON.parse(dataStr);
                    handleEvent(eventType, data);
                } catch (e) {
                    console.error('Error parsing SSE data:', e);
                }
            }
            scrollToBottom();
        }
    } finally {
        activeStream = null;
    }
}

function updateAssistantContent(messageEl, content, localId) {
    const contentEl = messageEl.querySelector('.message-content');
    if (contentEl) {
        contentEl.innerHTML = renderAssistantMarkdown(content || '');
    }
    messageEl.dataset.raw = content || '';
    updateTranscriptItem(localId, { content });
}

function findPreviousUserMessage(localId) {
    const idx = transcript.findIndex((m) => m.localId === localId);
    if (idx < 0) return null;
    for (let i = idx - 1; i >= 0; i -= 1) {
        if (transcript[i].role === 'user') {
            return transcript[i];
        }
    }
    return null;
}

async function handleMessageActionClick(e) {
    const followupBtn = e.target.closest('.followup-chip');
    if (followupBtn) {
        const text = followupBtn.getAttribute('data-followup') || '';
        if (text) {
            sendMessage({ query: text, regenerate: false });
        }
        return;
    }

    const quickBtn = e.target.closest('.quick-reply-chip');
    if (quickBtn) {
        const text = quickBtn.getAttribute('data-quick-reply') || '';
        if (text) {
            sendMessage({ query: text, regenerate: false });
        }
        return;
    }

    const actionBtn = e.target.closest('.msg-action');
    if (!actionBtn) return;
    const messageEl = actionBtn.closest('.message');
    if (!messageEl) return;
    const action = actionBtn.getAttribute('data-action');

    if (action === 'copy') {
        const raw = messageEl.dataset.raw || '';
        try {
            await navigator.clipboard.writeText(raw);
            showToast('Copied to clipboard', 'success');
        } catch (err) {
            showToast('Copy failed', 'error');
        }
        return;
    }

    if (action === 'regenerate') {
        const prev = findPreviousUserMessage(messageEl.dataset.localId || '');
        if (!prev || isLoading) return;
        sendMessage({ query: prev.content, regenerate: true });
        return;
    }

    if (action === 'thumbs-up' || action === 'thumbs-down') {
        const messageId = messageEl.dataset.messageId;
        if (!messageId || !conversationId) return;
        const rating = action === 'thumbs-up' ? 'up' : 'down';
        await submitFeedback({ conversationId, messageId, rating });
        const buttons = messageEl.querySelectorAll('.msg-action');
        buttons.forEach((btn) => {
            if (btn.getAttribute('data-action') === action) {
                btn.classList.add('active');
            } else if (btn.getAttribute('data-action') === 'thumbs-up' || btn.getAttribute('data-action') === 'thumbs-down') {
                btn.classList.remove('active');
            }
        });
    }
}

async function submitFeedback({ conversationId, messageId, rating }) {
    try {
        await fetch(`${API_BASE}/api/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: conversationId,
                message_id: Number(messageId),
                rating,
            }),
        });
    } catch (e) {
        console.error('Error submitting feedback:', e);
    }
}

function formatRelativeTime(value) {
    if (!value) return 'Just now';
    const ts = new Date(value).getTime();
    if (Number.isNaN(ts)) return 'Just now';
    const diffMs = Date.now() - ts;
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
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
    if (autoScroll) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
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

chatInput.addEventListener('input', () => {
    autoGrowInput();
});
