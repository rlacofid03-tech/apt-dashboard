import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import sqlite3
import os
import configparser
from datetime import datetime

# Initialize configuration
PORT = 8000
DB_FILE = 'apt_cache.db'

def load_api_key():
    config = configparser.ConfigParser()
    try:
        # Check if .env file exists
        if os.path.exists('.env'):
            config.read('.env', encoding='utf-8')
            # Extract key under [APT] section
            if 'APT' in config and 'key' in config['APT']:
                return config['APT']['key'].strip()
    except Exception as e:
        print(f"Error loading API key: {e}")
    return None

API_KEY = load_api_key()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create table for caching raw responses
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_api_cache (
            lawd_cd TEXT,
            deal_ymd TEXT,
            response_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lawd_cd, deal_ymd)
        )
    """)
    conn.commit()
    conn.close()

def get_past_months(year, month, count=6):
    """
    Returns a list of YYYYMM strings representing the last `count` months,
    starting from the input year and month (inclusive) backwards.
    """
    res = []
    curr_y = int(year)
    curr_m = int(month)
    for _ in range(count):
        res.append(f"{curr_y}{curr_m:02d}")
        curr_m -= 1
        if curr_m == 0:
            curr_m = 12
            curr_y -= 1
    return res

def fetch_raw_api_data(lawd_cd, deal_ymd):
    """
    Checks cache first, queries data.go.kr API if not found, and saves to cache.
    """
    # Check cache
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT response_json FROM raw_api_cache WHERE lawd_cd=? AND deal_ymd=?", (lawd_cd, deal_ymd))
    row = cursor.fetchone()
    if row:
        conn.close()
        print(f"Cache hit: {lawd_cd} - {deal_ymd}")
        return json.loads(row[0])
    
    # Query API
    if not API_KEY:
        conn.close()
        raise ValueError("API key not found in .env under [APT] key = ...")
        
    url = f"http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?serviceKey={API_KEY}&LAWD_CD={lawd_cd}&DEAL_YMD={deal_ymd}&numOfRows=2000&pageNo=1&_type=json"
    
    print(f"Cache miss. Querying API: {lawd_cd} - {deal_ymd}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()
            res_str = content.decode("utf-8", errors="ignore")
            data = json.loads(res_str)
            
            # Check for API error
            header = data.get("response", {}).get("header", {})
            code = header.get("resultCode", "")
            if code != "000":
                msg = header.get("resultMsg", "Unknown error")
                print(f"API returned error code {code}: {msg}")
                # Don't cache bad requests
                conn.close()
                return None
                
            # Cache valid response
            cursor.execute("INSERT OR REPLACE INTO raw_api_cache (lawd_cd, deal_ymd, response_json) VALUES (?, ?, ?)", 
                           (lawd_cd, deal_ymd, res_str))
            conn.commit()
            conn.close()
            return data
    except Exception as e:
        print(f"API request failed for {lawd_cd} - {deal_ymd}: {e}")
        conn.close()
        return None

def parse_and_clean_deals(raw_data):
    """
    Parses items from JSON, removes cancelled transactions, and formats fields.
    """
    if not raw_data:
        return []
        
    body = raw_data.get("response", {}).get("body", {})
    if not body:
        return []
        
    items_node = body.get("items", {})
    if not items_node or items_node == "":
        return []
        
    item_list = items_node.get("item", [])
    if isinstance(item_list, dict):
        item_list = [item_list]
    elif not isinstance(item_list, list):
        return []
        
    cleaned = []
    for item in item_list:
        try:
            # Exclude cancelled deals
            cdeal_day = str(item.get("cdealDay", "")).strip()
            if cdeal_day:
                continue
                
            amount_str = str(item.get("dealAmount", "0")).replace(",", "").strip()
            amount = int(amount_str) if amount_str else 0
            if amount == 0:
                continue
                
            area_str = str(item.get("excluUseAr", "0")).strip()
            area = float(area_str) if area_str else 0.0
            if area == 0.0:
                continue
                
            pyeong = area / 3.30578
            pyeong_price = amount / pyeong if pyeong > 0 else 0.0
            
            floor_str = str(item.get("floor", "0")).strip()
            floor = int(floor_str) if floor_str.lstrip("-").isdigit() else 0
            
            cleaned.append({
                "aptNm": str(item.get("aptNm", "")).strip(),
                "umdNm": str(item.get("umdNm", "")).strip(),
                "dealAmount": amount,
                "excluUseAr": area,
                "pyeong": round(pyeong, 2),
                "pyeongPrice": round(pyeong_price, 2),
                "floor": floor,
                "dealDay": int(item.get("dealDay", 1)) if str(item.get("dealDay")).isdigit() else 1,
                "dealMonth": int(item.get("dealMonth", 1)) if str(item.get("dealMonth")).isdigit() else 1,
                "dealYear": int(item.get("dealYear", 2000)) if str(item.get("dealYear")).isdigit() else 2000,
                "buildYear": int(item.get("buildYear", 2000)) if str(item.get("buildYear")).isdigit() else 0
            })
        except Exception as e:
            print(f"Error parsing item: {e}")
            continue
            
    return cleaned

def calculate_monthly_stats(deals):
    if not deals:
        return {
            "avg_price": 0.0,
            "total_deals": 0,
            "avg_pyeong_price": 0.0,
            "max_deal": None,
            "min_deal": None,
            "size_distribution": {
                "small": {"count": 0, "avg_price": 0.0},
                "medium_small": {"count": 0, "avg_price": 0.0},
                "medium_large": {"count": 0, "avg_price": 0.0},
                "large": {"count": 0, "avg_price": 0.0}
            },
            "price_distribution": {
                "under_3": 0,
                "3_to_6": 0,
                "6_to_9": 0,
                "9_to_12": 0,
                "12_to_15": 0,
                "over_15": 0
            }
        }
        
    prices = [d["dealAmount"] for d in deals]
    pyeong_prices = [d["pyeongPrice"] for d in deals]
    
    avg_price = sum(prices) / len(prices)
    avg_pyeong_price = sum(pyeong_prices) / len(pyeong_prices)
    
    max_deal = max(deals, key=lambda d: d["dealAmount"])
    min_deal = min(deals, key=lambda d: d["dealAmount"])
    
    # Size classes: Small (<60), Medium-Small (60<=x<85), Medium-Large (85<=x<135), Large (>=135)
    size_classes = {
        "small": {"count": 0, "sum_price": 0.0},
        "medium_small": {"count": 0, "sum_price": 0.0},
        "medium_large": {"count": 0, "sum_price": 0.0},
        "large": {"count": 0, "sum_price": 0.0}
    }
    for d in deals:
        sz = d["excluUseAr"]
        p = d["dealAmount"]
        if sz < 60:
            size_classes["small"]["count"] += 1
            size_classes["small"]["sum_price"] += p
        elif sz < 85:
            size_classes["medium_small"]["count"] += 1
            size_classes["medium_small"]["sum_price"] += p
        elif sz < 135:
            size_classes["medium_large"]["count"] += 1
            size_classes["medium_large"]["sum_price"] += p
        else:
            size_classes["large"]["count"] += 1
            size_classes["large"]["sum_price"] += p
            
    size_distribution = {}
    for k, v in size_classes.items():
        count = v["count"]
        avg_p = v["sum_price"] / count if count > 0 else 0.0
        size_distribution[k] = {
            "count": count,
            "avg_price": round(avg_p, 2)
        }
        
    # Price brackets (under 3억, 3억~6억, 6억~9억, 9억~12억, 12억~15억, over 15억)
    price_brackets = {
        "under_3": 0,
        "3_to_6": 0,
        "6_to_9": 0,
        "9_to_12": 0,
        "12_to_15": 0,
        "over_15": 0
    }
    for d in deals:
        p = d["dealAmount"]
        if p < 30000:
            price_brackets["under_3"] += 1
        elif p < 60000:
            price_brackets["3_to_6"] += 1
        elif p < 90000:
            price_brackets["6_to_9"] += 1
        elif p < 120000:
            price_brackets["9_to_12"] += 1
        elif p < 150000:
            price_brackets["12_to_15"] += 1
        else:
            price_brackets["over_15"] += 1
            
    return {
        "avg_price": round(avg_price, 2),
        "total_deals": len(deals),
        "avg_pyeong_price": round(avg_pyeong_price, 2),
        "max_deal": max_deal,
        "min_deal": min_deal,
        "size_distribution": size_distribution,
        "price_distribution": price_brackets
    }

class APIServerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve files from root directory
        super().__init__(*args, directory=os.getcwd(), **kwargs)
        
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path.startswith('/api/'):
            self.handle_api(path, parsed_url.query)
        else:
            # Fallback to SimpleHTTPRequestHandler to serve index.html
            super().do_GET()
            
    def handle_api(self, path, query_string):
        query_params = urllib.parse.parse_qs(query_string)
        
        if path == '/api/key':
            self.send_json_response(200, {"key": API_KEY})
            
        elif path == '/api/regions':
            self.send_json_file('sigungu_codes.json')
            
        elif path == '/api/search':
            self.handle_search(query_params)
            
        else:
            self.send_error_response(404, "API endpoint not found.")

    def send_json_file(self, filename):
        if not os.path.exists(filename):
            self.send_error_response(404, f"File {filename} not found.")
            return
            
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.send_json_response(200, data)
        except Exception as e:
            self.send_error_response(500, f"Error reading config: {e}")

    def handle_search(self, query_params):
        lawd_cd = query_params.get("lawd_cd", [None])[0]
        year = query_params.get("year", [None])[0]
        month = query_params.get("month", [None])[0]
        months_count_str = query_params.get("months_count", ["6"])[0]
        
        if not lawd_cd or not year or not month:
            self.send_error_response(400, "Missing required parameters: lawd_cd, year, month")
            return
            
        try:
            months_count = int(months_count_str)
            if months_count < 1 or months_count > 12:
                months_count = 6
        except ValueError:
            months_count = 6
            
        active_ymd = f"{int(year)}{int(month):02d}"
        target_months = get_past_months(year, month, count=months_count)
        
        historical_trend = []
        active_deals = []
        active_stats = None
        
        # Loop backwards through the historical list (or reverse to show chronological order on front end)
        for ymd in reversed(target_months):
            raw_data = fetch_raw_api_data(lawd_cd, ymd)
            deals = parse_and_clean_deals(raw_data)
            stats = calculate_monthly_stats(deals)
            
            # Format month display name, e.g. "2024.07"
            display_m = f"{ymd[:4]}.{ymd[4:]}"
            historical_trend.append({
                "month": display_m,
                "avg_price": stats["avg_price"],
                "total_deals": stats["total_deals"],
                "avg_pyeong_price": stats["avg_pyeong_price"]
            })
            
            # If this is the main month the user searched for
            if ymd == active_ymd:
                active_deals = deals
                active_stats = stats
                
        # If we failed to get statistics for the active month (possibly due to API error/empty result)
        if not active_stats:
            active_stats = calculate_monthly_stats([])
            
        response_data = {
            "active_month": f"{year}.{month:02s}" if len(month) == 1 else f"{year}.{month}",
            "transactions": active_deals,
            "stats": active_stats,
            "historical_trend": historical_trend
        }
        
        self.send_json_response(200, response_data)

    def send_json_response(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_response(self, status, message):
        self.send_json_response(status, {"error": message})

def run_server():
    init_db()
    if not API_KEY:
        print("WARNING: API key not found in .env! Requests to API will fail. Please ensure the key matches '[APT]\nkey = ...'")
    else:
        print("API Key loaded successfully.")

    # Python's ThreadingHTTPServer handles concurrent connections smoothly
    with socketserver.ThreadingTCPServer(("", PORT), APIServerHandler) as httpd:
        print(f"Serving Apartment Price Statistics Dashboard MVP at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    run_server()
