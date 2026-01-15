// News tab logic
const digestContent = document.getElementById('digest-content');
const digestSources = document.getElementById('digest-sources');
const digestMeta = document.getElementById('digest-meta');
const storiesList = document.getElementById('stories-list');
const windowSelect = document.getElementById('news-window');
const marketSelect = document.getElementById('news-market');
const topicSelect = document.getElementById('news-topic');
const summariesBtn = document.getElementById('summaries-btn');

let storiesState = [];
let newsLoadedOnce = false;

window.addEventListener('news:activate', () => {
    if (!newsLoadedOnce) {
        loadNews();
        newsLoadedOnce = true;
    }
});

if (windowSelect) {
    windowSelect.addEventListener('change', () => {
        loadNews();
    });
}
if (marketSelect) {
    marketSelect.addEventListener('change', () => {
        loadNews();
    });
}
if (topicSelect) {
    topicSelect.addEventListener('change', () => {
        loadNews();
    });
}
if (summariesBtn) {
    summariesBtn.addEventListener('click', () => {
        generateAllSummaries();
    });
}

async function loadNews() {
    await Promise.all([loadDigest(), loadStories()]);
}

function currentWindowDays() {
    return parseInt(windowSelect?.value || '1', 10);
}

function todayDate() {
    return new Date().toISOString().slice(0, 10);
}

async function loadDigest() {
    if (!digestContent) return;
    digestContent.innerHTML = '<p>Loading digest...</p>';
    digestSources.innerHTML = '';
    if (digestMeta) digestMeta.textContent = '';

    try {
        const params = new URLSearchParams({
            date: todayDate(),
            audience: 'DC_RE',
            days: String(currentWindowDays()),
        });
        const response = await fetch(`${API_BASE}/api/news/digest?${params.toString()}`);
        if (!response.ok) throw new Error('Digest fetch failed');
        const data = await response.json();
        const markdown = data.content_md || '';
        digestContent.innerHTML = renderNewsMarkdown(markdown);
        renderDigestSources(data.sources || []);
        if (digestMeta) {
            const days = data.meta?.window_days || currentWindowDays();
            const coverage = data.meta?.coverage_thin ? 'Coverage thin' : 'Coverage ok';
            digestMeta.textContent = `${days}d window • ${coverage}`;
        }
    } catch (err) {
        digestContent.innerHTML = '<p>Unable to load digest.</p>';
    }
}

function renderDigestSources(sources) {
    if (!digestSources) return;
    if (!sources || sources.length === 0) {
        digestSources.innerHTML = '';
        return;
    }
    digestSources.innerHTML = `
        <div class="sources">
            <div class="sources-header">
                <span>Sources</span>
                <span class="sources-count">${sources.length}</span>
            </div>
            <div class="sources-list">
                ${sources.map((source, idx) => `
                    <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer" class="source-item">
                        <span class="source-idx">[${idx + 1}]</span>
                        <span class="source-title">${escapeHtml(source.title || '')}</span>
                        <span class="source-name">${escapeHtml(source.source || '')}</span>
                    </a>
                `).join('')}
            </div>
        </div>
    `;
}

async function loadStories() {
    if (!storiesList) return;
    storiesList.innerHTML = '<p>Loading stories...</p>';
    const params = new URLSearchParams({
        days: String(currentWindowDays()),
        limit: '25',
    });
    if (marketSelect?.value) params.append('market', marketSelect.value);
    if (topicSelect?.value) params.append('topic', topicSelect.value);

    try {
        const response = await fetch(`${API_BASE}/api/news/stories?${params.toString()}`);
        if (!response.ok) throw new Error('Stories fetch failed');
        const data = await response.json();
        storiesState = Array.isArray(data.stories) ? data.stories : [];
        renderStories(storiesState);
    } catch (err) {
        storiesList.innerHTML = '<p>Unable to load stories.</p>';
    }
}

function renderStories(items) {
    if (!items || items.length === 0) {
        storiesList.innerHTML = '<p>No stories found for this window.</p>';
        return;
    }
    storiesList.innerHTML = items.map((story) => renderStoryCard(story)).join('');
    storiesList.querySelectorAll('.summary-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-article-id');
            if (!id) return;
            btn.disabled = true;
            await generateStorySummary(id);
            btn.disabled = false;
        });
    });
}

function renderStoryCard(story) {
    const summary = story.summary_md ? renderNewsMarkdown(story.summary_md) : '<p>Summary not generated yet.</p>';
    const factsHtml = renderKeyFacts(story.key_facts || {});
    const dateText = story.published_date ? new Date(story.published_date).toLocaleDateString() : 'Unknown date';
    const openUrl = story.open_url || story.url || '#';
    const summaryAction = story.summary_md
        ? ''
        : `<button class="summary-btn" data-article-id="${escapeHtml(String(story.id))}">Generate summary</button>`;

    return `
        <div class="story-card">
            <div class="story-title">${escapeHtml(story.title || '')}</div>
            <div class="story-meta">
                <span>${escapeHtml(story.source || '')}</span>
                <span>•</span>
                <span>${escapeHtml(dateText)}</span>
            </div>
            <div class="story-summary">${summary}</div>
            ${factsHtml}
            <div class="story-actions">
                ${summaryAction}
                <a class="story-link" href="${escapeHtml(openUrl)}" target="_blank" rel="noopener noreferrer">Open source</a>
            </div>
        </div>
    `;
}

function renderKeyFacts(facts) {
    if (!facts || typeof facts !== 'object') return '';
    const entries = Object.entries(facts).filter(([, value]) => value !== null && value !== '' && value !== undefined);
    if (entries.length === 0) return '';
    return `
        <div class="story-facts">
            ${entries.map(([key, value]) => `
                <div class="story-fact">${formatFactLabel(key)}: ${escapeHtml(String(value))}</div>
            `).join('')}
        </div>
    `;
}

function formatFactLabel(key) {
    return String(key)
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

async function generateStorySummary(articleId) {
    try {
        const response = await fetch(`${API_BASE}/api/news/stories/${articleId}/summarize`, {
            method: 'POST',
        });
        if (!response.ok) throw new Error('Summary failed');
        const data = await response.json();
        const idx = storiesState.findIndex((s) => String(s.id) === String(articleId));
        if (idx >= 0) {
            storiesState[idx].summary_md = data.summary_md;
            storiesState[idx].key_facts = data.key_facts || {};
            renderStories(storiesState);
        }
    } catch (err) {
        console.error('Summary generation failed', err);
    }
}

async function generateAllSummaries() {
    const pending = storiesState.filter((s) => !s.summary_md);
    if (pending.length === 0) return;

    const concurrency = 3;
    let index = 0;

    async function worker() {
        while (index < pending.length) {
            const item = pending[index];
            index += 1;
            await generateStorySummary(item.id);
        }
    }

    const workers = Array.from({ length: concurrency }).map(() => worker());
    await Promise.all(workers);
}

function renderNewsMarkdown(text) {
    if (typeof renderAssistantMarkdown === 'function') {
        return renderAssistantMarkdown(text || '');
    }
    return `<p>${escapeHtml(text || '')}</p>`;
}
