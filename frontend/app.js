// Data Center News Chatbot - Frontend JavaScript

const API_BASE = window.location.origin;

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const totalArticles = document.getElementById('total-articles');
const indexedArticles = document.getElementById('indexed-articles');
const providerInfo = document.getElementById('provider-info');
const refreshBtn = document.getElementById('refresh-btn');
const scrapeBtn = document.getElementById('scrape-btn');
const sampleBtns = document.querySelectorAll('.sample-btn');

// State
let isLoading = false;
let hasShownWelcome = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    setupEventListeners();
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
            body: JSON.stringify({ query }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Remove loading
        loadingEl.remove();
        
        // Add assistant message
        addMessage(data.answer, 'assistant', data.sources);
        
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
function addMessage(content, role, sources = []) {
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
        sourcesHtml = `
            <div class="sources">
                <div class="sources-header">📚 Sources</div>
                ${sources.map(source => `
                    <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener" class="source-item">
                        <span class="source-title">${escapeHtml(source.title)}</span>
                        <span class="source-name">${escapeHtml(source.source)}</span>
                    </a>
                `).join('')}
            </div>
        `;
    }
    
    messageEl.innerHTML = `
        <div class="message-content">
            ${formattedContent}
        </div>
        ${sourcesHtml}
    `;
    
    chatMessages.appendChild(messageEl);
    // Ensure links in assistant markdown open safely in a new tab
    if (role === 'assistant') {
        messageEl.querySelectorAll('.message-content a').forEach(a => {
            a.setAttribute('target', '_blank');
            a.setAttribute('rel', 'noopener noreferrer');
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

    // If markdown libs aren't available, fall back to simple paragraph formatting.
    if (!window.marked || !window.DOMPurify) {
        return raw
            .split('\n')
            .filter(p => p.trim())
            .map(p => `<p>${escapeHtml(p)}</p>`)
            .join('');
    }

    // Configure for readable chat output
    window.marked.setOptions({
        gfm: true,
        breaks: true,
        headerIds: false,
        mangle: false,
    });

    const html = window.marked.parse(raw);
    return window.DOMPurify.sanitize(html, {
        USE_PROFILES: { html: true },
    });
}

// Handle Enter key in input
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});
