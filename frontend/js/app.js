// Global state variables
let regionData = null;
let currentTransactions = [];
let tableSortConfig = { key: 'dealDay', asc: false };

// Chart.js instances (need to keep track to destroy/recreate on new search)
let trendChartInstance = null;
let sizeChartInstance = null;
let priceDistChartInstance = null;

// Helper function to format price in Korean style (e.g., 143500 만원 -> 14억 3,500만원)
function formatPrice(amountManwon) {
    if (!amountManwon || amountManwon === 0) return "-";
    
    const amount = Number(amountManwon);
    const eok = Math.floor(amount / 10000);
    const rest = amount % 10000;
    
    let result = "";
    if (eok > 0) {
        result += `${eok}억 `;
    }
    if (rest > 0) {
        result += `${rest.toLocaleString()}만원`;
    } else {
        result += "원";
    }
    return result.trim();
}

// Populate year selector (current year down to 2015)
function populateYearSelect() {
    const yearSelect = document.getElementById("year-select");
    const currentYear = new Date().getFullYear();
    yearSelect.innerHTML = "";
    
    for (let y = currentYear; y >= 2015; y--) {
        const option = document.createElement("option");
        option.value = y;
        option.textContent = `${y}년`;
        if (y === currentYear) {
            option.selected = true;
        }
        yearSelect.appendChild(option);
    }
}

// Populate month selector (1 to 12)
function populateMonthSelect() {
    const monthSelect = document.getElementById("month-select");
    const currentMonth = new Date().getMonth() + 1; // 1-indexed
    monthSelect.innerHTML = "";
    
    for (let m = 1; m <= 12; m++) {
        const option = document.createElement("option");
        option.value = m;
        option.textContent = `${m}월`;
        // Default to previous month (to ensure data is available)
        const targetDefault = currentMonth === 1 ? 12 : currentMonth - 1;
        if (m === targetDefault) {
            option.selected = true;
        }
        monthSelect.appendChild(option);
    }
}

// Load regions JSON from API and populate Sido select
async function loadRegions() {
    try {
        const res = await fetch("/api/regions");
        if (!res.ok) throw new Error("Failed to load regions");
        regionData = await res.json();
        
        const sidoSelect = document.getElementById("sido-select");
        sidoSelect.innerHTML = '<option value="" disabled selected>시/도 선택</option>';
        
        Object.keys(regionData).sort().forEach(sido => {
            const option = document.createElement("option");
            option.value = sido;
            option.textContent = sido;
            sidoSelect.appendChild(option);
        });
        
        document.getElementById("connection-status").textContent = "API 연결 완료";
    } catch (err) {
        console.error(err);
        document.getElementById("connection-status").textContent = "연결 오류";
        document.getElementById("connection-status").parentElement.querySelector('.pulse-dot').style.backgroundColor = 'var(--accent-red)';
    }
}

// Update Sigungu dropdown when Sido changes
function handleSidoChange() {
    const sidoSelect = document.getElementById("sido-select");
    const sigunguSelect = document.getElementById("sigungu-select");
    
    const selectedSido = sidoSelect.value;
    sigunguSelect.innerHTML = '<option value="" disabled selected>시/군/구 선택</option>';
    sigunguSelect.disabled = true;
    
    if (selectedSido && regionData[selectedSido]) {
        const sigungus = regionData[selectedSido];
        
        // Sort Sigungu names
        Object.keys(sigungus).sort().forEach(sigungu => {
            const option = document.createElement("option");
            option.value = sigungus[sigungu]; // The 5-digit code
            option.textContent = sigungu;
            sigunguSelect.appendChild(option);
        });
        
        sigunguSelect.disabled = false;
    }
}

// Run statistical analysis query
async function handleFormSubmit(e) {
    e.preventDefault();
    
    const sigunguSelect = document.getElementById("sigungu-select");
    const lawdCd = sigunguSelect.value;
    const year = document.getElementById("year-select").value;
    const month = document.getElementById("month-select").value;
    const monthsCount = document.getElementById("trend-months").value;
    
    const sidoText = document.getElementById("sido-select").value;
    const sigunguText = sigunguSelect.options[sigunguSelect.selectedIndex].text;
    
    if (!lawdCd) return;
    
    // UI state: Loading
    const searchBtn = document.getElementById("search-btn");
    const btnText = document.getElementById("btn-text");
    const btnSpinner = document.getElementById("btn-spinner");
    
    searchBtn.disabled = true;
    btnText.textContent = "분석 중...";
    btnSpinner.classList.remove("hidden");
    
    try {
        const url = `/api/search?lawd_cd=${lawdCd}&year=${year}&month=${month}&months_count=${monthsCount}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Search query failed");
        
        const data = await res.json();
        
        // Populate UI with retrieved data
        updateDashboard(data, sidoText, sigunguText, year, month);
        
        // UI state: Completed
        document.getElementById("empty-dashboard-state").classList.add("hidden");
        document.getElementById("dashboard-body").classList.remove("hidden");
    } catch (err) {
        console.error(err);
        alert("실거래 데이터를 가져오는 데 실패했습니다. API 키 및 네트워크 상태를 확인해 주세요.");
    } finally {
        searchBtn.disabled = false;
        btnText.textContent = "통계 분석 실행";
        btnSpinner.classList.add("hidden");
    }
}

// Update all components in the dashboard
function updateDashboard(data, sido, sigungu, year, month) {
    const stats = data.stats;
    currentTransactions = data.transactions || [];
    
    // Update Header Text
    document.getElementById("search-title-text").textContent = `${sido} ${sigungu} 실거래 분석 (${year}년 ${month}월)`;
    document.getElementById("search-subtitle-text").textContent = `최근 ${data.historical_trend.length}개월간의 거래 시세 동향 및 상세 분석 리스트를 제공합니다.`;
    
    // Update KPI Cards
    document.getElementById("kpi-avg-price").textContent = formatPrice(stats.avg_price);
    document.getElementById("kpi-total-deals").textContent = `${stats.total_deals.toLocaleString()}건`;
    document.getElementById("kpi-pyeong-price").textContent = stats.avg_pyeong_price > 0 ? `${Math.round(stats.avg_pyeong_price).toLocaleString()}만원` : "-";
    
    // Update KPI Subtexts
    document.getElementById("kpi-avg-price-sub").textContent = `${sigungu} 평균 실거래가`;
    document.getElementById("kpi-total-deals-sub").textContent = `취소 거래 제외 실거래 건수`;
    
    // Update Highest Deal Apartment Card
    const maxDeal = stats.max_deal;
    if (maxDeal) {
        document.getElementById("kpi-max-price").textContent = formatPrice(maxDeal.dealAmount);
        document.getElementById("kpi-max-desc").textContent = `${maxDeal.aptNm} ${maxDeal.floor}층 (${maxDeal.excluUseAr}㎡ / ${maxDeal.pyeong}평)`;
    } else {
        document.getElementById("kpi-max-price").textContent = "-";
        document.getElementById("kpi-max-desc").textContent = "거래 내역 없음";
    }
    
    // Update Detailed Summary Panel
    const minDeal = stats.min_deal;
    if (minDeal) {
        document.getElementById("stat-min-deal").textContent = `${formatPrice(minDeal.dealAmount)} (${minDeal.aptNm} ${minDeal.floor}층)`;
    } else {
        document.getElementById("stat-min-deal").textContent = "-";
    }
    
    if (currentTransactions.length > 0) {
        const avgArea = currentTransactions.reduce((acc, curr) => acc + curr.excluUseAr, 0) / currentTransactions.length;
        const avgPyeong = currentTransactions.reduce((acc, curr) => acc + curr.pyeong, 0) / currentTransactions.length;
        const avgFloor = currentTransactions.reduce((acc, curr) => acc + curr.floor, 0) / currentTransactions.length;
        const validBuildYears = currentTransactions.filter(d => d.buildYear > 0);
        const avgBuild = validBuildYears.length > 0 ? validBuildYears.reduce((acc, curr) => acc + curr.buildYear, 0) / validBuildYears.length : 0;
        
        document.getElementById("stat-avg-area").textContent = `${avgArea.toFixed(1)}㎡ (약 ${avgPyeong.toFixed(1)}평)`;
        document.getElementById("stat-avg-floor").textContent = `${avgFloor.toFixed(1)}층`;
        
        const currentYear = new Date().getFullYear();
        document.getElementById("stat-avg-build-year").textContent = avgBuild > 0 ? `${Math.round(avgBuild)}년 (평균 노후도 ${Math.round(currentYear - avgBuild)}년)` : "-";
        
        // Dynamic Insights text
        document.getElementById("insight-dynamic-text").innerHTML = `
            ${year}년 ${month}월 기준 <strong>${sigungu}</strong>의 평균 아파트 매매가는 <strong>${formatPrice(stats.avg_price)}</strong>이며, 평당 단가는 <strong>${Math.round(stats.avg_pyeong_price).toLocaleString()}만원</strong>입니다. 
            총 <strong>${stats.total_deals}건</strong>의 실거래가 이루어졌으며, 최고가 단지는 <strong>${maxDeal ? maxDeal.aptNm : '-'}</strong>입니다.
        `;
    } else {
        document.getElementById("stat-avg-area").textContent = "-";
        document.getElementById("stat-avg-floor").textContent = "-";
        document.getElementById("stat-avg-build-year").textContent = "-";
        document.getElementById("insight-dynamic-text").textContent = "해당 월에 등록된 실거래 데이터가 없습니다. 다른 연월을 선택해 분석해 보세요.";
    }
    
    // Render Charts
    renderTrendChart(data.historical_trend);
    renderSizeChart(stats.size_distribution);
    renderPriceDistChart(stats.price_distribution);
    
    // Reset table filter inputs & render table
    document.getElementById("table-search-name").value = "";
    document.getElementById("filter-min-size").value = "";
    document.getElementById("filter-max-size").value = "";
    
    renderTable();
}

// Chart 1: Historical Trend (Line & Bar Dual-Axis)
function renderTrendChart(trendData) {
    const ctx = document.getElementById("trendChart").getContext("2d");
    
    if (trendChartInstance) {
        trendChartInstance.destroy();
    }
    
    const labels = trendData.map(d => d.month);
    const avgPrices = trendData.map(d => d.avg_price);
    const totalDeals = trendData.map(d => d.total_deals);
    
    trendChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '거래량 (건)',
                    data: totalDeals,
                    backgroundColor: 'rgba(99, 102, 241, 0.2)',
                    borderColor: 'rgba(99, 102, 241, 0.8)',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    yAxisID: 'yVolume',
                    type: 'bar'
                },
                {
                    label: '평균 가격 (만원)',
                    data: avgPrices,
                    borderColor: '#38bdf8',
                    backgroundColor: 'transparent',
                    borderWidth: 3,
                    pointBackgroundColor: '#38bdf8',
                    pointBorderColor: '#0b0f19',
                    pointBorderWidth: 2,
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    tension: 0.3,
                    yAxisID: 'yPrice',
                    type: 'line'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
                },
                tooltip: {
                    padding: 12,
                    titleFont: { size: 13, weight: 'bold' },
                    bodyFont: { size: 12 },
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) label += ': ';
                            if (context.datasetIndex === 1) { // Price
                                label += formatPrice(context.raw);
                            } else { // Volume
                                label += context.raw + '건';
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#94a3b8', font: { family: 'Inter' } }
                },
                yPrice: {
                    type: 'linear',
                    position: 'right',
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        color: '#38bdf8',
                        font: { family: 'Inter' },
                        callback: function(value) {
                            return (value / 10000).toFixed(1) + '억';
                        }
                    },
                    title: {
                        display: true,
                        text: '평균 거래가',
                        color: '#38bdf8',
                        font: { size: 11, weight: 'bold' }
                    }
                },
                yVolume: {
                    type: 'linear',
                    position: 'left',
                    grid: { display: false },
                    ticks: { color: '#94a3b8', font: { family: 'Inter' } },
                    title: {
                        display: true,
                        text: '거래 건수',
                        color: '#94a3b8',
                        font: { size: 11, weight: 'bold' }
                    }
                }
            }
        }
    });
}

// Chart 2: Average Price by size class
function renderSizeChart(sizeData) {
    const ctx = document.getElementById("sizeChart").getContext("2d");
    
    if (sizeChartInstance) {
        sizeChartInstance.destroy();
    }
    
    const labels = ["소형 (<60㎡)", "중소형 (60~85㎡)", "중대형 (85~135㎡)", "대형 (≥135㎡)"];
    const values = [
        sizeData.small ? sizeData.small.avg_price : 0,
        sizeData.medium_small ? sizeData.medium_small.avg_price : 0,
        sizeData.medium_large ? sizeData.medium_large.avg_price : 0,
        sizeData.large ? sizeData.large.avg_price : 0
    ];
    
    sizeChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '평균 가격 (만원)',
                data: values,
                backgroundColor: [
                    'rgba(56, 189, 248, 0.25)', // Blue
                    'rgba(16, 185, 129, 0.25)', // Green
                    'rgba(168, 85, 247, 0.25)', // Purple
                    'rgba(251, 191, 36, 0.25)'  // Gold
                ],
                borderColor: [
                    '#38bdf8',
                    '#10b981',
                    '#a855f7',
                    '#fbbf24'
                ],
                borderWidth: 1.5,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '평균가: ' + formatPrice(context.raw);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8', font: { family: 'Noto Sans KR', size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        color: '#94a3b8',
                        font: { family: 'Inter' },
                        callback: function(value) {
                            return (value / 10000).toFixed(0) + '억';
                        }
                    }
                }
            }
        }
    });
}

// Chart 3: Price Distribution (Doughnut)
function renderPriceDistChart(priceData) {
    const ctx = document.getElementById("priceDistChart").getContext("2d");
    
    if (priceDistChartInstance) {
        priceDistChartInstance.destroy();
    }
    
    const labels = ["3억 미만", "3억~6억", "6억~9억", "9억~12억", "12억~15억", "15억 이상"];
    const values = [
        priceData.under_3 || 0,
        priceData.3_to_6 || 0,
        priceData.6_to_9 || 0,
        priceData.9_to_12 || 0,
        priceData.12_to_15 || 0,
        priceData.over_15 || 0
    ];
    
    // Check if we have any data to render, otherwise display empty chart
    const totalCount = values.reduce((a, b) => a + b, 0);
    
    priceDistChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: totalCount > 0 ? values : [1], // placeholder if no data
                backgroundColor: totalCount > 0 ? [
                    'rgba(148, 163, 184, 0.25)', // Slate
                    'rgba(16, 185, 129, 0.25)',  // Green
                    'rgba(56, 189, 248, 0.25)',  // Blue
                    'rgba(99, 102, 241, 0.25)',  // Indigo
                    'rgba(168, 85, 247, 0.25)',  // Purple
                    'rgba(239, 68, 68, 0.25)'    // Red
                ] : ['rgba(255, 255, 255, 0.05)'],
                borderColor: totalCount > 0 ? [
                    '#94a3b8',
                    '#10b981',
                    '#38bdf8',
                    '#6366f1',
                    '#a855f7',
                    '#ef4444'
                ] : ['rgba(255, 255, 255, 0.1)'],
                borderWidth: 1.5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#94a3b8', font: { family: 'Noto Sans KR', size: 11 } }
                },
                tooltip: {
                    enabled: totalCount > 0,
                    callbacks: {
                        label: function(context) {
                            const value = context.raw;
                            const percentage = ((value / totalCount) * 100).toFixed(1);
                            return ` ${context.label}: ${value}건 (${percentage}%)`;
                        }
                    }
                }
            },
            cutout: '70%'
        }
    });
}

// Render Transaction List Table
function renderTable() {
    const tableBody = document.getElementById("transaction-table-body");
    const emptyState = document.getElementById("table-empty-state");
    const subtitleCount = document.getElementById("table-subtitle-count");
    
    tableBody.innerHTML = "";
    
    // Extract filter values
    const searchName = document.getElementById("table-search-name").value.toLowerCase().trim();
    const minSize = parseFloat(document.getElementById("filter-min-size").value) || 0;
    const maxSize = parseFloat(document.getElementById("filter-max-size").value) || Infinity;
    
    // Apply filters
    let filtered = currentTransactions.filter(t => {
        const matchesName = t.aptNm.toLowerCase().includes(searchName) || t.umdNm.toLowerCase().includes(searchName);
        const matchesSize = t.excluUseAr >= minSize && t.excluUseAr <= maxSize;
        return matchesName && matchesSize;
    });
    
    // Apply sorting
    const sortKey = tableSortConfig.key;
    const isAsc = tableSortConfig.asc;
    
    filtered.sort((a, b) => {
        let valA = a[sortKey];
        let valB = b[sortKey];
        
        // Handle string comparison for apartment name / dong
        if (typeof valA === 'string') {
            return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        
        // Numeric sorting
        return isAsc ? valA - valB : valB - valA;
    });
    
    // Update subtitle count
    subtitleCount.textContent = `총 ${filtered.length.toLocaleString()}건의 거래 (전체 ${currentTransactions.length.toLocaleString()}건)`;
    
    if (filtered.length === 0) {
        emptyState.classList.remove("hidden");
        document.getElementById("transaction-table").style.display = "none";
        return;
    }
    
    emptyState.classList.add("hidden");
    document.getElementById("transaction-table").style.display = "table";
    
    filtered.forEach(t => {
        const tr = document.createElement("tr");
        
        // 계약일 formatting: e.g. 17일
        const dealDateStr = `${t.dealDay}일`;
        
        // 거래금액 formatting: e.g. 14억 3,500
        const priceStr = formatPrice(t.dealAmount).replace("만원", "");
        
        // 전용면적 formatting: 114.93㎡ (34.8평)
        const areaStr = `${t.excluUseAr.toFixed(1)}㎡ / ${t.pyeong}평`;
        
        // 평당단가 formatting
        const pyeongPriceStr = `${Math.round(t.pyeongPrice).toLocaleString()}만원`;
        
        tr.innerHTML = `
            <td>${dealDateStr}</td>
            <td>${t.umdNm}</td>
            <td><strong>${t.aptNm}</strong></td>
            <td class="text-right" style="color: var(--accent-blue); font-weight:600;">${priceStr}</td>
            <td class="text-right">${areaStr}</td>
            <td class="text-right">${t.floor}층</td>
            <td class="text-right">${t.buildYear > 0 ? t.buildYear + '년' : '-'}</td>
            <td class="text-right" style="color: var(--text-secondary);">${pyeongPriceStr}</td>
        `;
        
        tableBody.appendChild(tr);
    });
}

// Bind table headers for sorting
function initTableSorting() {
    const headers = document.querySelectorAll("#transaction-table th.sortable");
    headers.forEach(header => {
        header.addEventListener("click", () => {
            const key = header.getAttribute("data-sort");
            if (tableSortConfig.key === key) {
                tableSortConfig.asc = !tableSortConfig.asc;
            } else {
                tableSortConfig.key = key;
                tableSortConfig.asc = true; // default to ascending on new column
            }
            
            // Update sort icons
            headers.forEach(h => {
                const icon = h.querySelector("i");
                if (h === header) {
                    icon.className = tableSortConfig.asc ? "fa-solid fa-sort-up" : "fa-solid fa-sort-down";
                    icon.style.opacity = 1;
                } else {
                    icon.className = "fa-solid fa-sort";
                    icon.style.opacity = 0.5;
                }
            });
            
            renderTable();
        });
    });
}

// Setup Event Listeners
function initEventListeners() {
    // Dropdowns
    document.getElementById("sido-select").addEventListener("change", handleSidoChange);
    
    // Range slider value update
    const slider = document.getElementById("trend-months");
    const sliderVal = document.getElementById("trend-val");
    slider.addEventListener("input", (e) => {
        sliderVal.textContent = `${e.target.value}개월`;
    });
    
    // Form Submit
    document.getElementById("search-form").addEventListener("submit", handleFormSubmit);
    
    // Table Live Filters
    document.getElementById("table-search-name").addEventListener("keyup", renderTable);
    document.getElementById("filter-min-size").addEventListener("input", renderTable);
    document.getElementById("filter-max-size").addEventListener("input", renderTable);
    
    // Reset Filters
    document.getElementById("reset-filters-btn").addEventListener("click", () => {
        document.getElementById("table-search-name").value = "";
        document.getElementById("filter-min-size").value = "";
        document.getElementById("filter-max-size").value = "";
        renderTable();
    });
}

// Page Initialization
window.addEventListener("DOMContentLoaded", () => {
    populateYearSelect();
    populateMonthSelect();
    initEventListeners();
    initTableSorting();
    loadRegions();
});
