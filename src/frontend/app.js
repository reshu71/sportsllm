// ── APEX V4 — Frontend Application ─────────────────────────────────────
// State
let currentChatMode = 'ask';
let chatHistories = { ask: [], analyze: [], plan: [] };
let pmcChart = null;
let zoneChart = null;
let currentPlanJSON = null;    // V4: Holds plan JSON before confirm
let currentPlanMeta = null;    // V4: Holds plan metadata (goal, dates, etc.)
let currentDashboardPeriod = 30;
let cachedHeatmapGrid = null;  // V4: Cached full heatmap for period slicing

const SUGGESTED_PROMPTS = {
    ask: [
        { text: "What's the best way to improve my lactate threshold?", short: "Lactate Threshold" },
        { text: "How should I fuel for a 3-hour long run?", short: "Long Run Fuel" },
        { text: "Explain the 80/20 training method", short: "80/20 Method" },
        { text: "What does CTL mean and how should I interpret mine?", short: "CTL Explained" },
    ],
    analyze: [
        { text: "What does my training load look like over the past 6 weeks?", short: "6-Week Load" },
        { text: "Am I overreaching right now?", short: "Overreaching?" },
        { text: "Where am I spending most of my training time by zone?", short: "Zone Distribution" },
        { text: "How does my fitness compare to 3 months ago?", short: "Fitness Trend" },
    ],
    plan: [
        { text: "Build me a 16-week marathon plan", short: "Marathon Plan" },
        { text: "I can only run 5 days this week, adjust my plan", short: "Adjust Week" },
        { text: "Add a taper in the final 2 weeks", short: "Add Taper" },
        { text: "Shift all Wednesday sessions to Thursday", short: "Move Sessions" },
    ],
};

// ── Tab Switching ──────────────────────────────────────────────────────
function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');

    const views = ['chat-wrapper', 'dashboard-wrapper', 'analytics-wrapper', 'plan-wrapper'];
    views.forEach(v => {
        const el = document.getElementById(v);
        if (el) el.style.display = 'none';
    });

    const titles = {
        chat: ['AI Coach', 'RAG-powered endurance coaching'],
        dashboard: ['Dashboard', 'Strava-synced training overview'],
        analytics: ['Analytics', 'Performance metrics & race predictions'],
        plan: ['Training Plan', 'AI-generated periodized training']
    };
    document.getElementById('page-title').textContent = titles[tab][0];
    document.getElementById('page-subtitle').textContent = titles[tab][1];

    if (tab === 'chat') {
        document.getElementById('chat-wrapper').style.display = 'flex';
    } else if (tab === 'dashboard') {
        document.getElementById('dashboard-wrapper').style.display = 'block';
        loadDashboard();
    } else if (tab === 'analytics') {
        document.getElementById('analytics-wrapper').style.display = 'block';
        loadAnalytics();
    } else if (tab === 'plan') {
        document.getElementById('plan-wrapper').style.display = 'block';
        loadPlan();
    }
}

// ── V4: Chat Mode Switching ────────────────────────────────────────────
function switchChatMode(mode) {
    currentChatMode = mode;
    document.querySelectorAll('.chat-mode-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.chat-mode-btn[data-mode="${mode}"]`).classList.add('active');

    // Update prompt chips
    const chipsEl = document.getElementById('prompt-chips');
    chipsEl.innerHTML = SUGGESTED_PROMPTS[mode].map(p =>
        `<button class="prompt-chip" onclick="setPrompt('${p.text.replace(/'/g, "\\'")}')">${p.short}</button>`
    ).join('');

    // Show/hide welcome or history
    const container = document.getElementById('chat-container');
    const welcome = document.getElementById('welcome-screen');
    const history = chatHistories[mode];

    container.innerHTML = '';
    if (history.length === 0) {
        container.appendChild(welcome);
        welcome.style.display = 'flex';
        // Refresh icons
        chipsEl.innerHTML = SUGGESTED_PROMPTS[mode].map(p =>
            `<button class="prompt-chip" onclick="setPrompt('${p.text.replace(/'/g, "\\'")}')">${p.short}</button>`
        ).join('');
    } else {
        welcome.style.display = 'none';
        history.forEach(msg => {
            const div = createMessageDiv(msg.role, msg.content);
            container.appendChild(div);
        });
        container.scrollTop = container.scrollHeight;
    }

    // Update placeholder
    const placeholders = {
        ask: "Ask anything about endurance sports...",
        analyze: "Ask about your training data, trends, recovery...",
        plan: "Build or modify your training plan..."
    };
    document.getElementById('user-input').placeholder = placeholders[mode];
    lucide.createIcons();
}

// ── Dashboard Loading ──────────────────────────────────────────────────
function loadDashboard() {
    fetchDashboardStats(currentDashboardPeriod);
    loadDailyInsight();

    // Fetch profile
    fetch('/api/profile').then(r => r.json()).then(data => {
        const p = data.profile;
        document.getElementById('val-vdot').textContent = p.current_vdot || '-';
        document.getElementById('val-maxhr').textContent = p.max_hr || '-';
        document.getElementById('val-resthr').textContent = p.resting_hr || '-';
        // Strava status
        if (p.strava_connected) {
            document.getElementById('stravaStatus').innerHTML =
                `<span class="sync-dot"></span> Connected as <strong>${p.name || 'Athlete'}</strong>`;
        }
    }).catch(() => { });

    // Init map
    if (!map) initMap();
}

function fetchDashboardStats(days = 30) {
    currentDashboardPeriod = days;
    // Update filter buttons
    document.querySelectorAll('.filter-btns .apex-btn-outline').forEach(b => b.classList.remove('active'));
    const btn = document.getElementById(`filter-${days}`);
    if (btn) btn.classList.add('active');

    // Fetch stats
    fetch(`/api/stats/streaks`).then(r => r.json()).then(data => {
        document.getElementById('val-streak').textContent = data.current_streak || 0;
        document.getElementById('val-total').textContent = data.total_workouts || 0;
        document.getElementById('val-weekly-tss').textContent = data.weekly_tss || 0;
    }).catch(() => { });

    // Fetch workouts (Strava-only by default)
    fetch(`/api/workouts?period=${days}&source=strava`).then(r => r.json()).then(data => {
        window._dashboardWorkouts = data.workouts || [];
        renderRecentWorkouts(data.workouts || []);
    }).catch(() => { });

    // Fetch and cache full heatmap, then slice for period
    if (!cachedHeatmapGrid) {
        fetch('/api/analytics/heatmap').then(r => r.json()).then(data => {
            cachedHeatmapGrid = data.grid || [];
            renderHeatmap(cachedHeatmapGrid, days);
        }).catch(() => { });
    } else {
        renderHeatmap(cachedHeatmapGrid, days);
    }
}

// ── Map Viewer (Leaflet) ───────────────────────────────────────────────
let map = null;
let trackLayer = null;

function initMap() {
    try {
        map = L.map('map').setView([20, 0], 2);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '©OpenStreetMap ©CARTO', maxZoom: 19
        }).addTo(map);
    } catch (e) { }
}

function handleGPXUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    fetch('/api/workouts/upload-gpx', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.coordinates?.length) {
                if (trackLayer) map.removeLayer(trackLayer);
                trackLayer = L.polyline(data.coordinates, {
                    color: '#00d4ff', weight: 3, opacity: 0.9
                }).addTo(map);
                map.fitBounds(trackLayer.getBounds(), { padding: [30, 30] });
            }
        })
        .catch(err => console.error('GPX upload failed:', err));
}

function loadDailyInsight() {
    fetch('/api/coach/daily-insight').then(r => r.json()).then(data => {
        document.getElementById('daily-insight').textContent = data.insight;
    }).catch(() => {
        document.getElementById('daily-insight').textContent = 'Could not load insight.';
    });
}

// V4: Heatmap with period-aware rendering
function renderHeatmap(grid, periodDays = 365) {
    const container = document.getElementById('heatmap-container');
    if (!container) return;
    container.innerHTML = '';

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const periodCutoff = new Date(today);
    periodCutoff.setDate(today.getDate() - periodDays);

    grid.forEach(cell => {
        const el = document.createElement('div');
        el.className = 'heatmap-cell';
        const tss = cell.tss || 0;
        const cellDate = new Date(cell.date);
        const inPeriod = cellDate >= periodCutoff;

        if (tss === 0) {
            el.style.background = 'rgba(255,255,255,0.03)';
        } else if (tss < 30) {
            el.style.background = inPeriod ? 'rgba(0,212,255,0.2)' : 'rgba(255,255,255,0.04)';
        } else if (tss < 70) {
            el.style.background = inPeriod ? 'rgba(0,212,255,0.45)' : 'rgba(255,255,255,0.06)';
        } else if (tss < 120) {
            el.style.background = inPeriod ? 'rgba(0,212,255,0.7)' : 'rgba(255,255,255,0.08)';
        } else {
            el.style.background = inPeriod ? '#00d4ff' : 'rgba(255,255,255,0.1)';
        }
        if (!inPeriod) el.style.opacity = '0.35';
        el.title = `${cell.date}: TSS ${tss}`;
        container.appendChild(el);
    });
}

window._dashboardWorkouts = [];

function renderRecentWorkouts(workouts) {
    const container = document.getElementById('recent-workouts');
    if (!container) return;
    if (!workouts.length) {
        container.innerHTML = '<p style="color:var(--apex-muted);">No Strava activities yet. Connect Strava to sync.</p>';
        return;
    }
    container.innerHTML = workouts.slice(0, 15).map((w, i) => {
        const dist = w.distance_meters ? (w.distance_meters / 1000).toFixed(1) : null;
        const dur = w.duration_seconds ? Math.round(w.duration_seconds / 60) : 0;
        const sport = w.sport_type || w.sport || 'Workout';
        const name = w.name || sport;
        // V4: Badges for suffer_score, PR count
        let badges = '';
        if (w.suffer_score) badges += `<span class="badge badge-effort">⚡${w.suffer_score}</span>`;
        if (w.pr_count > 0) badges += `<span class="badge badge-pr">🏅 ${w.pr_count} PR${w.pr_count > 1 ? 's' : ''}</span>`;
        if (w.achievement_count > 0) badges += `<span class="badge badge-ach">🏆 ${w.achievement_count}</span>`;

        return `<div class="workout-card" onclick="showWorkoutDetail(${w.id})">
            <div class="wc-top"><strong>${name}</strong> <span class="wc-date">${w.date}</span></div>
            <div class="wc-stats">
                ${dist ? `<span>📏 ${dist} km</span>` : ''}
                <span>⏱ ${dur} min</span>
                ${w.avg_hr ? `<span>❤️ ${w.avg_hr} bpm</span>` : ''}
                ${w.tss ? `<span>📊 TSS ${Math.round(w.tss)}</span>` : ''}
            </div>
            ${badges ? `<div class="wc-badges">${badges}</div>` : ''}
        </div>`;
    }).join('');
}

let wdHrChart = null;

function showWorkoutDetail(workoutId) {
    const w = window._dashboardWorkouts.find(x => x.id === workoutId);
    if (!w) return;

    document.getElementById('workout-detail-modal').style.display = 'flex';
    document.getElementById('wd-title').textContent = w.name || w.sport_type || 'Workout';

    const dist = w.distance_meters ? (w.distance_meters / 1000).toFixed(2) : 'N/A';
    const dur = w.duration_seconds ? `${Math.floor(w.duration_seconds / 60)}:${String(Math.round(w.duration_seconds % 60)).padStart(2, '0')}` : 'N/A';
    const pace = w.distance_meters && w.duration_seconds
        ? `${Math.floor(w.duration_seconds / (w.distance_meters / 1000) / 60)}:${String(Math.round((w.duration_seconds / (w.distance_meters / 1000)) % 60)).padStart(2, '0')} /km`
        : 'N/A';

    let html = `
        <div class="wd-stats-grid">
            <div class="wd-stat"><span class="wd-label">Date</span><span class="wd-val">${w.date}</span></div>
            <div class="wd-stat"><span class="wd-label">Sport</span><span class="wd-val">${w.sport_type || w.sport || 'N/A'}</span></div>
            <div class="wd-stat"><span class="wd-label">Distance</span><span class="wd-val">${dist} km</span></div>
            <div class="wd-stat"><span class="wd-label">Duration</span><span class="wd-val">${dur}</span></div>
            <div class="wd-stat"><span class="wd-label">Avg Pace</span><span class="wd-val">${pace}</span></div>
            <div class="wd-stat"><span class="wd-label">Avg HR</span><span class="wd-val">${w.avg_hr || 'N/A'} bpm</span></div>
            <div class="wd-stat"><span class="wd-label">Max HR</span><span class="wd-val">${w.max_hr || 'N/A'} bpm</span></div>
            <div class="wd-stat"><span class="wd-label">TSS</span><span class="wd-val">${w.tss ? Math.round(w.tss) : 'N/A'}</span></div>
            <div class="wd-stat"><span class="wd-label">Elevation</span><span class="wd-val">${w.elevation_gain_m || 0}m</span></div>
            <div class="wd-stat"><span class="wd-label">Cadence</span><span class="wd-val">${w.avg_cadence || 'N/A'} spm</span></div>
            ${w.suffer_score ? `<div class="wd-stat"><span class="wd-label">Rel. Effort</span><span class="wd-val">${w.suffer_score}</span></div>` : ''}
            ${w.pr_count ? `<div class="wd-stat"><span class="wd-label">PRs</span><span class="wd-val">🏅 ${w.pr_count}</span></div>` : ''}
        </div>
        <div style="margin-top:15px;"><canvas id="wd-hr-chart" height="120"></canvas></div>
    `;

    document.getElementById('wd-body').innerHTML = html;

    // HR chart from stream
    setTimeout(() => {
        let hrData = [];
        let timeData = [];
        try { hrData = JSON.parse(w.hr_stream || '[]'); } catch (e) { }
        try { timeData = JSON.parse(w.time_stream || '[]'); } catch (e) { }
        if (hrData.length > 0) {
            if (wdHrChart) wdHrChart.destroy();
            const step = Math.max(1, Math.floor(hrData.length / 200));
            const hrSampled = hrData.filter((_, i) => i % step === 0);
            const labels = hrSampled.map((_, i) => '');
            wdHrChart = new Chart(document.getElementById('wd-hr-chart'), {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Heart Rate', data: hrSampled,
                        borderColor: '#ff6b6b', borderWidth: 1.5,
                        pointRadius: 0, fill: true,
                        backgroundColor: 'rgba(255,107,107,0.08)'
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                    }
                }
            });
        }
    }, 100);
}

function closeWorkoutDetail() {
    document.getElementById('workout-detail-modal').style.display = 'none';
}

// ── Analytics Loading ──────────────────────────────────────────────────
function loadAnalytics() {
    fetch('/api/analytics/pmc').then(r => r.json()).then(data => {
        renderPMCChart(data.series || []);
    }).catch(() => { });
    fetch('/api/analytics/zones').then(r => r.json()).then(data => {
        renderZoneTable(data.zones || {});
        renderZoneChart(data.distribution || {});
    }).catch(() => { });
}

function renderPMCChart(series) {
    const ctx = document.getElementById('pmc-chart');
    if (!ctx) return;
    if (pmcChart) pmcChart.destroy();
    const labels = series.map(d => d.date);
    pmcChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'CTL – Fitness (42-day)',
                    data: series.map(d => d.ctl),
                    borderColor: '#00d4ff', borderWidth: 2, pointRadius: 0,
                    fill: false, tension: 0.3
                },
                {
                    label: 'ATL – Fatigue (7-day)',
                    data: series.map(d => d.atl),
                    borderColor: '#ff6b35', borderWidth: 2, pointRadius: 0,
                    fill: false, tension: 0.3
                },
                {
                    label: 'TSB – Form (Fitness − Fatigue)',
                    data: series.map(d => d.tsb),
                    borderColor: '#00e676', borderWidth: 2, pointRadius: 0,
                    fill: true, backgroundColor: 'rgba(0,230,118,0.06)', tension: 0.3
                },
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { color: '#fff', font: { family: 'Space Grotesk', size: 12 }, padding: 15, usePointStyle: true }
                },
                tooltip: {
                    callbacks: {
                        afterBody: function (items) {
                            const tsbItem = items.find(i => i.dataset.label.startsWith('TSB'));
                            if (tsbItem) {
                                const tsb = tsbItem.raw;
                                if (tsb > 25) return 'Status: Detraining risk ⚠️';
                                if (tsb >= 5) return 'Status: Optimal race form 🏁';
                                if (tsb >= -10) return 'Status: Maintenance zone 👍';
                                if (tsb >= -30) return 'Status: Productive training 💪';
                                return 'Status: Overreaching — monitor ⛔';
                            }
                        }
                    }
                }
            },
            scales: {
                x: { ticks: { color: '#666', maxTicksLimit: 12 }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.06)' } }
            }
        }
    });
}

function renderZoneTable(zones) {
    const table = document.getElementById('zone-table');
    if (!table) return;
    const colors = ['#00e676', '#4fc3f7', '#ffd54f', '#ff7043', '#e53935'];
    let html = '<tr><th>Zone</th><th>Min HR</th><th>Max HR</th></tr>';
    let i = 0;
    for (const [z, { min, max }] of Object.entries(zones)) {
        html += `<tr><td style="color:${colors[i]}">${z}</td><td>${min}</td><td>${max}</td></tr>`;
        i++;
    }
    table.innerHTML = html;
}

function renderZoneChart(distribution) {
    const ctx = document.getElementById('zone-chart');
    if (!ctx) return;
    if (zoneChart) zoneChart.destroy();
    const labels = Object.keys(distribution);
    const values = Object.values(distribution);
    const colors = ['#00e676', '#4fc3f7', '#ffd54f', '#ff7043', '#e53935'];
    zoneChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{ data: values, backgroundColor: colors.slice(0, labels.length), borderRadius: 6 }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#fff' }, grid: { display: false } },
                y: { ticks: { color: '#888', callback: v => v + '%' }, grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}

// ── V4: Race Predictor with HH:MM:SS ──────────────────────────────────
function predictRaces() {
    const h = parseInt(document.getElementById('pred-hours').value) || 0;
    const m = parseInt(document.getElementById('pred-minutes').value) || 0;
    const s = parseInt(document.getElementById('pred-seconds').value) || 0;
    const totalSec = (h * 3600) + (m * 60) + s;
    if (totalSec <= 0) { alert('Please enter a valid time'); return; }

    const distKm = parseFloat(document.getElementById('pred-known-dist').value);
    const timeString = `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

    fetch('/api/predict/races', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ distance_km: distKm, time_string: timeString })
    })
        .then(r => r.json())
        .then(data => {
            const preds = data.predictions || [];
            let html = `<div class="vdot-badge">VDOT: <strong>${data.vdot?.toFixed(1) || '?'}</strong></div>`;
            html += `<table class="predictor-table"><thead><tr>
                <th>Distance</th><th>Predicted Time</th><th>Pace/km</th><th>Pace/mi</th>
            </tr></thead><tbody>`;
            preds.forEach(p => {
                html += `<tr>
                    <td>${p.label}</td>
                    <td class="font-mono">${p.predicted_time}</td>
                    <td class="font-mono">${p.pace_per_km || '-'}</td>
                    <td class="font-mono">${p.pace_per_mi || '-'}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            document.getElementById('predictor-result').innerHTML = html;
        })
        .catch(() => {
            document.getElementById('predictor-result').innerHTML = '<p style="color:#ff6b6b;">Prediction failed.</p>';
        });
}

// ── Training Plan ──────────────────────────────────────────────────────
function loadPlan() {
    fetch('/api/planner/current').then(r => r.json()).then(data => {
        if (data.plan) {
            document.getElementById('plan-header-info').innerHTML =
                `<span>📅 ${data.plan.goal} · Target: ${data.plan.target_date}</span>`;
            document.getElementById('btn-adjust-plan').style.display = 'inline-flex';
            renderPlanCalendar(formatPlanForCalendar(data.plan, data.workouts));
        } else {
            document.getElementById('plan-header-info').innerHTML = '<span>No active plan — Generate one to get started!</span>';
            document.getElementById('btn-adjust-plan').style.display = 'none';
            document.getElementById('plan-calendar').innerHTML =
                '<p style="color:var(--apex-muted);text-align:center;padding:2rem;">Click "Generate Plan" to build your training plan.</p>';
        }
    }).catch(() => { });
}

function formatPlanForCalendar(dbPlan, dbWorkouts) {
    const weeks = {};
    const start = new Date(dbWorkouts[0]?.date || dbPlan.created_at);
    dbWorkouts.forEach(w => {
        const d = new Date(w.date);
        const weekNum = Math.floor((d - start) / (7 * 86400000)) + 1;
        if (!weeks[weekNum]) weeks[weekNum] = { week_number: weekNum, focus: '', workouts: [] };
        weeks[weekNum].workouts.push({
            ...w,
            day: d.toLocaleDateString('en-US', { weekday: 'long' }),
            type: w.workout_type,
            distance_km: w.planned_distance_meters ? (w.planned_distance_meters / 1000).toFixed(1) : 0,
            duration_min: w.planned_duration_seconds ? Math.round(w.planned_duration_seconds / 60) : 0,
        });
    });
    return { plan_name: dbPlan.goal, goal: dbPlan.goal, weeks: Object.values(weeks) };
}

function renderPlanCalendar(plan) {
    const container = document.getElementById('plan-calendar');
    if (!container || !plan.weeks) return;

    const today = new Date().toISOString().split('T')[0];
    let html = '';
    plan.weeks.forEach(week => {
        html += `<div class="plan-week apex-card">
            <div class="week-header" onclick="toggleWeek(${week.week_number})">
                <strong>Week ${week.week_number}</strong>
                <span>${week.focus || ''}</span>
                <i data-lucide="chevron-down" class="week-chevron" id="chev-${week.week_number}"></i>
            </div>
            <div class="week-body" id="week-${week.week_number}" style="display:none;">`;

        (week.workouts || []).forEach(w => {
            const wDate = w.date || '';
            let stateClass = 'workout-upcoming';
            let stateLabel = '📋 Upcoming';
            if (w.completed) {
                stateClass = 'workout-completed';
                stateLabel = '✅ Completed';
            } else if (wDate <= today) {
                stateClass = 'workout-due';
                stateLabel = '⚡ Due';
            }

            const typeClass = 'type-' + (w.type || '').toLowerCase().replace(/[^a-z]/g, '').replace('easyrun', 'easy').replace('longrun', 'long');

            html += `<div class="plan-day ${typeClass} ${stateClass}">
                <div class="d-header">
                    <span class="d-title">${w.type || w.workout_type || 'Workout'}</span>
                    <span class="d-state-badge">${stateLabel}</span>
                </div>
                <div class="d-meta">
                    <span>${w.day || ''} · ${wDate}</span>
                    ${w.distance_km ? `<span>📏 ${w.distance_km} km</span>` : ''}
                    ${w.duration_min ? `<span>⏱ ${w.duration_min} min</span>` : ''}
                </div>
                <p class="d-desc">${w.description || ''}</p>`;

            // V4: Show planned vs actual for completed workouts
            if (w.completed && w.execution_score) {
                let scoreBadge = '';
                try {
                    const fb = JSON.parse(w.execution_feedback || '{}');
                    scoreBadge = `<div class="execution-card">
                        <span class="score-badge">${w.execution_score.toFixed(1)}/10</span>
                        <span class="score-headline">${fb.headline || ''}</span>
                    </div>`;
                } catch (e) { }

                const actDist = w.actual_distance_meters ? (w.actual_distance_meters / 1000).toFixed(1) + ' km' : '-';
                const actDur = w.actual_duration_seconds ? Math.round(w.actual_duration_seconds / 60) + ' min' : '-';

                html += `<div class="planned-vs-actual">
                    <div class="pva-planned"><small>Planned</small><br>${w.distance_km || 0} km · ${w.duration_min || 0} min</div>
                    <div class="pva-actual"><small>Actual</small><br>${actDist} · ${actDur}${w.actual_avg_hr ? ` · ${w.actual_avg_hr} bpm` : ''}</div>
                </div>
                ${scoreBadge}`;
                if (w.llm_comment) html += `<p class="llm-comment">💡 ${w.llm_comment}</p>`;
                if (w.user_notes) html += `<p class="user-note">📝 ${w.user_notes}</p>`;
            }

            // Execution button for due workouts
            if (!w.completed && wDate <= today) {
                html += `<button class="apex-btn-sm" onclick="openExecution(${w.id}, event)">Log Execution</button>`;
            }

            html += `</div>`;
        });
        html += '</div></div>';
    });
    container.innerHTML = html;
    lucide.createIcons();
}

function toggleWeek(num) {
    const body = document.getElementById(`week-${num}`);
    if (body) body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

// ── V4: Pre-Plan Interview Modal ───────────────────────────────────────
function openInterviewModal() {
    document.getElementById('interview-modal').style.display = 'flex';
    // Set default start date to today
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('iv-start-date').value = today;
    lucide.createIcons();
}

function closeInterviewModal() {
    document.getElementById('interview-modal').style.display = 'none';
}

function parseTimeToSeconds(str) {
    if (!str) return null;
    const parts = str.split(':').map(Number);
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    return null;
}

function submitInterview() {
    const goal = document.getElementById('iv-goal').value;
    const targetDate = document.getElementById('iv-target-date').value;
    const startDate = document.getElementById('iv-start-date').value;
    if (!goal || !targetDate || !startDate) { alert('Please fill required fields'); return; }

    const reqBody = {
        goal,
        target_date: targetDate,
        start_date: startDate,
        weekly_hours: parseFloat(document.getElementById('iv-hours').value) || 8,
        days_per_week: parseInt(document.getElementById('iv-days').value) || 5,
        experience_level: document.getElementById('iv-experience').value,
        current_weekly_km: parseFloat(document.getElementById('iv-weekly-km').value) || null,
        pb_5k_seconds: parseTimeToSeconds(document.getElementById('iv-pb-5k').value),
        pb_10k_seconds: parseTimeToSeconds(document.getElementById('iv-pb-10k').value),
        pb_hm_seconds: parseTimeToSeconds(document.getElementById('iv-pb-hm').value),
        pb_marathon_seconds: parseTimeToSeconds(document.getElementById('iv-pb-marathon').value),
        pb_other_text: document.getElementById('iv-pb-other').value || null,
        injury_notes: document.getElementById('iv-injury').value || null,
    };

    currentPlanMeta = reqBody;
    closeInterviewModal();

    // Show skeleton
    document.getElementById('plan-preview-container').style.display = 'none';
    document.getElementById('plan-calendar-container').style.display = 'block';
    const skeleton = document.getElementById('plan-skeleton');
    skeleton.style.display = 'block';

    // Stream plan generation
    let buffer = '';
    fetch('/api/planner/generate-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqBody)
    }).then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        function read() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    // Parse complete JSON
                    try {
                        currentPlanJSON = JSON.parse(buffer);
                        skeleton.style.display = 'none';
                        renderPlanPreview(currentPlanJSON);
                    } catch (e) {
                        skeleton.innerHTML = '<p style="color:#ff6b6b;">Failed to parse plan. Try again.</p>';
                    }
                    return;
                }
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.token) buffer += data.token;
                        } catch (e) { }
                    }
                }
                read();
            });
        }
        read();
    }).catch(err => {
        skeleton.innerHTML = '<p style="color:#ff6b6b;">Plan generation failed.</p>';
    });
}

// V4: Render plan preview table
function renderPlanPreview(planJSON) {
    document.getElementById('plan-calendar-container').style.display = 'none';
    document.getElementById('plan-preview-container').style.display = 'block';

    const tbody = document.querySelector('#plan-preview-table tbody');
    tbody.innerHTML = '';

    const typeColors = {
        'easy run': '#00e676', 'easy': '#00e676', 'recovery': '#00e676',
        'interval': '#ff4444', 'intervals': '#ff4444', 'speed': '#ff4444',
        'tempo': '#ff6b35', 'threshold': '#ff6b35',
        'long run': '#42a5f5', 'long': '#42a5f5',
        'rest': '#666', 'off': '#666',
        'cross': '#ba68c8', 'cross-train': '#ba68c8', 'cross training': '#ba68c8',
    };

    (planJSON.weeks || []).forEach(week => {
        (week.workouts || []).forEach(w => {
            const typeLower = (w.type || '').toLowerCase();
            const color = typeColors[typeLower] || '#00d4ff';
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${week.week_number}</td>
                <td>${w.day || ''}</td>
                <td><span class="type-badge" style="background:${color}20;color:${color};border:1px solid ${color}40;">${w.type || 'Workout'}</span></td>
                <td class="font-mono">${w.distance_km || '-'} km</td>
                <td class="font-mono">${w.duration_min || '-'} min</td>
                <td class="font-mono">${w.pace_min_per_km ? w.pace_min_per_km.toFixed(2) + '/km' : '-'}</td>
                <td>${w.description || ''}</td>
            `;
            tbody.appendChild(row);
        });
    });
}

function confirmPlan() {
    if (!currentPlanJSON || !currentPlanMeta) return;

    fetch('/api/planner/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            plan_json: currentPlanJSON,
            goal: currentPlanMeta.goal,
            target_date: currentPlanMeta.target_date,
            weekly_hours: currentPlanMeta.weekly_hours,
            start_date: currentPlanMeta.start_date,
        })
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                document.getElementById('plan-preview-container').style.display = 'none';
                document.getElementById('plan-calendar-container').style.display = 'block';
                currentPlanJSON = null;
                currentPlanMeta = null;
                loadPlan();
            }
        })
        .catch(err => alert('Failed to save plan'));
}

function startOverPlan() {
    currentPlanJSON = null;
    currentPlanMeta = null;
    document.getElementById('plan-preview-container').style.display = 'none';
    document.getElementById('plan-calendar-container').style.display = 'block';
}

// ── V4: Plan Adjust Drawer ─────────────────────────────────────────────
function openAdjustDrawer() {
    document.getElementById('adjust-drawer').style.display = 'flex';
    lucide.createIcons();
}

function closeAdjustDrawer() {
    document.getElementById('adjust-drawer').style.display = 'none';
}

function sendAdjustMessage() {
    const input = document.getElementById('adjust-input');
    const instruction = input.value.trim();
    if (!instruction) return;
    input.value = '';

    const chatContainer = document.getElementById('adjust-chat-container');
    chatContainer.innerHTML += `<div class="message user"><div class="msg-content"><p>${instruction}</p></div></div>`;

    // Need current plan JSON
    fetch('/api/planner/current').then(r => r.json()).then(data => {
        if (!data.plan) return;

        // Stream adjust
        const assistantDiv = document.createElement('div');
        assistantDiv.className = 'message assistant';
        assistantDiv.innerHTML = '<div class="msg-content"><p>Adjusting plan...</p></div>';
        chatContainer.appendChild(assistantDiv);

        let buffer = '';
        fetch('/api/planner/adjust', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                plan_json: { weeks: data.workouts },
                instruction: instruction,
                plan_id: data.plan.id,
            })
        }).then(response => {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            function read() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        try {
                            currentPlanJSON = JSON.parse(buffer);
                            assistantDiv.querySelector('.msg-content p').textContent =
                                `Plan adjusted! ${currentPlanJSON.weeks?.length || 0} weeks updated. Click "Confirm" to apply.`;
                            currentPlanMeta = data.plan;
                            renderPlanPreview(currentPlanJSON);
                            document.getElementById('plan-preview-container').style.display = 'block';
                            document.getElementById('plan-calendar-container').style.display = 'none';
                        } catch (e) {
                            assistantDiv.querySelector('.msg-content p').textContent = 'Failed to parse adjusted plan.';
                        }
                        return;
                    }
                    const chunk = decoder.decode(value);
                    for (const line of chunk.split('\n')) {
                        if (line.startsWith('data: ')) {
                            try {
                                const d = JSON.parse(line.slice(6));
                                if (d.token) buffer += d.token;
                            } catch (e) { }
                        }
                    }
                    read();
                });
            }
            read();
        });
    });
}

// ── Execution Modal ────────────────────────────────────────────────────
function ensureExecutionModal() {
    if (document.getElementById('execution-modal')) return;
    const modal = document.createElement('div');
    modal.id = 'execution-modal';
    modal.className = 'modal-overlay';
    modal.style.display = 'none';
    modal.innerHTML = `<div class="modal-content"><div class="modal-header"><h3>Log Execution</h3>
        <button class="modal-close" onclick="closeExecution()">&times;</button></div>
        <div class="modal-body" id="exec-body"></div></div>`;
    document.body.appendChild(modal);
}

function openExecution(workoutId, event) {
    if (event) event.stopPropagation();
    ensureExecutionModal();

    const w = null; // Would need to fetch planned workout
    document.getElementById('execution-modal').style.display = 'flex';
    document.getElementById('exec-body').innerHTML = `
        <div class="form-group">
            <label>Completion Status</label>
            <select id="exec-status">
                <option value="completed">Completed</option>
                <option value="partial">Partial</option>
                <option value="skipped">Skipped</option>
            </select>
        </div>
        <div id="exec-skip-reason" style="display:none;" class="form-group">
            <label>Reason</label>
            <select id="exec-reason">
                <option value="injury">Injury</option>
                <option value="time">Time</option>
                <option value="fatigue">Fatigue</option>
                <option value="weather">Weather</option>
                <option value="other">Other</option>
            </select>
        </div>
        <div class="interview-grid">
            <div class="form-group">
                <label>Actual Distance (km)</label>
                <input type="number" id="exec-distance" step="0.1">
            </div>
            <div class="form-group">
                <label>Actual Duration (min)</label>
                <input type="number" id="exec-duration">
            </div>
            <div class="form-group">
                <label>Average HR</label>
                <input type="number" id="exec-hr">
            </div>
            <div class="form-group">
                <label>RPE (1-10)</label>
                <input type="number" id="exec-rpe" min="1" max="10">
            </div>
        </div>
        <div class="form-group">
            <label>Notes (How did it feel?)</label>
            <textarea id="exec-notes" rows="2" placeholder="How was the workout?"></textarea>
        </div>
        <button class="apex-btn" onclick="scoreExecution(${workoutId})">Score Execution</button>
        <div id="exec-result"></div>
    `;

    document.getElementById('exec-status').addEventListener('change', function () {
        document.getElementById('exec-skip-reason').style.display =
            this.value !== 'completed' ? 'block' : 'none';
    });
}

function closeExecution() {
    const modal = document.getElementById('execution-modal');
    if (modal) modal.style.display = 'none';
}

function scoreExecution(workoutId) {
    const status = document.getElementById('exec-status').value;
    const distKm = parseFloat(document.getElementById('exec-distance').value) || 0;
    const durMin = parseFloat(document.getElementById('exec-duration').value) || 0;
    const avgPace = distKm > 0 ? (durMin * 60) / distKm : 300;

    const body = {
        planned_workout_id: workoutId,
        execution_data: {
            completion_status: status,
            actual_distance_meters: distKm * 1000,
            actual_duration_seconds: durMin * 60,
            actual_avg_hr: parseInt(document.getElementById('exec-hr').value) || null,
            rpe: parseInt(document.getElementById('exec-rpe').value) || null,
            avg_pace_sec_per_km: avgPace,
            notes: document.getElementById('exec-notes').value,
            skipped_reason: status !== 'completed' ? document.getElementById('exec-reason').value : null,
            splits: [{ rep: 1, pace_sec_per_km: Math.round(avgPace), hr: parseInt(document.getElementById('exec-hr').value) || 0 }],
        }
    };

    document.getElementById('exec-result').innerHTML = '<p>Scoring...</p>';

    fetch('/api/planner/score-execution', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    })
        .then(r => r.json())
        .then(result => {
            let html = `<div class="execution-card" style="margin-top:15px;">
                <div class="score-badge">${result.score}/10 (${result.grade})</div>
                <p><strong>${result.headline}</strong></p>
                <p>${result.summary || result.pacing_analysis || ''}</p>`;
            if (result.strengths?.length) html += `<p>✅ ${result.strengths.join(', ')}</p>`;
            if (result.improvements?.length) html += `<p>💡 ${result.improvements.join(', ')}</p>`;
            if (result.coaching_advice) html += `<p>🎯 ${result.coaching_advice}</p>`;
            if (result.adjust_next_workout) {
                html += `<div class="adjust-suggestion">
                    <p>📊 Based on this effort, consider adjusting your next workout.</p>
                    <button class="apex-btn-sm" onclick="closeExecution();openAdjustDrawer();">Yes, adjust</button>
                </div>`;
            }
            html += '</div>';
            document.getElementById('exec-result').innerHTML = html;
        })
        .catch(() => {
            document.getElementById('exec-result').innerHTML = '<p style="color:#ff6b6b;">Scoring failed.</p>';
        });
}

// ── ICS Export ─────────────────────────────────────────────────────────
function exportICS() {
    fetch('/api/planner/current').then(r => r.json()).then(data => {
        if (!data.workouts?.length) return alert('No plan to export');
        let ics = 'BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//APEX//Endurance Coach//EN\n';
        data.workouts.forEach(w => {
            const d = w.date.replace(/-/g, '');
            ics += `BEGIN:VEVENT\nDTSTART;VALUE=DATE:${d}\nSUMMARY:${w.workout_type}\nDESCRIPTION:${(w.description || '').replace(/\n/g, '\\n')}\nEND:VEVENT\n`;
        });
        ics += 'END:VCALENDAR';
        const blob = new Blob([ics], { type: 'text/calendar' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'apex_plan.ics';
        a.click();
    });
}

// ── Chat Functions ─────────────────────────────────────────────────────
const chatContainer = document.getElementById('chat-container');
const welcomeScreen = document.getElementById('welcome-screen');
const userInput = document.getElementById('user-input');
const newChatBtn = document.getElementById('new-chat-btn');

function setPrompt(text) {
    userInput.value = text;
    userInput.focus();
}

// Auto-resize textarea
userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 140) + 'px';
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

newChatBtn.addEventListener('click', () => {
    chatHistories[currentChatMode] = [];
    chatContainer.innerHTML = '';
    chatContainer.appendChild(welcomeScreen);
    welcomeScreen.style.display = 'flex';
    switchChatMode(currentChatMode);
    switchTab('chat');
});

function createMessageDiv(role, content) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    if (role === 'assistant') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.innerHTML = `<p>${content}</p>`;
    }
    msgDiv.appendChild(contentDiv);
    return msgDiv;
}

function addMessage(role, content) {
    if (welcomeScreen.style.display !== 'none') {
        welcomeScreen.style.display = 'none';
    }
    const msgDiv = createMessageDiv(role, content);
    chatContainer.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return msgDiv;
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;
    userInput.value = '';
    userInput.style.height = 'auto';

    chatHistories[currentChatMode].push({ role: 'user', content: text });
    addMessage('user', text);

    const assistantDiv = addMessage('assistant', '');
    const contentDiv = assistantDiv.querySelector('.msg-content');
    contentDiv.innerHTML = '<span class="typing-indicator">●●●</span>';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                messages: chatHistories[currentChatMode].map(m => ({ role: m.role, content: m.content })),
                mode: currentChatMode
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const raw = line.slice(6).trim();
                    if (raw === '[DONE]') break;
                    try {
                        const data = JSON.parse(raw);
                        if (data.type === 'metadata') {
                            renderSources(data.sources || []);
                        } else if (data.type === 'content') {
                            fullText += data.text;
                            contentDiv.innerHTML = marked.parse(fullText);
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        }
                    } catch (e) { }
                }
            }
        }

        chatHistories[currentChatMode].push({ role: 'assistant', content: fullText });

    } catch (err) {
        contentDiv.innerHTML = '<p style="color:#ff6b6b;">Error connecting to server.</p>';
    }
}

function renderSources(sources) {
    const list = document.getElementById('sources-list');
    const count = document.getElementById('sources-count');
    if (!list) return;
    count.textContent = sources.length;
    list.innerHTML = sources.map(s =>
        `<div class="source-item"><span class="source-type">${s.type}</span>
         <span class="source-sport">${s.sport}</span>
         <span class="source-score">${(s.score * 100).toFixed(0)}%</span>
         <p class="source-preview">${s.preview}</p></div>`
    ).join('');
}

// ── Init ───────────────────────────────────────────────────────────────
switchChatMode('ask');
