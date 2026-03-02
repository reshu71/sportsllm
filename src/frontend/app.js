// ── APEX V2 — Frontend Application ─────────────────────────────────────
// State
let chatHistory = [];
let pmcChart = null;
let zoneChart = null;

// ── Tab Switching ──────────────────────────────────────────────────────
function switchTab(tab) {
    // Hide all wrappers
    document.getElementById('chat-wrapper').style.display = 'none';
    document.getElementById('dashboard-wrapper').style.display = 'none';
    document.getElementById('analytics-wrapper').style.display = 'none';
    document.getElementById('plan-wrapper').style.display = 'none';

    // Deactivate all tabs
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

    // Show selected wrapper + set active tab
    const titles = {
        chat: ['AI Coach', 'Ask me about running, cycling, triathlon, or swimming'],
        dashboard: ['Athlete Dashboard', 'Your fitness at a glance'],
        analytics: ['Analytics', 'Performance insights & predictions'],
        plan: ['Training Plan', 'AI-generated periodized schedules'],
    };
    const el = tab === 'chat' ? 'chat-wrapper' :
        tab === 'dashboard' ? 'dashboard-wrapper' :
            tab === 'analytics' ? 'analytics-wrapper' : 'plan-wrapper';
    document.getElementById(el).style.display = tab === 'chat' ? 'flex' : 'block';
    document.getElementById(`tab-${tab}`).classList.add('active');
    document.getElementById('page-title').textContent = titles[tab][0];
    document.getElementById('page-subtitle').textContent = titles[tab][1];

    // Hide focus areas when not on Coach tab
    const focusSection = document.getElementById('focus-areas-section');
    const sourcesSection = document.getElementById('sources-section');
    if (focusSection) focusSection.style.display = tab === 'chat' ? '' : 'none';
    if (sourcesSection) sourcesSection.style.display = tab === 'chat' ? '' : 'none';

    // Load data
    if (tab === 'dashboard') loadDashboard();
    if (tab === 'analytics') loadAnalytics();
    if (tab === 'plan') loadPlan();
}

// ── Dashboard Loading ──────────────────────────────────────────────────
async function loadDashboard() {
    try {
        const [profileRes, heatmapRes, pmcRes] = await Promise.all([
            fetch('/api/profile').then(r => r.json()),
            fetch('/api/analytics/heatmap').then(r => r.json()),
            fetch('/api/analytics/pmc').then(r => r.json()),
        ]);

        const p = profileRes.profile || {};
        document.getElementById('val-vdot').textContent = (p.current_vdot || 0).toFixed(1);
        document.getElementById('val-hr').textContent = `${p.resting_hr || '--'} / ${p.max_hr || '--'}`;

        const si = document.getElementById('syncIndicator');
        if (p.strava_connected) {
            si.innerHTML = '<span class="sync-dot"></span> <span style="color:var(--apex-success);font-size:0.8rem;">Live Sync</span>';
        }

        const latest = pmcRes.latest || {};
        document.getElementById('val-form').textContent = latest.tsb != null ? latest.tsb.toFixed(1) : '--';
        const formBadge = document.getElementById('form-label');
        if (pmcRes.form === 'Fresh') formBadge.style.color = '#42a5f5';
        else if (pmcRes.form === 'Optimal') formBadge.style.color = 'var(--apex-success)';
        else if (pmcRes.form === 'High Risk') formBadge.style.color = 'var(--apex-danger)';
        formBadge.textContent = `Form · ${pmcRes.form || '--'}`;
        document.getElementById('val-ramp').textContent = pmcRes.ramp_rate != null ? pmcRes.ramp_rate : '--';

        renderHeatmap(heatmapRes.grid || []);
        const loadText = document.getElementById('daily-insight');
        if (latest.tsb < -25) {
            loadText.innerHTML = "<strong>🔥 Coach Focus:</strong> High fatigue detected (TSB < -25). Prioritize Zone 1 active recovery or complete rest today to prevent overtraining.";
        } else if (latest.tsb > 15) {
            loadText.innerHTML = "<strong>⚡ Coach Focus:</strong> High freshness (TSB > 15). You are primed for a breakthrough interval session, FTP test, or race simulation.";
        } else {
            loadText.innerHTML = "<strong>✅ Coach Focus:</strong> Optimal base training zone. Keep accumulating volume with consistent 80/20 polarized efforts.";
        }

        loadDailyInsight(); // Appends AI insight as well
        initMap();

        // Load default 30 days stats summary
        await fetchDashboardStats(30);

    } catch (e) {
        console.error('Dashboard load error:', e);
    }
}

async function fetchDashboardStats(days = 30) {
    document.querySelectorAll('.time-filter-group button').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.time-filter-group button[onclick="fetchDashboardStats(${days})"]`);
    if (btn) btn.classList.add('active');

    try {
        const workoutsRes = await fetch(`/api/workouts?period=${days}`).then(r => r.json());
        const workouts = workoutsRes.workouts || [];

        const totalDist = workouts.reduce((s, w) => s + parseFloat(w.distance_meters || 0), 0) / 1000;
        const totalDurSec = workouts.reduce((s, w) => s + (w.duration_seconds || 0), 0);
        const totalTss = workouts.reduce((s, w) => s + (w.tss || 0), 0);

        document.getElementById('val-streak').textContent = `${workouts.length}`;
        document.getElementById('val-streak').nextElementSibling.textContent = '🏃 Activities';

        document.getElementById('val-longest').textContent = `${totalDist.toFixed(1)}`;
        document.getElementById('val-longest').nextElementSibling.textContent = '📏 Distance (km)';

        document.getElementById('val-total').textContent = `${Math.floor(totalDurSec / 3600)}h ${Math.round((totalDurSec % 3600) / 60)}m`;
        document.getElementById('val-total').nextElementSibling.textContent = '⏱️ Training Time';

        document.getElementById('val-weekly-tss').textContent = `${totalTss.toFixed(0)}`;
        document.getElementById('val-weekly-tss').nextElementSibling.textContent = '⚡ Total TSS';

        renderRecentWorkouts(workouts.slice(0, 10));
    } catch (e) { console.error('Stats fetch err: ', e); }
}

// ── Map Viewer (Leaflet) ───────────────────────────────────────────────
let map = null;
let trackLayer = null;

function initMap() {
    if (!map && document.getElementById('map-container')) {
        map = L.map('map-container').setView([0, 0], 2);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(map);
    }
}

async function handleGPXUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/workouts/upload-gpx', {
            method: 'POST',
            body: formData
        }).then(r => r.json());

        if (res.status === 'success' && res.coordinates.length > 0) {
            if (trackLayer) map.removeLayer(trackLayer); // remove old route

            // Draw new polyline
            trackLayer = L.polyline(res.coordinates, {
                color: 'var(--apex-primary)',
                weight: 4,
                opacity: 0.8,
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(map);

            // Auto fit bounds to the route
            map.fitBounds(trackLayer.getBounds(), { padding: [20, 20] });
        } else {
            alert('No GPS points found in GPX file.');
        }
    } catch (err) {
        console.error('GPX upload failed:', err);
        alert('Failed to parse GPX file. See console for details.');
    } finally {
        event.target.value = ''; // Reset input
    }
}

async function loadDailyInsight() {
    try {
        const res = await fetch('/api/coach/daily-insight').then(r => r.json());
        const insightEl = document.getElementById('daily-insight');
        insightEl.innerHTML += `<br><br><span style="color:var(--apex-muted); font-size:0.85rem;">🤖 AI Analysis: ${res.insight}</span>`;
    } catch {
        console.warn('Could not load AI insight.');
    }
}

function renderHeatmap(grid) {
    const container = document.getElementById('heatmap-container');
    container.innerHTML = '';
    grid.forEach(cell => {
        const div = document.createElement('div');
        div.className = 'heatmap-cell';
        const tss = cell.tss || 0;
        const color = tss === 0 ? '#1a1a2e' :
            tss <= 30 ? '#1a472a' :
                tss <= 60 ? '#2d6a4f' :
                    tss <= 100 ? '#52b788' : '#95d5b2';
        div.style.backgroundColor = color;
        div.title = `${cell.date}: ${tss.toFixed(0)} TSS`;
        container.appendChild(div);
    });
}

window._dashboardWorkouts = [];

function renderRecentWorkouts(workouts) {
    window._dashboardWorkouts = workouts; // Store for modal
    const container = document.getElementById('recent-workouts-list');
    if (!workouts.length) {
        container.innerHTML = '<p class="text-muted" style="padding: 20px; text-align: center;">No activities found in this period.</p>';
        return;
    }
    container.innerHTML = workouts.map(w => {
        const dist = ((w.distance_meters || 0) / 1000).toFixed(1);
        const dur = Math.round((w.duration_seconds || 0) / 60);
        let icon = '🏃';
        const sport = String(w.sport_category || w.sport || 'Run').toLowerCase();
        if (sport.includes('bike') || sport.includes('cycl')) icon = '🚴';
        if (sport.includes('swim')) icon = '🏊';
        if (sport.includes('flex') || sport.includes('yoga')) icon = '🧘';
        if (sport.includes('train') || sport.includes('weight')) icon = '🏋️';

        const title = w.title || `${icon} ${sport.charAt(0).toUpperCase() + sport.slice(1)}`;

        return `
        <div class="workout-item stats-card" onclick="showWorkoutDetail(${w.id})" style="cursor:pointer; display:flex; justify-content:space-between; align-items:center; padding: 15px; margin-bottom: 10px; border-radius: 8px; background: var(--apex-card-alt); border: 1px solid var(--apex-border); transition: all 0.2s;">
            <div class="w-meta">
                <div class="w-title" style="font-weight: 600; font-size: 1rem; color: var(--apex-primary);">${icon} ${title}</div>
                <div class="w-sub" style="font-size: 0.8rem; color: var(--apex-muted); margin-top: 4px;">
                    ${w.date} • ${dur} min • ${w.avg_hr ? w.avg_hr + ' bpm' : '-- bpm'}
                </div>
            </div>
            <div class="w-metric" style="text-align: right;">
                <div class="w-dist" style="font-size: 1.1rem; font-weight: bold; color: var(--apex-text);">${w.distance_meters > 0 ? dist + ' km' : ''}</div>
                <div class="w-tss" style="font-size: 0.8rem; color: var(--apex-warning);">${(w.tss || 0).toFixed(0)} TSS</div>
            </div>
        </div>`;
    }).join('');
}

let wdHrChart = null;
function showWorkoutDetail(workoutId) {
    const w = window._dashboardWorkouts.find(x => x.id === workoutId);
    if (!w) return;

    document.getElementById('wd-title').textContent = w.title || (w.sport_category || w.sport || 'Workout');
    document.getElementById('wd-date').textContent = w.date;

    let icon = '🏃';
    const sport = String(w.sport_category || w.sport || 'Run').toLowerCase();
    if (sport.includes('bike') || sport.includes('cycl')) icon = '🚴';
    if (sport.includes('swim')) icon = '🏊';
    if (sport.includes('flex') || sport.includes('yoga')) icon = '🧘';
    if (sport.includes('train') || sport.includes('weight')) icon = '🏋️';
    document.getElementById('wd-icon').textContent = icon;

    document.getElementById('wd-dist').textContent = w.distance_meters ? ((w.distance_meters) / 1000).toFixed(2) : '--';

    const h = Math.floor((w.duration_seconds || 0) / 3600);
    const m = Math.floor(((w.duration_seconds || 0) % 3600) / 60);
    document.getElementById('wd-time').textContent = h > 0 ? `${h}h ${m}m` : `${m}m`;

    document.getElementById('wd-pace').textContent = w.avg_hr ? w.avg_hr : '--';

    // GPX Map
    const mapContainer = document.getElementById('wd-map-container');
    const lapsData = w.laps_json;
    if (lapsData && lapsData !== '[]' && lapsData.length > 5) {
        mapContainer.style.display = 'block';
        try {
            const rawCoords = JSON.parse(lapsData);
            if (!window.wdMap) {
                window.wdMap = L.map('wd-map-container').setView([0, 0], 2);
                L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(window.wdMap);
            }
            if (window.wdTrackLayer) window.wdMap.removeLayer(window.wdTrackLayer);

            window.wdTrackLayer = L.polyline(rawCoords, {
                color: 'var(--apex-primary)', weight: 4, opacity: 0.8, lineCap: 'round', lineJoin: 'round'
            }).addTo(window.wdMap);

            // Fix map size bug when display changes from none to block
            setTimeout(() => {
                window.wdMap.invalidateSize();
                window.wdMap.fitBounds(window.wdTrackLayer.getBounds(), { padding: [20, 20] });
            }, 50);
        } catch (e) {
            console.error("Map plot detail fail", e);
            mapContainer.style.display = 'none';
        }
    } else {
        mapContainer.style.display = 'none';
    }

    // HR Chart
    const hrDataStr = w.hr_stream;
    const timeDataStr = w.time_stream;

    if (wdHrChart) wdHrChart.destroy();
    document.getElementById('wd-zone-bars').innerHTML = '';

    if (hrDataStr && timeDataStr && hrDataStr !== '[]' && hrDataStr.length > 5) {
        try {
            const hrList = JSON.parse(hrDataStr);
            const timeList = JSON.parse(timeDataStr);

            // Build Line Chart
            const ctx = document.getElementById('wd-hr-chart');
            wdHrChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: timeList.map(t => Math.round(t / 60)), // minutes
                    datasets: [{
                        label: 'Heart Rate',
                        data: hrList,
                        borderColor: '#ff5252',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        fill: true,
                        backgroundColor: 'rgba(255, 82, 82, 0.1)'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: false },
                        y: { min: Math.max(50, Math.min(...hrList) - 10) }
                    },
                    interaction: { intersect: false, mode: 'index' }
                }
            });

            // Build Zone Bars matching Strava
            // Using generic max 190, rest 50 for quick modal
            const max = 190; const rest = 50; const hrr = max - rest;
            const z1 = rest + hrr * 0.5; const z2 = rest + hrr * 0.6; const z3 = rest + hrr * 0.7; const z4 = rest + hrr * 0.8; const z5 = rest + hrr * 0.9;
            let counts = [0, 0, 0, 0, 0];
            hrList.forEach(hr => {
                if (hr < z2) counts[0]++; else if (hr < z3) counts[1]++; else if (hr < z4) counts[2]++; else if (hr < z5) counts[3]++; else counts[4]++;
            });
            const total = counts.reduce((a, b) => a + b, 0) || 1;
            const colors = ['#8892b0', '#52b788', '#f5c842', '#ff9800', '#ff5252'];
            const labels = ['Z1 Endurance', 'Z2 Moderate', 'Z3 Tempo', 'Z4 Threshold', 'Z5 Anaerobic'];

            let zoneHtml = '';
            for (let i = 4; i >= 0; i--) {
                const pct = (counts[i] / total) * 100;
                zoneHtml += `
                <div style="margin-bottom: 8px;">
                    <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--apex-muted); margin-bottom:2px;">
                        <span>${labels[i]}</span>
                        <span>${Math.round(counts[i] / 60)}m (${pct.toFixed(0)}%)</span>
                    </div>
                    <div style="width: 100%; height: 8px; background: rgba(255,255,255,0.05); border-radius: 4px; overflow:hidden;">
                        <div style="width: ${pct}%; height: 100%; background: ${colors[i]};"></div>
                    </div>
                </div>`;
            }
            document.getElementById('wd-zone-bars').innerHTML = zoneHtml;
        } catch (e) { console.error("HR map fail", e); }
    } else {
        document.getElementById('wd-zone-bars').innerHTML = '<p class="text-muted" style="font-size:12px;">No HR stream data for this activity.</p>';
    }

    document.getElementById('workout-detail-modal').style.display = 'flex';
}

function closeWorkoutDetail() {
    document.getElementById('workout-detail-modal').style.display = 'none';
}

// ── Analytics Loading ──────────────────────────────────────────────────
async function loadAnalytics() {
    try {
        const [pmcRes, zoneRes] = await Promise.all([
            fetch('/api/analytics/pmc').then(r => r.json()),
            fetch('/api/analytics/zones').then(r => r.json()),
        ]);
        renderPMCChart(pmcRes.series || []);
        renderZoneTable(zoneRes.zones || {});
        renderZoneChart(zoneRes.distribution || {});
    } catch (e) {
        console.error('Analytics load error:', e);
    }
}

function renderPMCChart(series) {
    const ctx = document.getElementById('pmc-chart');
    if (!ctx) return;
    if (pmcChart) pmcChart.destroy();

    const labels = series.map(d => d.date);
    const ctlData = series.map(d => d.ctl);
    const atlData = series.map(d => d.atl);
    const tsbData = series.map(d => d.tsb);

    pmcChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Fitness (CTL)', data: ctlData,
                    borderColor: '#4FC3F7', borderWidth: 2,
                    tension: 0.4, pointRadius: 0, fill: false,
                },
                {
                    label: 'Fatigue (ATL)', data: atlData,
                    borderColor: '#FF8A65', borderWidth: 2,
                    tension: 0.4, pointRadius: 0, fill: false,
                },
                {
                    label: 'Form (TSB)', data: tsbData,
                    borderColor: '#81C784', borderWidth: 1.5,
                    tension: 0.4, pointRadius: 0,
                    fill: { target: 'origin', above: 'rgba(129,199,132,0.06)', below: 'rgba(229,57,53,0.06)' },
                    segment: {
                        borderColor: ctx2 => {
                            const v = ctx2.p0.parsed.y;
                            return v < -30 ? '#e53935' : v < -5 ? '#FDD835' : '#81C784';
                        }
                    }
                },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { labels: { color: '#9e9e9e', font: { family: "'Space Grotesk',sans-serif", size: 11 } } },
                tooltip: {
                    backgroundColor: '#16161f', borderColor: '#333', borderWidth: 1,
                    titleFont: { family: "'Space Grotesk',sans-serif" },
                    bodyFont: { family: "'JetBrains Mono',monospace", size: 12 },
                },
            },
            scales: {
                x: { ticks: { color: '#546e7a', maxTicksLimit: 12, font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
                y: { ticks: { color: '#546e7a', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
            },
        }
    });
}

function renderZoneTable(zones) {
    const container = document.getElementById('zone-table');
    const colors = ['#4FC3F7', '#66BB6A', '#FDD835', '#FF8A65', '#e53935'];
    let i = 0;
    container.innerHTML = Object.entries(zones).map(([name, range]) => {
        const color = colors[i++ % colors.length];
        return `<div class="zone-row">
            <span class="zone-label">${name}</span>
            <div class="zone-bar" style="background:${color}; width:${20 + i * 15}%"></div>
            <span class="zone-range">${range.min} – ${range.max}</span>
        </div>`;
    }).join('');
}

function renderZoneChart(distribution) {
    const ctx = document.getElementById('zone-chart');
    if (!ctx) return;
    if (zoneChart) zoneChart.destroy();
    const labels = Object.keys(distribution);
    const data = Object.values(distribution);
    const bgColors = ['#4FC3F7', '#66BB6A', '#FDD835', '#FF8A65', '#e53935'];

    zoneChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{ data, backgroundColor: bgColors, borderWidth: 0 }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '65%',
            plugins: {
                legend: { position: 'right', labels: { color: '#9e9e9e', font: { family: "'Space Grotesk',sans-serif", size: 11 }, padding: 12 } },
            }
        }
    });
}

// ── Race Predictor ─────────────────────────────────────────────────────
async function predictRaces() {
    const dist = parseFloat(document.getElementById('rp-dist').value);
    const timeSec = parseInt(document.getElementById('rp-time').value);
    if (!dist || !timeSec) return;

    try {
        const res = await fetch('/api/predict/races', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ distance_km: dist, time_seconds: timeSec })
        }).then(r => r.json());

        document.getElementById('race-results').style.display = 'block';
        document.getElementById('vdot-badge').textContent = `⚡ VDOT ${res.vdot.toFixed(1)}`;

        const rows = Object.entries(res.predictions).map(([name, pred]) =>
            `<tr><td>${name}</td><td>${pred.formatted}</td></tr>`
        ).join('');
        document.getElementById('race-table').innerHTML = `<table class="race-table">
            <thead><tr><th>Distance</th><th>Predicted Time</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    } catch (e) {
        console.error('Race prediction error:', e);
    }
}

// ── Training Plan ──────────────────────────────────────────────────────
async function loadPlan() {
    try {
        const res = await fetch('/api/planner/current').then(r => r.json());
        const header = document.getElementById('active-plan-header');
        const calendar = document.getElementById('plan-calendar');
        const exportBtn = document.getElementById('export-ics-btn');

        if (res.plan && res.workouts && res.workouts.length > 0) {
            header.innerHTML = `<strong style="color:var(--apex-primary);">${res.plan.goal}</strong> · Target: ${res.plan.target_date}`;
            calendar.style.display = 'block';
            exportBtn.style.display = 'inline-flex';
            window._planWorkouts = res.workouts;

            const localizedPlan = formatPlanForCalendar(res.plan, res.workouts);
            renderPlanCalendar(localizedPlan);
        } else {
            header.textContent = 'No active plan. Click "Generate AI Plan" to create one.';
            calendar.style.display = 'none';
            exportBtn.style.display = 'none';
        }
    } catch (e) {
        console.error('Plan load error:', e);
    }
}

function formatPlanForCalendar(dbPlan, dbWorkouts) {
    if (!dbWorkouts.length) return { weeks: [] };
    const sorted = [...dbWorkouts].sort((a, b) => new Date(a.date) - new Date(b.date));
    const start = new Date(sorted[0].date);
    const startMonday = new Date(start);
    startMonday.setDate(start.getDate() - ((start.getDay() + 6) % 7));

    const weeksMap = {};
    dbWorkouts.forEach(w => {
        const d = new Date(w.date + 'T12:00:00');
        const diffTime = d - startMonday;
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        const weekNum = Math.floor(diffDays / 7) + 1;

        if (!weeksMap[weekNum]) {
            weeksMap[weekNum] = { week_number: weekNum, focus: "Training Week " + weekNum, workouts: [] };
        }

        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        const dayStr = days[d.getDay()].substring(0, 3);
        const descMatch = String(w.description || '').match(/Pace: (.*)\/km/);

        weeksMap[weekNum].workouts.push({
            id: w.id,
            day: dayStr,
            date: w.date,
            type: w.workout_type,
            distance_km: w.distance_meters ? (w.distance_meters / 1000).toFixed(1) : 0,
            duration_min: Math.round((w.duration_seconds || 0) / 60),
            pace_min_per_km: descMatch ? descMatch[1] : '--',
            description: String(w.description || '').split(' | Pace:')[0],
            completed: w.completed,
            execution_score: w.execution_score,
            execution_data: w.execution_data,
            execution_feedback: w.execution_feedback
        });
    });

    const weeks = Object.values(weeksMap).sort((a, b) => a.week_number - b.week_number);
    weeks.forEach(w => {
        w.total_tss = Math.round(w.workouts.reduce((s, wk) => s + (wk.duration_min * 1), 0));
    });
    return { weeks };
}

function renderPlanCalendar(plan) {
    const container = document.getElementById('plan-calendar');
    container.innerHTML = plan.weeks.map(week => `
        <div class="plan-week" id="week-${week.week_number}">
            <div class="plan-week-header" onclick="toggleWeek(${week.week_number})">
                <div class="week-title-area" style="display:flex; align-items:center;">
                    <strong class="week-number" style="margin-right:15px; color:var(--apex-primary);">Week ${week.week_number}</strong>
                    <div class="week-focus">${week.focus}</div>
                </div>
                <div class="week-stats-area" style="display:flex; gap:15px; align-items:center;">
                    <div class="week-tss" style="color:var(--apex-warning); font-size: 13px;">${week.total_tss} TSS</div>
                    <div class="week-volume" style="font-size: 13px;">${week.workouts.reduce((s, w) => s + parseFloat(w.distance_km || 0), 0).toFixed(0)} km</div>
                    <span class="week-toggle" style="font-size: 10px;">▼</span>
                </div>
            </div>
            
            <div class="plan-week-body">
                <div class="plan-day-row" style="display:flex; gap: 8px; margin-top: 10px;">
                    ${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => {
        const workout = week.workouts.find(w => w.day === day);
        const isRest = !workout || (workout.type || '').toLowerCase().includes('rest') || workout.distance_km == 0;
        const t = String(workout ? workout.type : '').toLowerCase();
        let typeClass = 'type-rest';
        if (!isRest) {
            if (t.includes('easy')) typeClass = 'type-easy-run';
            else if (t.includes('tempo') || t.includes('threshold')) typeClass = 'type-tempo-run';
            else if (t.includes('interval')) typeClass = 'type-interval';
            else if (t.includes('long')) typeClass = 'type-long-run';
            else if (t.includes('race')) typeClass = 'type-race';
            else typeClass = 'type-strength';
        }

        return `<div class="plan-day-cell ${workout ? 'has-workout' : 'rest-day'} ${typeClass}" style="flex:1;">
                            <div class="plan-day-label" style="font-size: 11px; color: var(--apex-muted); font-weight: bold; margin-bottom: 5px;">${day}</div>
                            ${(!isRest && workout) ? `
                                <div class="plan-workout-type" style="font-size: 13px; font-weight: 500;">${workout.type}</div>
                                <div class="plan-workout-dist" style="font-size: 12px; color: var(--apex-primary); margin: 3px 0;">${workout.distance_km} km</div>
                                <div class="plan-workout-pace" style="font-size: 11px; color: var(--apex-muted);">${workout.pace_min_per_km} /km</div>
                                ${workout.completed ?
                    `<div class="exec-score-badge" style="margin-top:8px; display:inline-block; background: rgba(0,230,118,0.2); color: #00e676; padding: 3px 6px; border-radius:4px; font-size:11px;">Score: ${workout.execution_score}/10</div>` :
                    `<button class="exec-btn" onclick="openExecution(${workout.id}, event)" style="margin-top:8px; padding: 4px 8px; font-size: 11px; background: rgba(0,212,255,0.1); border: 1px solid var(--apex-border); border-radius: 4px; color: var(--apex-text); cursor: pointer;">Log ✏️</button>`
                }
                            ` : `<div class="rest-label" style="font-size: 11px; color: var(--apex-muted); padding: 15px 0; text-align:center;">Rest / Recovery</div>`}
                        </div>`;
    }).join('')}
                </div>
            </div>
        </div>
    `).join('');
}

function toggleWeek(num) {
    const w = document.getElementById('week-' + num);
    const body = w.querySelector('.plan-week-body');
    if (body.style.display === 'none' || body.style.display === '') {
        body.style.display = 'block';
    } else {
        body.style.display = 'none';
    }
}

function ensureExecutionModal() {
    if (!document.getElementById('execution-modal')) {
        const d = document.createElement('div');
        d.id = 'execution-modal';
        d.className = 'modal-overlay';
        d.style.display = 'none';
        d.innerHTML = `
            <div class="modal-content" style="max-width: 600px;">
                <button class="close-modal" onclick="closeExecution()">&times;</button>
                <div id="exec-content"></div>
            </div>
        `;
        document.body.appendChild(d);
    }
}

function openExecution(workoutId, event) {
    if (event) event.stopPropagation();
    ensureExecutionModal();
    const workout = window._planWorkouts.find(w => w.id === workoutId);
    if (!workout) return;

    const isInterval = workout.description.toLowerCase().includes('x') || workout.description.toLowerCase().includes('interval');

    let html = '';
    if (isInterval) {
        const repMatch = workout.description.match(/(\d+)x/i);
        const reps = repMatch ? parseInt(repMatch[1]) : 3;

        let splitTable = '';
        for (let i = 1; i <= Math.min(reps, 15); i++) {
            splitTable += `
            <div class="split-row" style="display:flex; gap: 5px; margin-bottom: 5px;">
              <span style="font-size: 13px; min-width: 50px; line-height:30px;">Rep ${i}</span>
              <input type="text" placeholder="-- km" class="dist-input" id="dist_${i}" style="flex:1;">
              <input type="text" placeholder="--:--" class="pace-input" id="pace_${i}" style="flex:1;">
              <input type="number" placeholder="HR" class="hr-input" id="hr_${i}" style="flex:1;">
            </div>`;
        }

        html = `
        <div class="execution-form" id="exec-${workoutId}">
          <h4>Log Execution: ${workout.workout_type}</h4>
          <p class="exec-desc" style="font-size:12px; color:var(--apex-muted); margin-bottom:15px;">${workout.description}</p>
          <div class="splits-table">
            ${splitTable}
          </div>
          <div class="recovery-row" style="margin-top: 15px;">
            <label style="font-size: 12px; color: var(--apex-text);">Recovery felt:</label>
            <select id="recoveryQuality_${workoutId}" style="width: 100%; margin-top: 5px;">
              <option>Complete — fully ready for next rep</option>
              <option>Partial — legs still heavy</option>
              <option>Incomplete — had to start early</option>
            </select>
          </div>
          <textarea placeholder="Any notes? (weather, fatigue, terrain...)" id="execNotes_${workoutId}" rows="2" style="width:100%; margin-top:15px;"></textarea>
          <button onclick="scoreExecution(${workoutId}, true, ${Math.min(reps, 15)})" class="btn-primary" style="margin-top: 15px; width: 100%;">⚡ Get AI Score</button>
        </div>`;
    } else {
        html = `
        <div class="execution-form" id="exec-${workoutId}">
          <h4>Log Execution: ${workout.workout_type}</h4>
          <p class="exec-desc" style="font-size:12px; color:var(--apex-muted); margin-bottom:15px;">${workout.description}</p>
          <div class="simple-log-row" style="display:flex; gap: 10px; margin: 15px 0;">
            <div><label style="font-size: 11px;">Distance</label>
                 <input type="number" id="actualDist_${workoutId}" placeholder="${(workout.distance_meters / 1000).toFixed(1)}"></div>
            <div><label style="font-size: 11px;">Pace /km</label>
                 <input type="text" id="actualPace_${workoutId}" placeholder="5:45"></div>
            <div><label style="font-size: 11px;">Avg HR</label>
                 <input type="number" id="actualHR_${workoutId}" placeholder="---"></div>
          </div>
          <textarea placeholder="How did it feel?" id="execNotes_${workoutId}" rows="2" style="width: 100%;"></textarea>
          <button onclick="scoreExecution(${workoutId}, false, 0)" class="btn-primary" style="margin-top: 15px; width: 100%;">⚡ Get AI Score</button>
        </div>`;
    }

    document.getElementById('exec-content').innerHTML = html;
    document.getElementById('execution-modal').style.display = 'flex';
}

function closeExecution() {
    document.getElementById('execution-modal').style.display = 'none';
}

function parsePaceToSec(paceStr) {
    if (!paceStr) return 0;
    const parts = paceStr.replace('/km', '').replace(' ', '').split(':');
    if (parts.length === 2) {
        return parseInt(parts[0]) * 60 + parseInt(parts[1]);
    }
    return 0;
}

async function scoreExecution(workoutId, isInterval, numReps) {
    const btn = document.querySelector(`#exec-${workoutId} button`);
    if (btn) { btn.innerText = "Analyzing Score..."; btn.disabled = true; }

    let execData = { splits: [], notes: document.getElementById('execNotes_' + workoutId).value };

    if (isInterval) {
        execData.recovery_quality = document.getElementById('recoveryQuality_' + workoutId).value;
        for (let i = 1; i <= numReps; i++) {
            const pace = document.getElementById('pace_' + i).value;
            if (pace) {
                execData.splits.push({
                    rep: i,
                    pace_sec_per_km: parsePaceToSec(pace),
                    hr: parseInt(document.getElementById('hr_' + i).value || '0')
                });
            }
        }
        if (execData.splits.length > 0) {
            execData.avg_pace_sec_per_km = Math.round(execData.splits.reduce((s, x) => s + x.pace_sec_per_km, 0) / execData.splits.length);
        }
    } else {
        const p = document.getElementById('actualPace_' + workoutId).value;
        execData.avg_pace_sec_per_km = parsePaceToSec(p);
        execData.avg_hr = parseInt(document.getElementById('actualHR_' + workoutId).value || '0');
        execData.actual_distance_km = parseFloat(document.getElementById('actualDist_' + workoutId).value || '0');
    }

    try {
        const res = await fetch('/api/planner/score-execution', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                planned_workout_id: workoutId,
                execution_data: execData
            })
        });
        const scoreJson = await res.json();
        renderScoreCard(scoreJson, execData.splits);
        loadPlan();
    } catch (e) {
        console.error("Scoring failed: ", e);
        if (btn) { btn.innerText = "⚡ Get AI Score"; btn.disabled = false; }
    }
}

function renderScoreCard(scoreData, splits) {
    let gradeCss = scoreData.grade.replace('+', 'plus').replace('-', 'minus').toLowerCase();
    let html = `
    <div class="score-card score-${gradeCss}" style="background: var(--apex-card-alt); padding: 20px; border-radius: 12px; margin-top: 10px;">
      <div class="score-header" style="display:flex; align-items:center; gap: 15px; margin-bottom: 20px;">
        <div class="score-circle" style="width: 60px; height: 60px; border-radius: 50%; background: var(--apex-primary); color: #000; display:flex; align-items:center; justify-content:center; font-size: 20px; font-weight:bold;">
            ${scoreData.score}/10
        </div>
        <div>
          <div class="score-grade" style="font-size: 22px; font-weight:bold;">${scoreData.grade}</div>
          <div class="score-headline" style="font-size: 13px; color: var(--apex-text);">${scoreData.headline}</div>
        </div>
      </div>
      
      <div class="score-body">
        <div class="analysis-section" style="margin-top:15px;">
          <h5 style="margin-bottom:8px; color:var(--apex-muted);">Pacing Analysis</h5>
          <p style="font-size:13px; line-height:1.4;">${scoreData.pacing_analysis || ''}</p>
          <canvas id="splitsChart" height="80" style="margin-top:10px;"></canvas>
        </div>
        
        <div class="strengths-improvements" style="display:flex; gap:15px; margin-top:20px;">
          <div class="strengths" style="flex:1;">
            <h5 style="color:var(--apex-success); margin-bottom:8px;">✅ Strengths</h5>
            <ul style="font-size:12px; padding-left:15px;">${(scoreData.strengths || []).map(s => `<li style="margin-bottom:4px;">${s}</li>`).join('')}</ul>
          </div>
          <div class="improvements" style="flex:1;">
            <h5 style="color:var(--apex-danger); margin-bottom:8px;">📈 To Improve</h5>
            <ul style="font-size:12px; padding-left:15px;">${(scoreData.improvements || []).map(s => `<li style="margin-bottom:4px;">${s}</li>`).join('')}</ul>
          </div>
        </div>
        
        <div class="next-advice" style="margin-top:20px; padding: 15px; background: rgba(0,212,255,0.05); border-left: 3px solid var(--apex-primary); border-radius: 4px;">
          <h5 style="margin-bottom:5px; color:var(--apex-primary);">🎯 Coach Says Next Time</h5>
          <p style="font-size:13px;">${scoreData.next_session_advice || ''}</p>
        </div>
      </div>
    </div>`;

    document.getElementById('exec-content').innerHTML = html;

    if (splits && splits.length > 0) {
        const targetPace = splits.length > 0 ? splits[0].pace_sec_per_km * 0.95 : 240;
        new Chart(document.getElementById('splitsChart'), {
            type: 'bar',
            data: {
                labels: splits.map((_, i) => `Rep ${i + 1}`),
                datasets: [
                    {
                        label: 'Target', type: 'line',
                        data: splits.map(() => targetPace),
                        borderColor: 'rgba(245,200,66,0.7)',
                        borderDash: [5, 5], pointRadius: 0,
                    },
                    {
                        label: 'Actual',
                        data: splits.map(s => s.pace_sec_per_km),
                        backgroundColor: splits.map(s =>
                            s.pace_sec_per_km > targetPace * 1.05 ? '#ff5252' :
                                s.pace_sec_per_km < targetPace * 0.95 ? '#69f0ae' : '#00d4ff'
                        ),
                    }
                ]
            },
            options: { plugins: { legend: { display: false } }, scales: { y: { reverse: true } } }
        });
    }
}

// ── ICS Export ─────────────────────────────────────────────────────────
function exportICS() {
    const workouts = window._planWorkouts;
    if (!workouts || !workouts.length) return;

    const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//APEX Coach//EN'];
    workouts.forEach(w => {
        lines.push('BEGIN:VEVENT');
        lines.push(`DTSTART: ${(w.date || '').replace(/-/g, '')}T060000Z`);
        lines.push(`DTEND: ${(w.date || '').replace(/-/g, '')} T070000Z`);
        lines.push(`SUMMARY:${w.workout_type || 'Workout'} — ${((w.planned_distance_meters || 0) / 1000).toFixed(1)} km`);
        lines.push(`DESCRIPTION:${(w.description || '').replace(/\n/g, '\\n')} `);
        lines.push('END:VEVENT');
    });
    lines.push('END:VCALENDAR');

    const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'apex_training_plan.ics'; a.click();
    URL.revokeObjectURL(url);
}

// ── Plan Modal ─────────────────────────────────────────────────────────
function openPlanModal() { document.getElementById('plan-modal').style.display = 'flex'; }
function closePlanModal() { document.getElementById('plan-modal').style.display = 'none'; }

function showPlanSkeleton() {
    const container = document.getElementById('plan-calendar');
    container.innerHTML = `
        < div class="plan-generating-banner" >
            <div class="pulse-dot"></div>
            <span>APEX is building your periodized plan...</span>
        </div >
        ${Array(4).fill(0).map((_, i) => `
            <div class="week-skeleton">
                <div class="skeleton-header"></div>
                ${Array(5).fill(0).map(() => `
                    <div class="skeleton-row"></div>
                `).join('')}
            </div>
        `).join('')
        }
    `;
    container.style.display = 'block';
}

document.getElementById('plan-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('generate-plan-btn');
    btn.textContent = 'Generating...'; btn.disabled = true;

    const goal = document.getElementById('p-goal').value;
    const target = document.getElementById('p-date').value;
    const hours = parseFloat(document.getElementById('p-hours').value);
    const today = new Date().toISOString().split('T')[0];

    closePlanModal();
    showPlanSkeleton();

    let fullJson = '';
    try {
        const response = await fetch('/api/planner/generate-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal, target_date: target, weekly_hours: hours, start_date: today, user_id: 1 })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const lines = decoder.decode(value).split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const strData = line.slice(6).trim();
                    if (!strData || strData === '[DONE]') continue;
                    try {
                        const data = JSON.parse(strData);
                        if (data.token) {
                            fullJson += data.token;
                        }
                        if (data.status === 'complete') {
                            loadPlan();
                        }
                    } catch (e) { }
                }
            }
        }
    } catch (err) {
        console.error('Plan generation stream error:', err);
    } finally {
        btn.textContent = 'Generate Plan'; btn.disabled = false;
        loadPlan(); // Ensure final UI refresh regardless of crash
    }
});

// ── Workout Form ───────────────────────────────────────────────────────
document.getElementById('w-date').valueAsDate = new Date();

document.getElementById('workout-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('submit-workout-btn');
    btn.textContent = 'Saving...'; btn.disabled = true;
    const payload = {
        date: document.getElementById('w-date').value,
        sport: 'run',
        distance_meters: parseFloat(document.getElementById('w-dist').value) * 1000,
        duration_seconds: parseInt(document.getElementById('w-dur').value) * 60,
        avg_hr: parseInt(document.getElementById('w-hr').value),
        rpe: parseInt(document.getElementById('w-rpe').value),
    };
    try {
        const res = await fetch('/api/workouts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(r => r.json());
        if (res.status === 'success') loadDashboard();
    } catch (err) {
        console.error('Workout save error:', err);
    } finally {
        btn.textContent = 'Save Workout'; btn.disabled = false;
    }
});

// ── Chat Logic ─────────────────────────────────────────────────────────
const chatContainer = document.getElementById('chat-container');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const welcomeScreen = document.getElementById('welcome-screen');
const newChatBtn = document.getElementById('new-chat-btn');

function setPrompt(text) { userInput.value = text; userInput.focus(); }

// Auto-resize textarea
userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 140) + 'px';
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

sendBtn.addEventListener('click', sendMessage);

newChatBtn.addEventListener('click', () => {
    chatHistory = [];
    chatContainer.innerHTML = '';
    chatContainer.appendChild(welcomeScreen);
    welcomeScreen.style.display = 'flex';
    switchTab('chat');
});

function addMessage(role, content) {
    if (welcomeScreen) welcomeScreen.style.display = 'none';
    const div = document.createElement('div');
    div.className = `message ${role} `;
    const iconName = role === 'user' ? 'user' : 'zap';
    div.innerHTML = `
        < div class="avatar" > <i data-lucide="${iconName}"></i></div >
            <div class="msg-content">${role === 'assistant' ? marked.parse(content) : `<p>${content}</p>`}</div>
    `;
    chatContainer.appendChild(div);
    lucide.createIcons({ attrs: { class: 'icon', width: 16, height: 16 } });
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return div;
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    userInput.value = '';
    userInput.style.height = 'auto';
    addMessage('user', text);
    chatHistory.push({ role: 'user', content: text });

    sendBtn.disabled = true;
    const assistantDiv = addMessage('assistant', '<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot" style="animation-delay:0.2s"></span><span class="typing-dot" style="animation-delay:0.4s"></span></div>');
    const contentEl = assistantDiv.querySelector('.msg-content');

    try {
        const resp = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: chatHistory })
        });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);
                if (payload === '[DONE]') break;
                try {
                    const data = JSON.parse(payload);
                    if (data.type === 'metadata') {
                        renderSources(data.sources || []);
                    } else if (data.type === 'content') {
                        fullText += data.text;
                        contentEl.innerHTML = marked.parse(fullText);
                    }
                } catch { }
            }
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        chatHistory.push({ role: 'assistant', content: fullText });
    } catch (err) {
        contentEl.innerHTML = `< p style = "color:var(--apex-danger);" > Error: ${err.message}</p > `;
    } finally {
        sendBtn.disabled = false;
        lucide.createIcons();
    }
}

function renderSources(sources) {
    const section = document.getElementById('sources-section');
    const list = document.getElementById('sources-list');
    const count = document.getElementById('sources-count');
    if (!sources.length) return;
    section.style.display = '';
    count.textContent = sources.length;
    list.innerHTML = sources.map(s => `< div class="source-item" >
        <div class="source-header"><span>${s.type}</span><span>${s.score}</span></div>
        <div class="source-preview">${s.preview}</div>
    </div > `).join('');
}

// ── Init ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    // Check for Strava redirect
    if (window.location.search.includes('connected=strava')) {
        window.history.replaceState({}, '', '/');
        const si = document.getElementById('stravaStatus');
        if (si) si.innerHTML = '<span style="color:var(--apex-success);">✅ Connected — syncing...</span>';
    }
});
