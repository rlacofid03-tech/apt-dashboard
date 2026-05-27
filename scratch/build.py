import json
import os
import configparser

def load_env_keys(workspace_dir):
    config = configparser.ConfigParser()
    apt_key = ""
    kakao_js_key = ""
    env_path = os.path.join(workspace_dir, ".env")
    if os.path.exists(env_path):
        try:
            config.read(env_path, encoding='utf-8')
            if 'APT' in config and 'key' in config['APT']:
                apt_key = config['APT']['key'].strip()
            if 'kakao' in config and 'JavaScript_KEY' in config['kakao']:
                kakao_js_key = config['kakao']['JavaScript_KEY'].strip()
        except Exception as e:
            print(f"Error reading .env in build script: {e}")
    return apt_key, kakao_js_key

def build_single_html():
    workspace_dir = r"c:\Users\knuser\Documents\vibecode\apt"
    
    # 1. Load keys from .env
    apt_key, kakao_js_key = load_env_keys(workspace_dir)
    print(f"Loaded Keys - APT Key: {apt_key[:8]}..., Kakao JS Key: {kakao_js_key[:8]}...")
    
    # 2. Load regional mapping data
    json_path = os.path.join(workspace_dir, "sigungu_codes.json")
    with open(json_path, "r", encoding="utf-8") as f:
        region_data = json.load(f)
    region_json_str = json.dumps(region_data, ensure_ascii=False)
    
    # 3. Load custom CSS stylesheet
    css_path = os.path.join(workspace_dir, "frontend", "css", "style.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    # 4. Read HTML template
    html_path = os.path.join(workspace_dir, "frontend", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 5. Construct embedded JavaScript code (using placeholder values to avoid f-string syntax errors)
    js_content = """
    // Embedded region code database
    const REGION_DATA = __REGION_DATA_PLACEHOLDER__;
    
    // Embedded API Keys from .env
    const EMBEDDED_API_KEY = "__APT_KEY_PLACEHOLDER__";
    const EMBEDDED_KAKAO_KEY = "__KAKAO_KEY_PLACEHOLDER__";
    
    // Global state variables
    let apiKey = EMBEDDED_API_KEY || "";
    let currentTransactions = [];
    let tableSortConfig = { key: 'dealDay', asc: false };

    // Chart.js instances
    let trendChartInstance = null;
    let sizeChartInstance = null;
    let priceDistChartInstance = null;

    // Kakao Map instances
    let map = null;
    let geocoder = null;
    let activeMarkers = [];
    let activeCustomOverlay = null;

    // Format price to Korean style (e.g., 143500 만원 -> 14억 3,500만원)
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
            if (y === 2024) { // Default to 2024 since data is guaranteed
                option.selected = true;
            }
            yearSelect.appendChild(option);
        }
    }

    // Populate month selector (1 to 12)
    function populateMonthSelect() {
        const monthSelect = document.getElementById("month-select");
        monthSelect.innerHTML = "";
        
        for (let m = 1; m <= 12; m++) {
            const option = document.createElement("option");
            option.value = m;
            option.textContent = `${m}월`;
            if (m === 7) { // Default to July
                option.selected = true;
            }
            monthSelect.appendChild(option);
        }
    }

    // Check if API key is available via embedded, local server or localStorage
    async function checkApiKey() {
        const apiKeyGroup = document.getElementById("api-key-group");
        const apiKeyInput = document.getElementById("api-key-input");
        
        // 1. Try embedded key first
        if (EMBEDDED_API_KEY) {
            apiKey = EMBEDDED_API_KEY;
            if (apiKeyGroup) apiKeyGroup.classList.add("hidden");
            document.getElementById("connection-status").textContent = "임베디드 API 키 사용";
            console.log("API key loaded from embedded .env.");
            return true;
        }
        
        // 2. Try fetching from server
        try {
            const res = await fetch("/api/key");
            if (res.ok) {
                const data = await res.json();
                if (data.key) {
                    apiKey = data.key;
                    if (apiKeyGroup) apiKeyGroup.classList.add("hidden");
                    document.getElementById("connection-status").textContent = "서버 API 키 로드됨";
                    console.log("API key loaded from server.");
                    return true;
                }
            }
        } catch (e) {
            console.log("Local API server key fetch bypassed.");
        }
        
        // 3. Try loading from localStorage
        const savedKey = localStorage.getItem("apt_api_key");
        if (savedKey) {
            apiKey = savedKey;
            if (apiKeyInput) apiKeyInput.value = savedKey;
            if (apiKeyGroup) apiKeyGroup.classList.remove("hidden");
            document.getElementById("connection-status").textContent = "로컬 저장 키 사용";
            console.log("API key loaded from localStorage.");
            return true;
        } else {
            // Force user to input key since no key is detected
            if (apiKeyGroup) apiKeyGroup.classList.remove("hidden");
            document.getElementById("connection-status").textContent = "인증키 입력 필요";
            return false;
        }
    }

    // Initialize Kakao Map
    function initKakaoMap() {
        if (typeof kakao === "undefined" || !kakao.maps) {
            console.error("Kakao Map SDK not loaded.");
            document.getElementById("map").innerHTML = 
                '<div style="padding:20px; color:var(--text-muted); text-align:center;">카카오 지도 SDK 로드 실패. API 키를 확인해 주세요.</div>';
            return;
        }
        
        try {
            const mapContainer = document.getElementById('map');
            const mapOption = { 
                center: new kakao.maps.LatLng(37.566826, 126.9786567), // Default: Seoul City Hall
                level: 7 // Zoom level
            }; 

            map = new kakao.maps.Map(mapContainer, mapOption); 
            geocoder = new kakao.maps.services.Geocoder();
            
            // Add zoom control
            const zoomControl = new kakao.maps.ZoomControl();
            map.addControl(zoomControl, kakao.maps.ControlPosition.RIGHT);
            console.log("Kakao Map initialized successfully.");
        } catch (e) {
            console.error("Error initializing Kakao Map:", e);
        }
    }

    // Clear all markers from map
    function clearMarkers() {
        activeMarkers.forEach(marker => marker.setMap(null));
        activeMarkers = [];
        if (activeCustomOverlay) {
            activeCustomOverlay.setMap(null);
            activeCustomOverlay = null;
        }
    }

    // Show Custom Overlay popup for an apartment
    function showOverlayForApt(apt, coords) {
        if (activeCustomOverlay) {
            activeCustomOverlay.setMap(null);
        }
        
        const deals = apt.deals;
        const prices = deals.map(d => d.dealAmount);
        const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;
        const maxPrice = Math.max(...prices);
        const latestDeal = deals[0];
        
        const content = `
            <div class="custom-overlay">
                <h5>${apt.aptNm}</h5>
                <p>평균가: <span class="overlay-price">${formatPrice(avgPrice)}</span></p>
                <p>최고가: <span class="overlay-price">${formatPrice(maxPrice)}</span></p>
                <p>거래량: ${deals.length}건 (${latestDeal.excluUseAr}㎡ / ${latestDeal.pyeong}평)</p>
            </div>
        `;
        
        activeCustomOverlay = new kakao.maps.CustomOverlay({
            content: content,
            position: coords,
            yAnchor: 1
        });
        
        activeCustomOverlay.setMap(map);
        map.panTo(coords);
    }

    // Map unique apartments and set markers
    function mapTransactionsToMap(transactions, sido, sigungu) {
        if (!map || !geocoder) return;
        clearMarkers();
        
        if (!transactions || transactions.length === 0) return;
        
        const aptGroup = {};
        transactions.forEach(t => {
            if (!aptGroup[t.aptNm]) {
                aptGroup[t.aptNm] = {
                    aptNm: t.aptNm,
                    umdNm: t.umdNm,
                    deals: []
                };
            }
            aptGroup[t.aptNm].deals.push(t);
        });
        
        const bounds = new kakao.maps.LatLngBounds();
        let markerCount = 0;
        const totalApts = Object.keys(aptGroup).length;
        
        Object.values(aptGroup).forEach(apt => {
            const fullAddress = `${sido} ${sigungu} ${apt.umdNm} ${apt.aptNm}`;
            
            geocoder.addressSearch(fullAddress, function(result, status) {
                if (status === kakao.maps.services.Status.OK) {
                    const coords = new kakao.maps.LatLng(result[0].y, result[0].x);
                    
                    const marker = new kakao.maps.Marker({
                        map: map,
                        position: coords,
                        title: apt.aptNm
                    });
                    
                    activeMarkers.push(marker);
                    bounds.extend(coords);
                    markerCount++;
                    
                    kakao.maps.event.addListener(marker, 'click', function() {
                        showOverlayForApt(apt, coords);
                    });
                    
                    if (markerCount === totalApts) {
                        map.setBounds(bounds);
                    }
                } else {
                    const fallbackAddress = `${sido} ${sigungu} ${apt.umdNm}`;
                    geocoder.addressSearch(fallbackAddress, function(result, status) {
                        if (status === kakao.maps.services.Status.OK) {
                            const coords = new kakao.maps.LatLng(result[0].y, result[0].x);
                            
                            const marker = new kakao.maps.Marker({
                                map: map,
                                position: coords,
                                title: apt.aptNm
                            });
                            
                            activeMarkers.push(marker);
                            bounds.extend(coords);
                            markerCount++;
                            
                            kakao.maps.event.addListener(marker, 'click', function() {
                                showOverlayForApt(apt, coords);
                            });
                            
                            if (markerCount === totalApts) {
                                map.setBounds(bounds);
                            }
                        } else {
                            markerCount++;
                            if (markerCount === totalApts) {
                                map.setBounds(bounds);
                            }
                        }
                    });
                }
            });
        });
    }

    // Handle table row click to center map on the selected apartment
    function handleTableClick(aptNm, umdNm) {
        if (!map || !geocoder) return;
        
        const sido = document.getElementById("sido-select").value;
        const sigunguSelect = document.getElementById("sigungu-select");
        const sigungu = sigunguSelect.options[sigunguSelect.selectedIndex].text;
        
        const fullAddress = `${sido} ${sigungu} ${umdNm} ${aptNm}`;
        
        geocoder.addressSearch(fullAddress, function(result, status) {
            if (status === kakao.maps.services.Status.OK) {
                const coords = new kakao.maps.LatLng(result[0].y, result[0].x);
                
                const matchedDeals = currentTransactions.filter(t => t.aptNm === aptNm);
                const aptObj = {
                    aptNm: aptNm,
                    umdNm: umdNm,
                    deals: matchedDeals
                };
                
                showOverlayForApt(aptObj, coords);
            } else {
                const fallbackAddress = `${sido} ${sigungu} ${umdNm}`;
                geocoder.addressSearch(fallbackAddress, function(result, status) {
                    if (status === kakao.maps.services.Status.OK) {
                        const coords = new kakao.maps.LatLng(result[0].y, result[0].x);
                        
                        const matchedDeals = currentTransactions.filter(t => t.aptNm === aptNm);
                        const aptObj = {
                            aptNm: aptNm,
                            umdNm: umdNm,
                            deals: matchedDeals
                        };
                        
                        showOverlayForApt(aptObj, coords);
                    }
                });
            }
        });
    }

    // Load Sido regions from internal object
    async function loadRegions() {
        const sidoSelect = document.getElementById("sido-select");
        sidoSelect.innerHTML = '<option value="" disabled selected>시/도 선택</option>';
        
        Object.keys(REGION_DATA).sort().forEach(sido => {
            const option = document.createElement("option");
            option.value = sido;
            option.textContent = sido;
            sidoSelect.appendChild(option);
        });
        
        await checkApiKey();
    }

    // Update Sigungu when Sido changes
    function handleSidoChange() {
        const sidoSelect = document.getElementById("sido-select");
        const sigunguSelect = document.getElementById("sigungu-select");
        
        const selectedSido = sidoSelect.value;
        sigunguSelect.innerHTML = '<option value="" disabled selected>시/군/구 선택</option>';
        sigunguSelect.disabled = true;
        
        if (selectedSido && REGION_DATA[selectedSido]) {
            const sigungus = REGION_DATA[selectedSido];
            
            Object.keys(sigungus).sort().forEach(sigungu => {
                const option = document.createElement("option");
                option.value = sigungus[sigungu]; // 5-digit code
                option.textContent = sigungu;
                sigunguSelect.appendChild(option);
            });
            
            sigunguSelect.disabled = false;
        }
    }

    // Hybrid Data Fetching: local cache server vs direct public API
    async function fetchAptData(lawdCd, year, month, monthsCount) {
        const isLocalServer = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
        
        if (isLocalServer && window.location.port === "8000") {
            try {
                console.log("Running in server mode. Querying local python cache server...");
                const url = `/api/search?lawd_cd=${lawdCd}&year=${year}&month=${month}&months_count=${monthsCount}`;
                const res = await fetch(url);
                if (res.ok) {
                    return await res.json();
                }
            } catch (e) {
                console.log("Local server API request failed, falling back to direct API fetch:", e);
            }
        }
        
        if (!apiKey) {
            throw new Error("공공데이터 API 인증키가 필요합니다. 사이드바에 입력해 주세요.");
        }
        
        console.log("Running in standalone mode. Fetching directly from data.go.kr...");
        const targetMonths = getPastMonthsList(year, month, monthsCount);
        const historicalTrend = [];
        let activeDeals = [];
        let activeStats = null;
        
        const activeYmd = `${year}${String(month).padStart(2, '0')}`;
        
        for (const ymd of [...targetMonths].reverse()) {
            const deals = await fetchAndCleanDirectAPI(lawdCd, ymd);
            const stats = calculateStatsJS(deals);
            
            const displayMonth = `${ymd.substring(0, 4)}.${ymd.substring(4)}`;
            historicalTrend.push({
                month: displayMonth,
                avg_price: stats.avg_price,
                total_deals: stats.total_deals,
                avg_pyeong_price: stats.avg_pyeong_price
            });
            
            if (ymd === activeYmd) {
                activeDeals = deals;
                activeStats = stats;
            }
        }
        
        if (!activeStats) {
            activeStats = calculateStatsJS([]);
        }
        
        return {
            active_month: `${year}.${String(month).padStart(2, '0')}`,
            transactions: activeDeals,
            stats: activeStats,
            historical_trend: historicalTrend
        };
    }

    function getPastMonthsList(year, month, count) {
        const res = [];
        let currY = parseInt(year);
        let currM = parseInt(month);
        for (let i = 0; i < count; i++) {
            res.push(`${currY}${String(currM).padStart(2, '0')}`);
            currM--;
            if (currM === 0) {
                currM = 12;
                currY--;
            }
        }
        return res;
    }

    async function fetchAndCleanDirectAPI(lawdCd, dealYmd) {
        const cacheKey = `cache_${lawdCd}_${dealYmd}`;
        const cached = sessionStorage.getItem(cacheKey);
        if (cached) {
            console.log(`Session Cache Hit: ${lawdCd} - ${dealYmd}`);
            return JSON.parse(cached);
        }
        
        const url = `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?serviceKey=${apiKey}&LAWD_CD=${lawdCd}&DEAL_YMD=${dealYmd}&numOfRows=2000&pageNo=1&_type=json`;
        
        console.log(`Session Cache Miss. Fetching: ${url.substring(0, 120)}...`);
        const res = await fetch(url);
        if (!res.ok) {
            throw new Error(`Public API returned status ${res.status}`);
        }
        
        const data = await res.json();
        const header = data?.response?.header || {};
        if (header.resultCode !== "000") {
            throw new Error(`API Error (${header.resultCode}): ${header.resultMsg}`);
        }
        
        const itemsNode = data?.response?.body?.items || {};
        if (!itemsNode || itemsNode === "") {
            return [];
        }
        
        let itemList = itemsNode.item || [];
        if (!Array.isArray(itemList)) {
            itemList = [itemList];
        }
        
        const cleaned = [];
        for (const item of itemList) {
            try {
                if (String(item.cdealDay || "").trim()) continue;
                
                const amountStr = String(item.dealAmount || "0").replace(/,/g, "").trim();
                const amount = parseInt(amountStr) || 0;
                if (amount === 0) continue;
                
                const areaStr = String(item.excluUseAr || "0").trim();
                const area = parseFloat(areaStr) || 0.0;
                if (area === 0.0) continue;
                
                const pyeong = area / 3.30578;
                const pyeongPrice = amount / pyeong;
                
                const floorStr = String(item.floor || "0").trim();
                const floor = parseInt(floorStr) || 0;
                
                cleaned.push({
                    aptNm: String(item.aptNm || "").trim(),
                    umdNm: String(item.umdNm || "").trim(),
                    dealAmount: amount,
                    excluUseAr: area,
                    pyeong: parseFloat(pyeong.toFixed(2)),
                    pyeongPrice: parseFloat(pyeongPrice.toFixed(2)),
                    floor: floor,
                    dealDay: parseInt(item.dealDay) || 1,
                    dealMonth: parseInt(item.dealMonth) || 1,
                    dealYear: parseInt(item.dealYear) || 2000,
                    buildYear: parseInt(item.buildYear) || 0
                });
            } catch (e) {
                console.error("Item parsing failed:", e);
            }
        }
        
        try {
            sessionStorage.setItem(cacheKey, JSON.stringify(cleaned));
        } catch (e) {
            console.log("sessionStorage quota exceeded");
        }
        
        return cleaned;
    }

    function calculateStatsJS(deals) {
        if (!deals || deals.length === 0) {
            return {
                avg_price: 0.0,
                total_deals: 0,
                avg_pyeong_price: 0.0,
                max_deal: null,
                min_deal: null,
                size_distribution: {
                    small: { count: 0, avg_price: 0.0 },
                    medium_small: { count: 0, avg_price: 0.0 },
                    medium_large: { count: 0, avg_price: 0.0 },
                    large: { count: 0, avg_price: 0.0 }
                },
                price_distribution: {
                    under_3: 0,
                    "3_to_6": 0,
                    "6_to_9": 0,
                    "9_to_12": 0,
                    "12_to_15": 0,
                    over_15: 0
                }
            };
        }
        
        const prices = deals.map(d => d.dealAmount);
        const pyeongPrices = deals.map(d => d.pyeongPrice);
        
        const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;
        const avgPyeongPrice = pyeongPrices.reduce((a, b) => a + b, 0) / pyeongPrices.length;
        
        let maxDeal = deals[0];
        let minDeal = deals[0];
        for (const d of deals) {
            if (d.dealAmount > maxDeal.dealAmount) maxDeal = d;
            if (d.dealAmount < minDeal.dealAmount) minDeal = d;
        }
        
        const sizeClasses = {
            small: { count: 0, sum_price: 0.0 },
            medium_small: { count: 0, sum_price: 0.0 },
            medium_large: { count: 0, sum_price: 0.0 },
            large: { count: 0, sum_price: 0.0 }
        };
        
        for (const d of deals) {
            const sz = d.excluUseAr;
            const p = d.dealAmount;
            if (sz < 60) {
                sizeClasses.small.count++;
                sizeClasses.small.sum_price += p;
            } else if (sz < 85) {
                sizeClasses.medium_small.count++;
                sizeClasses.medium_small.sum_price += p;
            } else if (sz < 135) {
                sizeClasses.medium_large.count++;
                sizeClasses.medium_large.sum_price += p;
            } else {
                sizeClasses.large.count++;
                sizeClasses.large.sum_price += p;
            }
        }
        
        const sizeDistribution = {};
        for (const [k, v] of Object.entries(sizeClasses)) {
            sizeDistribution[k] = {
                count: v.count,
                avg_price: v.count > 0 ? parseFloat((v.sum_price / v.count).toFixed(2)) : 0.0
            };
        }
        
        const priceBrackets = {
            under_3: 0,
            "3_to_6": 0,
            "6_to_9": 0,
            "9_to_12": 0,
            "12_to_15": 0,
            over_15: 0
        };
        
        for (const d of deals) {
            const p = d.dealAmount;
            if (p < 30000) {
                priceBrackets.under_3++;
            } else if (p < 60000) {
                priceBrackets["3_to_6"]++;
            } else if (p < 90000) {
                priceBrackets["6_to_9"]++;
            } else if (p < 120000) {
                priceBrackets["9_to_12"]++;
            } else if (p < 150000) {
                priceBrackets["12_to_15"]++;
            } else {
                priceBrackets.over_15++;
            }
        }
        
        return {
            avg_price: parseFloat(avgPrice.toFixed(2)),
            total_deals: deals.length,
            avg_pyeong_price: parseFloat(avgPyeongPrice.toFixed(2)),
            max_deal: maxDeal,
            min_deal: minDeal,
            size_distribution: sizeDistribution,
            price_distribution: priceBrackets
        };
    }

    // Run statistics query
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
        
        const searchBtn = document.getElementById("search-btn");
        const btnText = document.getElementById("btn-text");
        const btnSpinner = document.getElementById("btn-spinner");
        
        searchBtn.disabled = true;
        btnText.textContent = "분석 중...";
        btnSpinner.classList.remove("hidden");
        
        try {
            const data = await fetchAptData(lawdCd, year, month, monthsCount);
            
            updateDashboard(data, sidoText, sigunguText, year, month);
            
            document.getElementById("empty-dashboard-state").classList.add("hidden");
            document.getElementById("dashboard-body").classList.remove("hidden");
            
            // Force Kakao Map to recalculate layout now that it is visible
            if (map) {
                setTimeout(() => {
                    map.relayout();
                }, 100);
            }
            
            mapTransactionsToMap(data.transactions, sidoText, sigunguText);
        } catch (err) {
            console.error(err);
            alert("실거래 데이터를 조회하지 못했습니다: " + err.message);
        } finally {
            searchBtn.disabled = false;
            btnText.textContent = "통계 분석 실행";
            btnSpinner.classList.add("hidden");
        }
    }

    // Update Dashboard UI
    function updateDashboard(data, sido, sigungu, year, month) {
        const stats = data.stats;
        currentTransactions = data.transactions || [];
        
        document.getElementById("search-title-text").textContent = `${sido} ${sigungu} 아파트 실거래 분석 (${year}년 ${month}월)`;
        document.getElementById("search-subtitle-text").textContent = `최근 ${data.historical_trend.length}개월간의 거래 정보 시세 추이 및 상세 거래 리스트입니다.`;
        
        document.getElementById("kpi-avg-price").textContent = formatPrice(stats.avg_price);
        document.getElementById("kpi-total-deals").textContent = `${stats.total_deals.toLocaleString()}건`;
        document.getElementById("kpi-pyeong-price").textContent = stats.avg_pyeong_price > 0 ? `${Math.round(stats.avg_pyeong_price).toLocaleString()}만원` : "-";
        
        document.getElementById("kpi-avg-price-sub").textContent = `${sigungu} 평균 실거래가`;
        document.getElementById("kpi-total-deals-sub").textContent = `취소 거래 제외 실거래 건수`;
        
        const maxDeal = stats.max_deal;
        if (maxDeal) {
            document.getElementById("kpi-max-price").textContent = formatPrice(maxDeal.dealAmount);
            document.getElementById("kpi-max-desc").textContent = `${maxDeal.aptNm} ${maxDeal.floor}층 (${maxDeal.excluUseAr}㎡ / ${maxDeal.pyeong}평)`;
        } else {
            document.getElementById("kpi-max-price").textContent = "-";
            document.getElementById("kpi-max-desc").textContent = "거래 내역 없음";
        }
        
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
            
            document.getElementById("insight-dynamic-text").innerHTML = `
                ${year}년 ${month}월 기준 <strong>${sigungu}</strong>의 평균 아파트 매매가는 <strong>${formatPrice(stats.avg_price)}</strong>이며, 평당 단가는 <strong>${Math.round(stats.avg_pyeong_price).toLocaleString()}만원</strong>입니다. 
                총 <strong>${stats.total_deals}건</strong>의 실거래가 이루어졌으며, 최고가 거래 단지는 <strong>${maxDeal ? maxDeal.aptNm : '-'}</strong>입니다.
            `;
        } else {
            document.getElementById("stat-avg-area").textContent = "-";
            document.getElementById("stat-avg-floor").textContent = "-";
            document.getElementById("stat-avg-build-year").textContent = "-";
            document.getElementById("insight-dynamic-text").textContent = "해당 월에 등록된 실거래 데이터가 없습니다. 다른 연월을 선택해 분석해 보세요.";
        }
        
        renderTrendChart(data.historical_trend);
        renderSizeChart(stats.size_distribution);
        renderPriceDistChart(stats.price_distribution);
        
        document.getElementById("table-search-name").value = "";
        document.getElementById("filter-min-size").value = "";
        document.getElementById("filter-max-size").value = "";
        
        renderTable();
    }

    // Chart.js render configurations
    function renderTrendChart(trendData) {
        const ctx = document.getElementById("trendChart").getContext("2d");
        if (trendChartInstance) trendChartInstance.destroy();
        
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
                    legend: { labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) label += ': ';
                                if (context.datasetIndex === 1) {
                                    label += formatPrice(context.raw);
                                } else {
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
                        }
                    },
                    yVolume: {
                        type: 'linear',
                        position: 'left',
                        grid: { display: false },
                        ticks: { color: '#94a3b8', font: { family: 'Inter' } }
                    }
                }
            }
        });
    }

    function renderSizeChart(sizeData) {
        const ctx = document.getElementById("sizeChart").getContext("2d");
        if (sizeChartInstance) sizeChartInstance.destroy();
        
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
                        'rgba(56, 189, 248, 0.25)',
                        'rgba(16, 185, 129, 0.25)',
                        'rgba(168, 85, 247, 0.25)',
                        'rgba(251, 191, 36, 0.25)'
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

    function renderPriceDistChart(priceData) {
        const ctx = document.getElementById("priceDistChart").getContext("2d");
        if (priceDistChartInstance) priceDistChartInstance.destroy();
        
        const labels = ["3억 미만", "3억~6억", "6억~9억", "9억~12억", "12억~15억", "15억 이상"];
        const values = [
            priceData.under_3 || 0,
            priceData["3_to_6"] || 0,
            priceData["6_to_9"] || 0,
            priceData["9_to_12"] || 0,
            priceData["12_to_15"] || 0,
            priceData.over_15 || 0
        ];
        
        const totalCount = values.reduce((a, b) => a + b, 0);
        
        priceDistChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: totalCount > 0 ? values : [1],
                    backgroundColor: totalCount > 0 ? [
                        'rgba(148, 163, 184, 0.25)',
                        'rgba(16, 185, 129, 0.25)',
                        'rgba(56, 189, 248, 0.25)',
                        'rgba(99, 102, 241, 0.25)',
                        'rgba(168, 85, 247, 0.25)',
                        'rgba(239, 68, 68, 0.25)'
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

    // Render Transaction Log Table
    function renderTable() {
        const tableBody = document.getElementById("transaction-table-body");
        const emptyState = document.getElementById("table-empty-state");
        const subtitleCount = document.getElementById("table-subtitle-count");
        
        tableBody.innerHTML = "";
        
        const searchName = document.getElementById("table-search-name").value.toLowerCase().trim();
        const minSize = parseFloat(document.getElementById("filter-min-size").value) || 0;
        const maxSize = parseFloat(document.getElementById("filter-max-size").value) || Infinity;
        
        let filtered = currentTransactions.filter(t => {
            const matchesName = t.aptNm.toLowerCase().includes(searchName) || t.umdNm.toLowerCase().includes(searchName);
            const matchesSize = t.excluUseAr >= minSize && t.excluUseAr <= maxSize;
            return matchesName && matchesSize;
        });
        
        const sortKey = tableSortConfig.key;
        const isAsc = tableSortConfig.asc;
        
        filtered.sort((a, b) => {
            let valA = a[sortKey];
            let valB = b[sortKey];
            
            if (typeof valA === 'string') {
                return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }
            return isAsc ? valA - valB : valB - valA;
        });
        
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
            const dealDateStr = `${t.dealDay}일`;
            const priceStr = formatPrice(t.dealAmount).replace("만원", "");
            const areaStr = `${t.excluUseAr.toFixed(1)}㎡ / ${t.pyeong}평`;
            const pyeongPriceStr = `${Math.round(t.pyeongPrice).toLocaleString()}만원`;
            
            tr.addEventListener("click", () => {
                handleTableClick(t.aptNm, t.umdNm);
            });
            
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
                    tableSortConfig.asc = true;
                }
                
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

    function initEventListeners() {
        document.getElementById("sido-select").addEventListener("change", handleSidoChange);
        
        const slider = document.getElementById("trend-months");
        const sliderVal = document.getElementById("trend-val");
        slider.addEventListener("input", (e) => {
            sliderVal.textContent = `${e.target.value}개월`;
        });
        
        document.getElementById("search-form").addEventListener("submit", handleFormSubmit);
        
        document.getElementById("table-search-name").addEventListener("keyup", renderTable);
        document.getElementById("filter-min-size").addEventListener("input", renderTable);
        document.getElementById("filter-max-size").addEventListener("input", renderTable);
        
        document.getElementById("reset-filters-btn").addEventListener("click", () => {
            document.getElementById("table-search-name").value = "";
            document.getElementById("filter-min-size").value = "";
            document.getElementById("filter-max-size").value = "";
            renderTable();
        });

        // Save key button event (optional)
        const saveKeyBtn = document.getElementById("save-key-btn");
        if (saveKeyBtn) {
            saveKeyBtn.addEventListener("click", () => {
                const keyInput = document.getElementById("api-key-input") ? document.getElementById("api-key-input").value.trim() : "";
                if (keyInput) {
                    localStorage.setItem("apt_api_key", keyInput);
                    apiKey = keyInput;
                    document.getElementById("connection-status").textContent = "인증키 저장됨";
                    alert("공공데이터 API 인증키가 로컬 브라우저에 임시 저장되었습니다.");
                } else {
                    alert("인증키를 입력해주세요.");
                }
            });
        }
    }

    window.addEventListener("DOMContentLoaded", () => {
        populateYearSelect();
        populateMonthSelect();
        initEventListeners();
        initTableSorting();
        loadRegions();
        initKakaoMap();
    });
    """

    # 6. Replace string placeholders with actual values
    js_content = js_content.replace("__REGION_DATA_PLACEHOLDER__", region_json_str)
    js_content = js_content.replace("__APT_KEY_PLACEHOLDER__", apt_key)
    js_content = js_content.replace("__KAKAO_KEY_PLACEHOLDER__", kakao_js_key)

    # 7. Inject CSS & JS & Kakao Map SDK script tag
    style_tag = f"<style>\n{css_content}\n</style>"
    html_content = html_content.replace('<link rel="stylesheet" href="css/style.css">', style_tag)
    
    sdk_script = f'<script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={kakao_js_key}&libraries=services"></script>'
    html_content = html_content.replace('<!-- KAKAO_MAP_SDK_PLACEHOLDER -->', sdk_script)

    script_tag = f"<script>\n{js_content}\n</script>"
    html_content = html_content.replace('<script src="js/app.js"></script>', script_tag)
    
    # 8. Write final single HTML file to workspace root
    output_html_path = os.path.join(workspace_dir, "index.html")
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Successfully reverted single consolidated HTML file with Kakao Map SDK at {output_html_path}")

if __name__ == "__main__":
    build_single_html()
