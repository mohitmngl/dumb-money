/**
 * DumbMoney — Frontend App
 * Clean, minimal stock screener
 */

const API_BASE = '';

// ── State ──────────────────────────────────────────────────────────
let state = {
    page: 1,
    perPage: 20,
    sort: 'weighted_alpha',
    sortDir: 'desc',
    search: '',
    filterType: 'all',
    filterTimeframe: '1Day',
    dateCutoff: '',
    exchangeFilter: '',
    minWA: '', maxWA: '',
    maxATRP: '',
    minPrice: '', maxPrice: '',
    minChange: '', maxChange: '',
    minStreak: '', maxStreak: '',
    minVolume: '',
    minPreChange: '', minPostChange: '',
    atrStatus: '', atrMultiplier: '',
    profitStatus: '',
    total: 0,
    totalPages: 0,
};

// ── Init ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    setupEventListeners();
});

function setupEventListeners() {
    // ── Multi-Select Initialization ─────────────────────────────────
    initMultiSelects();

    // Search
    const searchInput = document.getElementById('searchInput');
    let searchTimer;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
            state.search = searchInput.value;
            state.page = 1;
            loadScreener();
        }, 300);
    });

    // Sort headers
    document.querySelectorAll('.screener-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.sort;
            if (state.sort === col) {
                state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                state.sort = col;
                state.sortDir = 'asc';
            }
            // Update header classes
            document.querySelectorAll('.screener-table th.sortable').forEach(h => {
                h.classList.remove('active', 'asc', 'desc');
            });
            th.classList.add('active', state.sortDir);
            loadScreener();
        });
    });

    // Timeframe filter
    const tfSelect = document.getElementById('filterTimeframe');
    if (tfSelect) {
        tfSelect.addEventListener('change', () => {
            state.filterTimeframe = tfSelect.value;
            state.page = 1;
            loadScreener();
        });
    }

    // Date cutoff filter
    const dateInput = document.getElementById('filterDateCutoff');
    if (dateInput) {
        dateInput.addEventListener('input', () => {
            state.dateCutoff = dateInput.value;
            state.page = 1;
            loadScreener();
        });
    }

    // Exchange filter
    const exchangeSelect = document.getElementById('filterExchange');
    if (exchangeSelect) {
        exchangeSelect.addEventListener('change', () => {
            state.exchangeFilter = exchangeSelect.value;
            state.page = 1;
            loadScreener();
        });
    }

    // Auto-apply filters on change (debounced for text inputs)
    function readFilterState() {
        const dateInput = document.getElementById('filterDateCutoff');
        if (dateInput) state.dateCutoff = dateInput.value;
        const tfSelect = document.getElementById('filterTimeframe');
        if (tfSelect) state.filterTimeframe = tfSelect.value;
        state.filterType = getMultiSelectValues('msType');
        state.minWA = document.getElementById('filterMinWA').value;
        state.maxWA = document.getElementById('filterMaxWA').value;
        state.maxATRP = document.getElementById('filterMaxATRP').value;
        state.minPrice = document.getElementById('filterMinPrice').value;
        state.maxPrice = document.getElementById('filterMaxPrice').value;
        state.minChange = document.getElementById('filterMinChange').value;
        state.maxChange = document.getElementById('filterMaxChange').value;
        state.minStreak = document.getElementById('filterMinStreak').value;
        state.maxStreak = document.getElementById('filterMaxStreak').value;
        state.minVolume = document.getElementById('filterMinVolume').value;
        state.minPreChange = document.getElementById('filterMinPreChange').value;
        state.minPostChange = document.getElementById('filterMinPostChange').value;
        state.atrStatus = getMultiSelectValues('msATRStatus');
        state.atrMultiplier = getMultiSelectValues('msATRMult');
        state.profitStatus = getMultiSelectValues('msProfit');
    }

    let filterTimer;
    function applyFilters() {
        clearTimeout(filterTimer);
        filterTimer = setTimeout(() => {
            readFilterState();
            state.page = 1;
            loadScreener();
        }, 350);
    }

    // Auto-apply on input for all number fields in the sidebar
    document.querySelectorAll('.filters-sidebar input[type="number"]').forEach(el => {
        el.addEventListener('input', applyFilters);
    });
    // Auto-apply on change for multi-selects
    document.querySelectorAll('.multi-select input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', applyFilters);
    });

    // Clear All
    document.getElementById('btnClearFilters').addEventListener('click', () => {
        resetMultiSelect('msType', 'All');
        document.getElementById('filterMinWA').value = '';
        document.getElementById('filterMaxWA').value = '';
        document.getElementById('filterMaxATRP').value = '';
        document.getElementById('filterMinPrice').value = '';
        document.getElementById('filterMaxPrice').value = '';
        document.getElementById('filterMinChange').value = '';
        document.getElementById('filterMaxChange').value = '';
        document.getElementById('filterMinStreak').value = '';
        document.getElementById('filterMaxStreak').value = '';
        document.getElementById('filterMinVolume').value = '';
        document.getElementById('filterMinPreChange').value = '';
        document.getElementById('filterMinPostChange').value = '';
        resetMultiSelect('msATRStatus', 'All');
        resetMultiSelect('msATRMult', 'All');
        resetMultiSelect('msProfit', 'All');
        document.getElementById('filterTimeframe').value = '1Day';
        document.getElementById('filterDateCutoff').value = '';
        resetMultiSelect('msExchange', 'All Exchanges');
        readFilterState();
        state.dateCutoff = '';
        state.exchangeFilter = '';
        state.filterTimeframe = '1Day';
        state.page = 1;
        loadScreener();
    });

    // Pagination
    document.getElementById('prevBtn').addEventListener('click', () => {
        if (state.page > 1) {
            state.page--;
            loadScreener();
        }
    });

    document.getElementById('nextBtn').addEventListener('click', () => {
        if (state.page < state.totalPages) {
            state.page++;
            loadScreener();
        }
    });

    // Refresh
    document.getElementById('btnRefresh').addEventListener('click', () => {
        const btn = document.getElementById('btnRefresh');
        if (btn.classList.contains('loading')) return;

        btn.classList.add('loading');
        updateOpProgress('refresh', { visible: true, pct: 0, phase: 'Starting refresh...', detail: '0%', eta: 'calculating...' });

        fetch('/api/refresh', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'already_running') {
                    showStatus('Refresh already in progress');
                    btn.classList.remove('loading');
                    dismissProgress('refreshProgress');
                    return;
                }

                // Poll for completion
                const pollInterval = setInterval(async () => {
                    try {
                        const statusRes = await fetch('/api/download-status');
                        const statusData = await statusRes.json();
                        if (statusData.status !== 'running' && statusData.status !== 'idle') {
                            clearInterval(pollInterval);
                            btn.classList.remove('loading');
                            if (statusData.status === 'complete') {
                                updateOpProgress('refresh', { pct: 100, phase: 'Refresh complete!', detail: '100%', eta: '', done: true });
                                showStatus(statusData.message || 'Refresh complete! Starting pre/post update...');
                                // After refresh, update pre/post market data automatically
                                setTimeout(() => {
                                    updatePrePost();
                                }, 500);
                                loadData();
                                // Also reload stock detail if viewing one
                                if (currentSymbol && document.getElementById('stockDetail').querySelector('.stock-header')) {
                                    loadStock(currentSymbol);
                                }
                                setTimeout(() => dismissProgress('refreshProgress'), 2500);
                            } else if (statusData.status === 'error') {
                                updateOpProgress('refresh', { phase: 'Refresh failed', detail: 'Error', eta: '' });
                                showStatus(statusData.message || 'Refresh failed');
                                setTimeout(() => dismissProgress('refreshProgress'), 3000);
                            }
                        } else if (statusData.status === 'running') {
                            // Update progress bar with live data
                            const phase = statusData.phase || 'Refreshing...';
                            const done = statusData.symbols_done || 0;
                            const total = statusData.symbols_total || 0;
                            const pct = total > 0 ? Math.round((done / total) * 100) : 0;
                            const curSym = statusData.current_symbol || '';
                            const speed = statusData.speed_str || '';

                            // ETA calculation
                            let etaText = '';
                            if (statusData.start_time && done > 0 && pct > 0 && pct < 100) {
                                const elapsed = Date.now() / 1000 - statusData.start_time;
                                const remaining = (elapsed / pct) * (100 - pct);
                                const etaSecs = Math.round(remaining);
                                if (etaSecs < 60) etaText = `${etaSecs}s`;
                                else etaText = `${Math.floor(etaSecs / 60)}m ${etaSecs % 60}s`;
                            } else if (pct >= 100) {
                                etaText = 'Almost done';
                            } else {
                                etaText = 'calculating...';
                            }

                            const detailParts = [`${done}/${total}`];
                            if (speed) detailParts.push(speed);
                            if (curSym) detailParts.push(curSym);
                            if (etaText) detailParts.push(`ETA ${etaText}`);

                            updateOpProgress('refresh', {
                                pct: pct,
                                phase: phase,
                                detail: detailParts.join(' · '),
                                eta: etaText,
                            });
                        }
                    } catch (e) {
                        clearInterval(pollInterval);
                        btn.classList.remove('loading');
                        dismissProgress('refreshProgress');
                    }
                }, 1000);
            })
            .catch(() => {
                btn.classList.remove('loading');
                dismissProgress('refreshProgress');
                showStatus('Failed to start refresh');
            });
    });

    // Reset
    const resetModal = document.getElementById('resetModal');
    document.getElementById('btnReset').addEventListener('click', () => {
        resetModal.classList.add('active');
    });
    document.getElementById('btnCancelReset').addEventListener('click', () => {
        resetModal.classList.remove('active');
    });
    resetModal.addEventListener('click', (e) => {
        if (e.target === resetModal) resetModal.classList.remove('active');
    });
    document.getElementById('btnConfirmReset').addEventListener('click', async () => {
        resetModal.classList.remove('active');
        const btn = document.getElementById('btnConfirmReset');
        btn.disabled = true;
        btn.textContent = 'Resetting...';
        try {
            const res = await fetch('/api/reset-data', { method: 'POST' });
            const data = await res.json();
            showStatus(data.message || 'Reset started...');
            if (data.status === 'running') {
                pollResetStatus();
            }
        } catch (e) {
            showStatus('Failed to start reset');
            btn.disabled = false;
            btn.textContent = 'Yes, Reset Everything';
        }
    });

    async function pollResetStatus() {
        const pollInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/download-status');
                const data = await res.json();
                if (data.status === 'complete') {
                    clearInterval(pollInterval);
                    showStatus(data.message || 'Reset complete! Reloading...');
                    setTimeout(() => location.reload(), 2000);
                } else if (data.status === 'error') {
                    clearInterval(pollInterval);
                    showStatus(data.message || 'Reset failed');
                    document.getElementById('btnConfirmReset').disabled = false;
                    document.getElementById('btnConfirmReset').textContent = 'Yes, Reset Everything';
                }
            } catch (e) {
                clearInterval(pollInterval);
            }
        }, 1000);
    }

    function showStatus(msg) {
        const el = document.getElementById('updateStatus');
        el.textContent = msg;
        setTimeout(() => { el.textContent = ''; }, 5000);
    }

    function dismissProgress(id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('visible');
    }

    function updateOpProgress(type, data) {
        const map = {
            refresh: {
                bar: 'refreshProgress',
                fill: 'refreshBarFill',
                label: 'refreshLabel',
                detail: 'refreshDetail',
                eta: 'refreshETA',
                icon: 'refreshIcon',
            },
            prepost: {
                bar: 'prePostProgress',
                fill: 'prePostBarFill',
                label: 'prePostLabel',
                detail: 'prePostDetail',
                eta: 'prePostETA',
                icon: 'prePostIcon',
            },
        };
        const c = map[type];
        if (!c) return;

        const bar = document.getElementById(c.bar);
        const fill = document.getElementById(c.fill);
        const label = document.getElementById(c.label);
        const detail = document.getElementById(c.detail);
        const eta = document.getElementById(c.eta);
        const icon = document.getElementById(c.icon);

        if (!bar) return;

        if (data.visible) {
            bar.classList.add('visible');
        }

        if (fill && data.pct !== undefined) {
            fill.style.width = data.pct + '%';
        }
        if (label && data.phase) {
            label.textContent = data.phase;
        }
        if (detail && data.detail !== undefined) {
            detail.textContent = data.detail;
        }
        if (eta && data.eta !== undefined) {
            eta.textContent = data.eta;
        }
        if (icon && data.done) {
            icon.classList.add('done');
        }
    }

    // ── Auto-Refresh Timer ───────────────────────────────────────────
    const AUTO_REFRESH_INTERVAL = 86400; // 24 hours (disabled for practical use)
    let autoRefreshSeconds = AUTO_REFRESH_INTERVAL;
    let autoRefreshTimer = null;
    let autoRefreshPaused = false;
    const timerEl = document.getElementById('autoRefreshTimer');
    const countdownEl = document.getElementById('timerCountdown');

    function updateTimerDisplay() {
        const mins = Math.floor(autoRefreshSeconds / 60);
        const secs = autoRefreshSeconds % 60;
        countdownEl.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;

        if (autoRefreshPaused) {
            timerEl.classList.add('paused');
            timerEl.classList.remove('running');
        } else {
            timerEl.classList.add('running');
            timerEl.classList.remove('paused');
        }
    }

    function startAutoRefreshCountdown() {
        autoRefreshSeconds = AUTO_REFRESH_INTERVAL;
        autoRefreshPaused = false;
        updateTimerDisplay();

        clearInterval(autoRefreshTimer);
        autoRefreshTimer = setInterval(() => {
            if (autoRefreshPaused) return;

            autoRefreshSeconds--;
            updateTimerDisplay();

            if (autoRefreshSeconds <= 0) {
                // Time's up — trigger refresh
                showStatus('Auto-refresh triggered');
                document.getElementById('btnRefresh').click();
                // Reset countdown after triggering
                autoRefreshSeconds = AUTO_REFRESH_INTERVAL;
            }
        }, 1000);
    }

    function pauseAutoRefresh() {
        autoRefreshPaused = true;
        updateTimerDisplay();
    }

    function resumeAutoRefresh() {
        autoRefreshPaused = false;
        updateTimerDisplay();
    }

    // Click timer to manually trigger refresh
    timerEl.addEventListener('click', () => {
        const btn = document.getElementById('btnRefresh');
        if (!btn.classList.contains('loading')) {
            showStatus('Manual refresh triggered');
            document.getElementById('btnRefresh').click();
            autoRefreshSeconds = AUTO_REFRESH_INTERVAL;
            updateTimerDisplay();
        }
    });

    // Pause auto-refresh when user is interacting, resume after idle
    let idleTimeout;
    const resetIdle = () => {
        clearTimeout(idleTimeout);
        pauseAutoRefresh();
        idleTimeout = setTimeout(() => {
            resumeAutoRefresh();
        }, 30000); // Resume after 30 seconds of inactivity
    };

    document.addEventListener('mousemove', resetIdle);
    document.addEventListener('keydown', resetIdle);
    document.addEventListener('click', resetIdle);

    // Start the auto-refresh countdown
    startAutoRefreshCountdown();

    // Expose progress helpers for inline onclick handlers
    window.dismissProgress = dismissProgress;
    window.updateOpProgress = updateOpProgress;
}

// ── Multi-Select Helpers ───────────────────────────────────────────
function initMultiSelects() {
    document.querySelectorAll('.multi-select').forEach(ms => {
        const trigger = ms.querySelector('.ms-trigger');
        const dropdown = ms.querySelector('.ms-dropdown');
        const label = ms.querySelector('.ms-label');
        const checkboxes = ms.querySelectorAll('input[type="checkbox"]');

        // Toggle dropdown
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            // Close other dropdowns
            document.querySelectorAll('.multi-select.open').forEach(other => {
                if (other !== ms) other.classList.remove('open');
            });
            ms.classList.toggle('open');
        });

        // Handle checkbox changes
        checkboxes.forEach(cb => {
            cb.addEventListener('change', () => {
                updateMultiSelectLabel(ms);
                // If "All" is checked, uncheck others
                const allCb = ms.querySelector('input[value=""]');
                if (cb.value === '' && cb.checked) {
                    checkboxes.forEach(other => {
                        if (other !== cb) other.checked = false;
                    });
                }
                // If any specific option is checked, uncheck "All"
                if (cb.value !== '' && cb.checked && allCb) {
                    allCb.checked = false;
                }
                // If nothing checked, check "All"
                const anyChecked = ms.querySelector('input[value!=""]:checked');
                if (!anyChecked && allCb) {
                    allCb.checked = true;
                }
                updateMultiSelectLabel(ms);
            });
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!ms.contains(e.target)) {
                ms.classList.remove('open');
            }
        });
    });
}

function updateMultiSelectLabel(ms) {
    const label = ms.querySelector('.ms-label');
    const checkboxes = ms.querySelectorAll('input[type="checkbox"]');
    const checked = Array.from(checkboxes).filter(cb => cb.checked && cb.value !== '');
    const allCb = ms.querySelector('input[value=""]');

    if (checked.length === 0 || (allCb && allCb.checked)) {
        const allLabel = ms.querySelector('input[value=""]')?.parentElement?.textContent?.trim() || 'All';
        label.textContent = allLabel;
    } else if (checked.length === 1) {
        label.textContent = checked[0].parentElement.textContent.trim();
    } else {
        label.textContent = `${checked.length} selected`;
    }
}

function getMultiSelectValues(msId) {
    const ms = document.getElementById(msId);
    if (!ms) return '';
    const checkboxes = ms.querySelectorAll('input[type="checkbox"]');
    const values = Array.from(checkboxes)
        .filter(cb => cb.checked && cb.value !== '')
        .map(cb => cb.value);
    return values.join(',');
}

function resetMultiSelect(msId, defaultLabel) {
    const ms = document.getElementById(msId);
    if (!ms) return;
    const checkboxes = ms.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(cb => {
        cb.checked = cb.value === '';
    });
    const label = ms.querySelector('.ms-label');
    if (label) label.textContent = defaultLabel;
}

// ── Data Loading ───────────────────────────────────────────────────
function loadData() {
    loadScreener();
    loadMarketBreadth();
    loadTopLists();
    loadStats();
    loadExchanges();
}

function loadExchanges() {
    fetch('/api/exchanges')
        .then(r => r.json())
        .then(data => {
            const dropdown = document.getElementById('exchangeDropdown');
            if (!dropdown || !data.exchanges) return;
            dropdown.innerHTML = '<label class="ms-option"><input type="checkbox" value="" checked> All Exchanges</label>' +
                data.exchanges.map(ex => `<label class="ms-option"><input type="checkbox" value="${escapeHtml(ex)}"> ${escapeHtml(ex)}</label>`).join('');
        });
}

async function updatePrePost() {
    const btn = document.getElementById('btnPrePost');
    if (btn.classList.contains('loading')) return;

    btn.classList.add('loading');
    updateOpProgress('prepost', { visible: true, pct: 0, phase: 'Starting pre/post update...', detail: '0%', eta: 'calculating...' });

    try {
        const res = await fetch('/api/update-pre-post', { method: 'POST' });
        const data = await res.json();
        showStatus(data.message || 'Updating pre/post market prices...');

        // Poll for completion
        const pollInterval = setInterval(async () => {
            const statusRes = await fetch('/api/download-status');
            const statusData = await statusRes.json();
            if (statusData.status !== 'running' && statusData.status !== 'idle') {
                clearInterval(pollInterval);
                btn.classList.remove('loading');
                if (statusData.status === 'complete') {
                    updateOpProgress('prepost', { pct: 100, phase: 'Pre/post update complete!', detail: '100%', eta: '', done: true });
                    showStatus(statusData.message || 'Pre/post update complete!');
                    loadData();
                    setTimeout(() => dismissProgress('prePostProgress'), 2500);
                } else if (statusData.status === 'error') {
                    updateOpProgress('prepost', { phase: 'Pre/post update failed', detail: 'Error', eta: '' });
                    showStatus(statusData.message || 'Pre/post update failed');
                    setTimeout(() => dismissProgress('prePostProgress'), 3000);
                }
            } else if (statusData.status === 'running') {
                // Update progress bar with live data
                const phase = statusData.phase || 'Updating...';
                const done = statusData.symbols_done || 0;
                const total = statusData.symbols_total || 0;
                const pct = total > 0 ? Math.round((done / total) * 100) : 0;

                // ETA calculation
                let etaText = '';
                if (statusData.start_time && done > 0 && pct > 0 && pct < 100) {
                    const elapsed = Date.now() / 1000 - statusData.start_time;
                    const remaining = (elapsed / pct) * (100 - pct);
                    const etaSecs = Math.round(remaining);
                    if (etaSecs < 60) etaText = `${etaSecs}s`;
                    else etaText = `${Math.floor(etaSecs / 60)}m ${etaSecs % 60}s`;
                } else if (pct >= 100) {
                    etaText = 'Almost done';
                } else {
                    etaText = 'calculating...';
                }

                updateOpProgress('prepost', {
                    pct: pct,
                    phase: phase,
                    detail: `${done}/${total}`,
                    eta: etaText,
                });
            }
        }, 1000);
    } catch (e) {
        btn.classList.remove('loading');
        dismissProgress('prePostProgress');
        showStatus('Failed to start pre/post update');
    }
}

function loadScreener() {
    const params = new URLSearchParams({
        page: state.page,
        per_page: state.perPage,
        sort: state.sort,
        dir: state.sortDir,
        search: state.search,
        type: state.filterType,
        timeframe: state.filterTimeframe,
    });
    if (state.dateCutoff) params.set('date_cutoff', state.dateCutoff);
    if (state.exchangeFilter) params.set('exchange', state.exchangeFilter);
    if (state.minWA) params.set('min_wa', state.minWA);
    if (state.maxWA) params.set('max_wa', state.maxWA);
    if (state.maxATRP) params.set('max_atrp', state.maxATRP);
    if (state.minPrice) params.set('min_price', state.minPrice);
    if (state.maxPrice) params.set('max_price', state.maxPrice);
    if (state.minChange) params.set('min_change', state.minChange);
    if (state.maxChange) params.set('max_change', state.maxChange);
    if (state.minStreak) params.set('min_streak', state.minStreak);
    if (state.maxStreak) params.set('max_streak', state.maxStreak);
    if (state.minVolume) params.set('min_volume', state.minVolume);
    if (state.minPreChange) params.set('min_pre_change', state.minPreChange);
    if (state.minPostChange) params.set('min_post_change', state.minPostChange);
    if (state.atrStatus) params.set('atr_status', state.atrStatus);
    if (state.atrMultiplier) params.set('atr_multiplier', state.atrMultiplier);
    if (state.profitStatus) params.set('profit_status', state.profitStatus);

    fetch(`/api/screener?${params}`)
        .then(r => r.json())
        .then(data => {
            state.total = data.total;
            state.totalPages = data.total_pages;
            renderTable(data.stocks);
            renderPagination();
        });
}

function loadMarketBreadth() {
    fetch('/api/market-breadth')
        .then(r => r.json())
        .then(data => renderBreadth(data));
}

function loadTopLists() {
    fetch('/api/top-lists')
        .then(r => r.json())
        .then(data => {
            renderPanel('momentumBody', data.momentum, 'weighted_alpha', true);
            renderPanel('gainersBody', data.gainers, 'change_pct', true);
            renderPanel('volumeBody', data.volume, 'volume', false);
        });
}

function loadStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            document.getElementById('resultCount').textContent =
                `${data.total_stocks.toLocaleString()} stocks · Avg WA: ${data.avg_weighted_alpha}%`;
            document.getElementById('dataRange').textContent =
                `Data: ${data.oldest_data_min || '?'} – ${data.oldest_data_max || '?'}`;
        });
}

// ── Rendering ──────────────────────────────────────────────────────
function renderTable(stocks) {
    const tbody = document.getElementById('tableBody');

    if (stocks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="24" class="empty-cell">No stocks match your filters</td></tr>';
        return;
    }

    tbody.innerHTML = stocks.map(s => {
        const changeClass = s.change_pct > 0 ? 'change-positive' : s.change_pct < 0 ? 'change-negative' : '';
        const waClass = s.weighted_alpha > 20 ? 'wa-bullish' : s.weighted_alpha < -10 ? 'wa-bearish' : 'wa-neutral';
        const preClass = s.pre_change_pct > 0 ? 'text-green' : s.pre_change_pct < 0 ? 'text-red' : '';
        const postClass = s.post_change_pct > 0 ? 'text-green' : s.post_change_pct < 0 ? 'text-red' : '';
        const streakVal = s.streak ?? 0;
        const streakHtml = streakVal >= 5 ? `<span class="streak-fire">${streakVal}</span>` : streakVal;
        const oldestFormatted = s.oldest_data ? formatOldestData(s.oldest_data) : '—';

        // Type badge
        const typeBadge = s.asset_class === 'etf' || s.type === 'etf' ? 'ETF'
            : s.asset_class === 'index' || s.type === 'index' ? 'IDX'
            : s.asset_class === 'adr' || s.type === 'adr' ? 'ADR'
            : 'STK';

        // Events HTML
        let eventsHtml = '—';
        if (s.events && s.events.length > 0) {
            const importantTypes = ['split', 'bonus', 'merger', 'acquisition', 'dividend', 'spin_off'];
            const importantEvent = s.events.find(e => importantTypes.includes(e.event_type?.toLowerCase()));
            if (importantEvent) {
                eventsHtml = `<span class="event-badge ${importantEvent.event_type?.toLowerCase()}">${importantEvent.event_type || 'Event'}</span>`;
            } else {
                eventsHtml = `<span class="event-badge minor">${s.events[0].event_type || 'Event'}</span>`;
            }
        }

        // AI Score
        let aiScoreHtml = '—';
        if (s.ai_score != null) {
            const scoreColor = s.ai_score >= 65 ? 'var(--green)' : s.ai_score <= 35 ? 'var(--red)' : 'var(--text-secondary)';
            const biasColor = s.ai_bias === 'bullish' ? 'var(--green)' : s.ai_bias === 'bearish' ? 'var(--red)' : 'var(--text-secondary)';
            aiScoreHtml = `<span style="color:${scoreColor};font-weight:600">${s.ai_score.toFixed(0)}</span>
                           <span style="color:${biasColor};font-size:9px;text-transform:uppercase;margin-left:3px">${s.ai_bias || ''}</span>`;
        }

        // Sub-score helper
        const subScoreHtml = (val) => val ? `<span style="font-variant-numeric:tabular-nums;font-size:11px">${val.toFixed(0)}</span>` : '—';

        // Volume Profile Score
        const vpHtml = subScoreHtml(s.ai_volume_profile);

        // Trendline Score
        const tlHtml = subScoreHtml(s.ai_trendline);

        // Sentiment Score
        const sentHtml = subScoreHtml(s.ai_sentiment);

        // Conclusion badge
        let conclusionHtml = '—';
        if (s.ai_conclusion) {
            const cls = s.ai_conclusion === 'BUY' ? 'conclusion-buy' : s.ai_conclusion === 'SELL' ? 'conclusion-sell' : 'conclusion-hold';
            conclusionHtml = `<span class="${cls}">${s.ai_conclusion}</span>`;
        }

        // ATR Cross columns
        const crossAboveHtml = s.atr_crossed_above
            ? '<span style="color:var(--green);font-weight:700;font-size:13px">&#10003;</span>'
            : '<span style="color:var(--text-tertiary)">—</span>';
        const crossBelowHtml = s.atr_crossed_below
            ? '<span style="color:var(--red);font-weight:700;font-size:13px">&#10003;</span>'
            : '<span style="color:var(--text-tertiary)">—</span>';

        // ATR Status — show stop price + streak with direction arrow
        let atrHtml = '—';
        if (s.atr_stop != null && s.atr_stop > 0) {
            const isUptrend = s.atr_signal === 1;
            const arrow = isUptrend ? '▲' : '▼';
            const colorClass = isUptrend ? 'change-positive' : s.atr_signal === -1 ? 'change-negative' : '';
            atrHtml = `<span class="${colorClass}" style="font-weight:600;font-size:10px">$${formatPrice(s.atr_stop)} ${arrow} ${s.atr_streak ?? 0}</span>`;
        } else if (s.atrp != null && s.atrp > 0 && s.atr_stop != null && s.atr_stop <= 0) {
            atrHtml = '<span style="color:var(--text-tertiary);font-size:10px">No ATR stop</span>';
        }

        // Margin
        const marginHtml = s.marginable ? '<span style="color:var(--green);font-weight:600">2x</span>' : '<span style="color:var(--text-tertiary)">—</span>';

        // Profit
        let profitHtml = '<span style="color:var(--text-tertiary)">—</span>';
        const ps = s.profit_status;
        let profitDetailHtml = '';
        if (s.profit_millions != null) {
            const dir = s.profit_post_result_dir === 'up' ? '&#9650;' : s.profit_post_result_dir === 'down' ? '&#9660;' : '';
            const exp = s.profit_expectations === 'above' ? '&#9650;' : s.profit_expectations === 'below' ? '&#9660;' : '';
            profitDetailHtml = `<br><span style="font-size:10px;color:var(--text-tertiary)">$${s.profit_millions.toFixed(1)}M ${dir} ${exp}</span>`;
        }
        if (ps === 'profitable') {
            profitHtml = '<span style="color:var(--green);font-weight:600">Profitable</span>' + profitDetailHtml;
        } else if (ps === 'loss_making') {
            profitHtml = '<span style="color:var(--red);font-weight:600">Loss</span>' + profitDetailHtml;
        } else if (ps === 'growing') {
            profitHtml = '<span style="color:var(--green);font-weight:600">&#9650; Growing</span>' + profitDetailHtml;
        } else if (ps === 'declining') {
            profitHtml = '<span style="color:var(--red);font-weight:600">&#9660; Declining</span>' + profitDetailHtml;
        } else if (ps === 'N/A') {
            profitHtml = '<span style="color:var(--text-tertiary)">N/A</span>';
        }

        return `<tr class="clickable" onclick="window.open('/stock/${s.symbol}', '_blank')">
            <td class="symbol-cell">${s.symbol}</td>
            <td>${escapeHtml(s.name)}</td>
            <td class="exchange-cell">${s.exchange || '—'}</td>
            <td class="type-cell"><span class="type-badge ${typeBadge.toLowerCase()}">${typeBadge}</span></td>
            <td class="price-cell">$${formatPrice(s.price)}</td>
            <td class="pre-cell ${preClass}">${s.pre_price != null ? `$${formatPrice(s.pre_price)}` : '<span style="color:var(--text-tertiary);font-size:9px">no pre</span>'}${s.pre_change_pct != null ? `<br><span class="change-sub">${s.pre_change_pct > 0 ? '+' : ''}${s.pre_change_pct.toFixed(2)}%</span>` : ''}</td>
            <td class="post-cell ${postClass}">${s.post_price != null ? `$${formatPrice(s.post_price)}` : '<span style="color:var(--text-tertiary);font-size:9px">no post</span>'}${s.post_change_pct != null ? `<br><span class="change-sub">${s.post_change_pct > 0 ? '+' : ''}${s.post_change_pct.toFixed(2)}%</span>` : ''}</td>
            <td class="change-cell ${changeClass}">${s.change_pct > 0 ? '+' : ''}${s.change_pct.toFixed(2)}%</td>
            <td class="wa-cell ${waClass}">${s.weighted_alpha > 0 ? '+' : ''}${s.weighted_alpha.toFixed(1)}%</td>
            <td class="volume-cell">${formatVolume(s.volume)}</td>
            <td class="streak-cell">${streakHtml != null && streakHtml !== '' ? streakHtml : '—'}</td>
            <td class="oldest-cell">${oldestFormatted}</td>
            <td class="events-cell">${eventsHtml}</td>
            <td class="ai-score-cell">${aiScoreHtml}</td>
            <td class="ai-sub-cell">${vpHtml}</td>
            <td class="ai-sub-cell">${tlHtml}</td>
            <td class="ai-sub-cell">${sentHtml}</td>
            <td class="conclusion-cell">${conclusionHtml}</td>
            <td class="cross-cell" style="text-align:center">${crossAboveHtml}</td>
            <td class="cross-cell" style="text-align:center">${crossBelowHtml}</td>
            <td class="atr-cell">${atrHtml}</td>
            <td class="atrp-cell">${s.atrp != null && s.atrp !== '' ? `<span style="font-variant-numeric:tabular-nums">${s.atrp.toFixed(2)}%</span>` : '—'}</td>
            <td class="margin-cell">${marginHtml}</td>
            <td class="frac-cell">${s.fractionable ? 'Yes' : 'No'}</td>
            <td class="profit-cell">${profitHtml}</td>
            <td class="updated-cell">${s.last_updated ? new Date(s.last_updated).toLocaleDateString() : '—'}</td>
        </tr>`;
    }).join('');
}

function renderPagination() {
    document.getElementById('prevBtn').disabled = state.page <= 1;
    document.getElementById('nextBtn').disabled = state.page >= state.totalPages;
    document.getElementById('pageInfo').textContent =
        `Page ${state.page} of ${state.totalPages || 1} · ${state.total.toLocaleString()} results`;
}

function renderBreadth(data) {
    const strip = document.getElementById('breadthStrip');
    const html = Object.entries(data).map(([name, d]) => {
        const declinePct = 100 - d.ratio;
        return `<div class="breadth-item">
            <span class="breadth-label">${name}</span>
            <span class="breadth-stats">${d.advancing}↑ / ${d.declining}↓</span>
        </div>`;
    }).join('');
    strip.innerHTML = `<div class="breadth-inner">${html}</div>`;
}

function renderPanel(tbodyId, items, valueField, isPercent) {
    const tbody = document.getElementById(tbodyId);
    if (!items || items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading-cell">No data</td></tr>';
        return;
    }
    tbody.innerHTML = items.map((item, i) => {
        const val = item[valueField];
        const valStr = isPercent
            ? `${val > 0 ? '+' : ''}${val.toFixed(1)}%`
            : formatVolume(val);
        return `<tr>
            <td class="panel-rank">${i + 1}</td>
            <td class="panel-symbol"><a href="/stock/${item.symbol}" target="_blank" rel="noopener" class="panel-link">${item.symbol}</a></td>
            <td class="panel-value">$${formatPrice(item.price)}</td>
            <td class="panel-value ${val > 0 ? 'text-green' : val < 0 ? 'text-red' : ''}">${valStr}</td>
        </tr>`;
    }).join('');
}

// ── Stock Detail (opens in new tab) ─────────────────────────────────
function openStock(symbol) {
    window.open(`/stock/${symbol}`, '_blank');
}

// ── Chart Drawing (legacy, kept for reference) ──────────────────────
function drawMiniChart(bars) {
    const canvas = document.getElementById('priceChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width - 32;
    canvas.height = rect.height - 32;

    const w = canvas.width;
    const h = canvas.height;
    const closes = bars.map(b => b.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;

    const padding = 4;
    const isUp = closes[closes.length - 1] >= closes[0];
    const lineColor = isUp ? '#00C805' : '#FF3B30';
    const fillColor = isUp ? 'rgba(0, 200, 5, 0.08)' : 'rgba(255, 59, 48, 0.08)';

    ctx.clearRect(0, 0, w, h);

    // Grid lines
    ctx.strokeStyle = 'rgba(0,0,0,0.04)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 4; i++) {
        const y = padding + (h - 2 * padding) * i / 3;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
    }

    // Price line
    ctx.beginPath();
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';

    const stepX = (w - 2 * padding) / (closes.length - 1);
    const points = closes.map((c, i) => ({
        x: padding + i * stepX,
        y: padding + (1 - (c - min) / range) * (h - 2 * padding)
    }));

    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.stroke();

    // Fill area
    ctx.lineTo(points[points.length - 1].x, h);
    ctx.lineTo(points[0].x, h);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();

    // End dot
    const last = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(last.x, last.y, 3, 0, Math.PI * 2);
    ctx.fillStyle = lineColor;
    ctx.fill();
}

// ── Utility Functions ──────────────────────────────────────────────
function formatPrice(p) {
    if (p == null || isNaN(p)) return '—';
    if (p >= 1000) return p.toFixed(0);
    if (p >= 1) return p.toFixed(2);
    return p.toFixed(4);
}

function formatOldestData(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        const now = new Date();
        const months = (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth());
        const years = Math.floor(months / 12);
        const remMonths = months % 12;
        if (years > 0 && remMonths > 0) return `${years}y ${remMonths}m`;
        if (years > 0) return `${years}y`;
        return `${remMonths}m`;
    } catch {
        return dateStr;
    }
}

function formatVolume(v) {
    if (!v || isNaN(v)) return '—';
    return v.toLocaleString('en-US');
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Column Resize ──────────────────────────────────────────────────
function initColumnResize() {
    const table = document.getElementById('screenerTable');
    if (!table) return;

    document.querySelectorAll('.screener-table th .resize-handle').forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const th = handle.closest('th');
            const startX = e.clientX;
            const startWidth = th.offsetWidth;
            handle.classList.add('resizing');

            function onMouseMove(ev) {
                const diff = ev.clientX - startX;
                const newWidth = Math.max(40, startWidth + diff);
                // Set width on all cells in this column (th + tds)
                const colIdx = Array.from(th.parentElement.children).indexOf(th);
                table.querySelectorAll(`tr th:nth-child(${colIdx + 1}), tr td:nth-child(${colIdx + 1})`).forEach(cell => {
                    cell.style.width = newWidth + 'px';
                    cell.style.minWidth = newWidth + 'px';
                    cell.style.maxWidth = newWidth + 'px';
                    cell.style.whiteSpace = 'nowrap';
                    cell.style.overflow = 'hidden';
                    cell.style.textOverflow = 'ellipsis';
                });
            }

            function onMouseUp() {
                handle.classList.remove('resizing');
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    });
}

// Init column resize after table is rendered
const origRenderTable = renderTable;
renderTable = function(stocks) {
    origRenderTable(stocks);
    initColumnResize();
};

// ── Live Price Polling ──────────────────────────────────────────────────
let _liveTimers = {};

function startLivePrices(symbols, callback, intervalMs = 1500) {
    const key = callback.toString();
    if (_liveTimers[key]) stopLivePrices(key);
    // Subscribe to backend
    fetch('/api/live/subscribe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbols})
    }).catch(() => {});
    // Poll
    function poll() {
        const s = Object.keys(_liveTimers).length > 0
            ? [...new Set(Object.values(_liveTimers).flatMap(t => t.symbols))].join(',')
            : symbols.join(',');
        if (!s) return;
        fetch(`/api/live/prices?symbols=${s}`)
            .then(r => r.json())
            .then(data => callback(data))
            .catch(() => {});
    }
    _liveTimers[key] = { symbols, interval: setInterval(poll, intervalMs), callback };
    poll();
}

function stopLivePrices(key) {
    if (!key) {
        Object.values(_liveTimers).forEach(t => clearInterval(t.interval));
        _liveTimers = {};
        return;
    }
    if (_liveTimers[key]) {
        clearInterval(_liveTimers[key].interval);
        delete _liveTimers[key];
    }
}

function updateLivePrice(elementId, prices) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const sym = el.dataset.symbol;
    if (sym && prices[sym]) {
        const p = prices[sym];
        if (p.price) {
            el.textContent = '$' + p.price.toFixed(2);
            if (p.from_db) el.style.color = 'var(--text-secondary)';
            else el.style.color = 'var(--accent)';
        }
    }
}
