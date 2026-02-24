document.addEventListener('DOMContentLoaded', () => {
    console.log('Automated Code Review Assistant initialized.');

    // Dynamic configuration variables (will be substituted by CodeBuild or manually configured)
    const API_BASE_URL = window.API_BASE_URL || 'YOUR_API_GATEWAY_URL_HERE';
    const REPORTS_BUCKET_URL_BASE = window.REPORTS_BUCKET_URL_BASE || 'YOUR_REPORTS_BUCKET_URL_HERE';

    const analyzeForm = document.getElementById('analyze-form');
    if (analyzeForm) {
        analyzeForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const repoUrl = document.getElementById('repo-url').value;
            window.location.href = `dashboard.html?repo=${encodeURIComponent(repoUrl)}`;
        });
    }

    if (document.getElementById('tech-debt-chart')) {
        const urlParams = new URLSearchParams(window.location.search);
        const repo = urlParams.get('repo');

        if (repo) {
            document.querySelector('.loading-text').textContent = "Triggering Serverless Analysis Pipeline for " + repo + "...";
            startAnalysisPipeline(repo, API_BASE_URL);
        } else {
            document.querySelector('.loading-text').textContent = "Loading latest reports from S3...";
            loadLatestReports(REPORTS_BUCKET_URL_BASE);
        }
    }
});

async function startAnalysisPipeline(repoUrl, apiUrl) {
    try {
        const analyzeResponse = await fetch(`${apiUrl}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_url: repoUrl })
        });

        const data = await analyzeResponse.json();

        if (data.statusCode >= 400 || data.status === "error") {
            const errorMsg = data.message || data.body || "Backend Error";
            alert("API Error: " + errorMsg);
            document.querySelector('.loading-text').textContent = errorMsg;
            return;
        }

        const bucketUrl = `https://${data.reports_bucket}.s3.amazonaws.com`;
        document.querySelector('.loading-text').textContent = "Analysis Jobs Triggered. Polling S3 for results...";
        pollReports(bucketUrl);

    } catch (error) {
        console.error("Pipeline failure:", error);
        document.querySelector('.loading-text').textContent = "Network Error integrating with API Gateway. Check CORS or API_BASE_URL.";
    }
}

async function loadLatestReports(bucketUrl) {
    await fetchReportsAndRender(bucketUrl);
}

async function pollReports(bucketUrl) {
    let polling = true;
    let attempts = 0;
    const maxAttempts = 30; // 30 * 5s = 150s

    while (polling && attempts < maxAttempts) {
        attempts++;
        try {
            const isDone = await fetchReportsAndRender(bucketUrl, true);
            if (isDone) {
                polling = false;
                break;
            }
        } catch (e) {
            // Wait
        }
        await new Promise(r => setTimeout(r, 5000));
    }

    if (polling) {
        document.querySelector('.loading-text').textContent = "Polling timed out. Results may take longer.";
    }
}

async function fetchReportsAndRender(bucketUrl, requireComplete = false) {
    let techDebtData = null;
    let reviewData = null;

    const ts = new Date().getTime();

    try {
        const crRes = await fetch(`${bucketUrl}/reports/code_review_latest.json?t=${ts}`);
        if (crRes.ok) reviewData = await crRes.json();

        const tdRes = await fetch(`${bucketUrl}/reports/technical_debt_latest.json?t=${ts}`);
        if (tdRes.ok) techDebtData = await tdRes.json();
    } catch (e) {
        return false;
    }

    if (requireComplete) {
        if (!reviewData || reviewData.status === "processing" || !techDebtData || techDebtData.status === "processing") {
            return false;
        }
    }

    if (reviewData && techDebtData && reviewData.status !== "processing" && techDebtData.status !== "processing") {
        const mappedData = {
            score: reviewData.score || 0,
            trend: '+0%',
            reviews: reviewData.reviews || [],
            techDebt: {
                commits: techDebtData.modules ? techDebtData.modules.map(m => m.name.split('/').pop()) : [],
                debtScore: techDebtData.modules ? techDebtData.modules.map(m => m.urgency) : []
            }
        };
        loadDashboardData(mappedData);
        const loader = document.querySelector('.loading-container') || document.querySelector('.loading-text')?.parentElement;
        if (loader) loader.style.display = 'none';
        return true;
    }
    return false;
}

function loadDashboardData(data) {
    const scoreVal = document.querySelector('.score-value');
    if (scoreVal) {
        let current = 0;
        const target = data.score;
        const interval = setInterval(() => {
            current += 2;
            if (current >= target) {
                current = target;
                clearInterval(interval);
            }
            scoreVal.textContent = `${current}/100`;
        }, 20);
    }

    const reviewContainer = document.querySelector('.review-content');
    if (reviewContainer) {
        reviewContainer.innerHTML = '';

        data.reviews.forEach((review, index) => {
            const item = document.createElement('div');
            item.className = 'review-item';
            if (!review.isDanger) {
                item.style.borderLeftColor = 'var(--success)';
            }
            item.style.animation = `fadeUp 0.5s ease-out ${0.3 + (index * 0.1)}s forwards`;
            item.style.opacity = '0';

            let html = `<h4>${review.type || 'Review Item'}</h4><p>${review.message || ''}</p>`;

            if (review.snippet) {
                html += `
                    <div style="margin-top: 1rem; margin-bottom: 0.5rem; font-weight: 600; font-size: 0.9rem;">Existing Code:</div>
                    <div class="code-snippet">
                        <pre><code>${review.snippet}</code></pre>
                    </div>
                `;
            }
            if (review.improved_code) {
                html += `
                    <div style="margin-top: 1rem; margin-bottom: 0.5rem; color: var(--success); font-weight: 600; font-size: 0.9rem;">Improved Code:</div>
                    <div class="code-snippet" style="border-left: 2px solid var(--success);">
                        <pre><code>${review.improved_code}</code></pre>
                    </div>
                `;
            }

            item.innerHTML = html;
            reviewContainer.appendChild(item);
        });
    }

    const chartContainer = document.getElementById('tech-debt-chart');
    if (chartContainer) {
        chartContainer.innerHTML = '<canvas id="debtCanvas"></canvas>';
        const ctx = document.getElementById('debtCanvas').getContext('2d');

        if (typeof Chart !== 'undefined') {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.techDebt.commits,
                    datasets: [{
                        label: 'Technical Debt Score',
                        data: data.techDebt.debtScore,
                        borderColor: '#4f46e5',
                        backgroundColor: 'rgba(79, 70, 229, 0.1)',
                        borderWidth: 3,
                        pointBackgroundColor: '#ffffff',
                        pointBorderColor: '#4f46e5',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { backgroundColor: '#0f172a', titleFont: { family: 'Inter', size: 13 }, bodyFont: { family: 'Inter', size: 14 }, padding: 12, cornerRadius: 8, displayColors: false }
                    },
                    scales: {
                        x: { grid: { display: false, drawBorder: false }, ticks: { font: { family: 'Inter' }, color: '#64748b' } },
                        y: { grid: { color: '#e2e8f0', drawBorder: false, borderDash: [5, 5] }, ticks: { font: { family: 'Inter' }, color: '#64748b', stepSize: 20 } }
                    },
                    animation: { duration: 2000, easing: 'easeOutQuart' }
                }
            });
        }
    }
}
