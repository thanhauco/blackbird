/**
 * Blackbird Search Engine - Frontend Application
 */

// API Base URL
const API_BASE = '';

// State
let currentView = 'search';

// DOM Elements
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const filterLanguage = document.getElementById('filter-language');
const filterLimit = document.getElementById('filter-limit');
const resultsContainer = document.getElementById('results-container');
const resultsList = document.getElementById('results-list');
const resultsCount = document.getElementById('results-count');
const resultsTime = document.getElementById('results-time');
const emptyState = document.getElementById('empty-state');
const loadingOverlay = document.getElementById('loading-overlay');
const toastContainer = document.getElementById('toast-container');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initSearch();
    initIndex();
    initStats();
    initKeyboardShortcuts();
});

// Navigation
function initNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const view = link.dataset.view;
            switchView(view);
        });
    });
}

function switchView(view) {
    currentView = view;

    // Update nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.view === view);
    });

    // Update views
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.id === `${view}-view`);
    });

    // Load data for stats view
    if (view === 'stats') {
        loadStats();
    }
}

// Search
function initSearch() {
    // Search button click
    searchBtn.addEventListener('click', performSearch);

    // Enter key in search input
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    // Example queries
    document.querySelectorAll('.example-query').forEach(btn => {
        btn.addEventListener('click', () => {
            searchInput.value = btn.dataset.query;
            performSearch();
        });
    });
}

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) {
        showToast('Please enter a search query', 'error');
        return;
    }

    const language = filterLanguage.value;
    const limit = filterLimit.value;

    showLoading('Searching...');

    try {
        const params = new URLSearchParams({
            q: query,
            limit: limit
        });

        if (language) {
            params.append('language', language);
        }

        const response = await fetch(`${API_BASE}/search?${params}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Search failed');
        }

        displayResults(data);
    } catch (error) {
        console.error('Search error:', error);
        showToast(`Search failed: ${error.message}`, 'error');
    } finally {
        hideLoading();
    }
}

function displayResults(data) {
    const { query, total_results, results, took_ms, shards_queried } = data;

    if (total_results === 0) {
        resultsContainer.classList.add('hidden');
        emptyState.classList.remove('hidden');
        emptyState.querySelector('h3').textContent = 'No results found';
        emptyState.querySelector('p').textContent = `No matches for "${query}"`;
        return;
    }

    emptyState.classList.add('hidden');
    resultsContainer.classList.remove('hidden');

    resultsCount.textContent = `${total_results} result${total_results !== 1 ? 's' : ''}`;
    resultsTime.textContent = `${took_ms.toFixed(1)}ms across ${shards_queried} shards`;

    resultsList.innerHTML = results.map(result => createResultCard(result)).join('');
}

function createResultCard(result) {
    const { doc_id, repo_id, path, language, score, matched_ngrams, has_symbol_match, snippet } = result;

    return `
        <div class="result-card">
            <div class="result-header">
                <span class="result-path">${escapeHtml(path)}</span>
                <span class="result-score">
                    <span>⭐</span>
                    <span>${score.toFixed(2)}</span>
                </span>
            </div>
            <div class="result-meta">
                <span class="result-badge">${language || 'unknown'}</span>
                <span class="result-badge">Matched: ${matched_ngrams} ngrams</span>
                ${has_symbol_match ? '<span class="result-badge symbol">Symbol Match</span>' : ''}
            </div>
            ${snippet ? `<div class="result-snippet">${escapeHtml(snippet)}</div>` : ''}
        </div>
    `;
}

// Index
function initIndex() {
    const indexBtn = document.getElementById('index-btn');
    const repoPath = document.getElementById('repo-path');
    const repoId = document.getElementById('repo-id');
    const indexResult = document.getElementById('index-result');

    indexBtn.addEventListener('click', async () => {
        const path = repoPath.value.trim();
        if (!path) {
            showToast('Please enter a repository path', 'error');
            return;
        }

        showLoading('Indexing repository...');

        try {
            const response = await fetch(`${API_BASE}/index/repo`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    path: path,
                    repo_id: repoId.value.trim() || null
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Indexing failed');
            }

            indexResult.classList.remove('hidden', 'error');
            indexResult.innerHTML = `
                <h4>✅ Repository Indexed Successfully</h4>
                <p><strong>Repository ID:</strong> ${data.repo_id}</p>
                <p><strong>Documents Indexed:</strong> ${data.documents_indexed}</p>
                <p><strong>Documents Skipped:</strong> ${data.documents_skipped}</p>
                <p><strong>Duration:</strong> ${data.duration_seconds.toFixed(2)}s</p>
                ${data.errors.length > 0 ? `<p><strong>Errors:</strong> ${data.errors.length}</p>` : ''}
            `;

            showToast('Repository indexed successfully!', 'success');
        } catch (error) {
            console.error('Index error:', error);
            indexResult.classList.remove('hidden');
            indexResult.classList.add('error');
            indexResult.innerHTML = `
                <h4>❌ Indexing Failed</h4>
                <p>${escapeHtml(error.message)}</p>
            `;
            showToast(`Indexing failed: ${error.message}`, 'error');
        } finally {
            hideLoading();
        }
    });
}

// Stats
function initStats() {
    document.getElementById('compact-btn').addEventListener('click', async () => {
        showLoading('Running compaction...');
        try {
            const response = await fetch(`${API_BASE}/admin/compact`, { method: 'POST' });
            if (response.ok) {
                showToast('Compaction completed', 'success');
                loadStats();
            } else {
                throw new Error('Compaction failed');
            }
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            hideLoading();
        }
    });

    document.getElementById('save-btn').addEventListener('click', async () => {
        showLoading('Saving index...');
        try {
            const response = await fetch(`${API_BASE}/admin/save`, { method: 'POST' });
            if (response.ok) {
                showToast('Index saved', 'success');
            } else {
                throw new Error('Save failed');
            }
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            hideLoading();
        }
    });

    document.getElementById('refresh-stats-btn').addEventListener('click', loadStats);
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load stats');
        }

        document.getElementById('stat-documents').textContent = formatNumber(data.total_documents);
        document.getElementById('stat-ngrams').textContent = formatNumber(data.total_ngrams);
        document.getElementById('stat-shards').textContent = data.num_shards;

        const tableBody = document.getElementById('shards-table-body');
        tableBody.innerHTML = data.shards.map(shard => `
            <tr>
                <td>Shard ${shard.shard_id}</td>
                <td>${formatNumber(shard.documents)}</td>
                <td>${formatNumber(shard.ngrams)}</td>
                <td>${shard.segments}</td>
                <td>${shard.pending}</td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Stats error:', error);
        showToast(`Failed to load stats: ${error.message}`, 'error');
    }
}

// Keyboard Shortcuts
function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl + K to focus search
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            switchView('search');
            searchInput.focus();
        }

        // Escape to clear search
        if (e.key === 'Escape' && document.activeElement === searchInput) {
            searchInput.value = '';
            searchInput.blur();
        }
    });
}

// Utility Functions
function showLoading(text = 'Loading...') {
    document.querySelector('.loading-text').textContent = text;
    loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
    loadingOverlay.classList.add('hidden');
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}
