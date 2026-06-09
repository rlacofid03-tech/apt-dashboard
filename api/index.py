from flask import Flask, jsonify, request, send_from_directory
import os
import json
import urllib.request
import urllib.parse
import configparser
from datetime import datetime

app = Flask(__name__)

# --- Configuration & Environment Helpers ---

def get_env_value(section, key, env_name):
    # 1. Check OS environment variable first (Vercel Production)
    val = os.environ.get(env_name)
    if val:
        return val.strip()
        
    # 2. Check local .env file (Local development)
    # Target directory is parent since this file is under /api
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        try:
            config = configparser.ConfigParser()
            config.read(env_path, encoding='utf-8')
            if section in config and key in config[section]:
                return config[section][key].strip()
        except Exception as e:
            print(f"Error reading local .env: {e}")
            
    return None

# Load API keys
API_KEY = get_env_value('APT', 'key', 'APT_KEY')
GITHUB_KEY = get_env_value('github', 'key', 'GITHUB_KEY')
GITHUB_OWNER = get_env_value('github', 'username', 'GITHUB_OWNER')

# Detect repository name
def get_repo_name():
    # 1. Check environment variable
    val = os.environ.get('GITHUB_REPO')
    if val:
        return val.strip()
        
    # 2. Try to parse from git config
    git_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.git', 'config')
    if os.path.exists(git_config_path):
        try:
            with open(git_config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if 'url =' in line:
                        url = line.split('url =')[1].strip()
                        url_clean = url.replace('.git', '')
                        if '/' in url_clean:
                            return url_clean.split('/')[-1]
        except Exception as e:
            print(f"Error parsing .git/config: {e}")
            
    return 'apt-dashboard' # Fallback

GITHUB_REPO = get_repo_name()

# --- Business Logic (Ported from main.py, SQLite cache removed) ---

def get_past_months(year, month, count=6):
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
    Directly queries data.go.kr API without SQLite caching.
    """
    if not API_KEY:
        raise ValueError("API key not found. Please set APT_KEY environment variable.")
        
    url = f"http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?serviceKey={API_KEY}&LAWD_CD={lawd_cd}&DEAL_YMD={deal_ymd}&numOfRows=2000&pageNo=1&_type=json"
    
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
                return None
                
            return data
    except Exception as e:
        print(f"API request failed for {lawd_cd} - {deal_ymd}: {e}")
        return None

def parse_and_clean_deals(raw_data):
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
                "under_3": 0, "3_to_6": 0, "6_to_9": 0,
                "9_to_12": 0, "12_to_15": 0, "over_15": 0
            }
        }
        
    prices = [d["dealAmount"] for d in deals]
    pyeong_prices = [d["pyeongPrice"] for d in deals]
    
    avg_price = sum(prices) / len(prices)
    avg_pyeong_price = sum(pyeong_prices) / len(pyeong_prices)
    
    max_deal = max(deals, key=lambda d: d["dealAmount"])
    min_deal = min(deals, key=lambda d: d["dealAmount"])
    
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
        
    price_brackets = {
        "under_3": 0, "3_to_6": 0, "6_to_9": 0,
        "9_to_12": 0, "12_to_15": 0, "over_15": 0
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

# --- Flask Routes ---

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response

@app.route('/api/key', methods=['GET'])
def get_api_key():
    return jsonify({"key": API_KEY})

@app.route('/api/regions', methods=['GET'])
def get_regions():
    root_dir = os.path.dirname(os.path.dirname(__file__))
    json_path = os.path.join(root_dir, 'sigungu_codes.json')
    if not os.path.exists(json_path):
        return jsonify({"error": "sigungu_codes.json not found"}), 404
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Failed to read regions: {e}"}), 500

@app.route('/api/search', methods=['GET'])
def handle_search():
    lawd_cd = request.args.get("lawd_cd")
    year = request.args.get("year")
    month = request.args.get("month")
    months_count_str = request.args.get("months_count", "6")
    
    if not lawd_cd or not year or not month:
        return jsonify({"error": "Missing required parameters: lawd_cd, year, month"}), 400
        
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
    
    for ymd in reversed(target_months):
        raw_data = fetch_raw_api_data(lawd_cd, ymd)
        deals = parse_and_clean_deals(raw_data)
        stats = calculate_monthly_stats(deals)
        
        display_m = f"{ymd[:4]}.{ymd[4:]}"
        historical_trend.append({
            "month": display_m,
            "avg_price": stats["avg_price"],
            "total_deals": stats["total_deals"],
            "avg_pyeong_price": stats["avg_pyeong_price"]
        })
        
        if ymd == active_ymd:
            active_deals = deals
            active_stats = stats
            
    if not active_stats:
        active_stats = calculate_monthly_stats([])
        
    # Ensure proper display formatting of month
    display_month = f"{year}.{int(month):02d}"
    
    response_data = {
        "active_month": display_month,
        "transactions": active_deals,
        "stats": active_stats,
        "historical_trend": historical_trend
    }
    
    return jsonify(response_data)

@app.route('/api/github/issues', methods=['GET'])
def handle_github_list_issues():
    if not GITHUB_KEY or not GITHUB_OWNER or not GITHUB_REPO:
        return jsonify({"configured": False, "issues": []})
        
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues?state=all&per_page=100"
    headers = {
        "Authorization": f"token {GITHUB_KEY}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Flask-Vercel"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            issues = json.loads(content)
            
            filtered_issues = []
            for issue in issues:
                if "pull_request" not in issue:
                    filtered_issues.append({
                        "number": issue.get("number"),
                        "title": issue.get("title"),
                        "body": issue.get("body") or "",
                        "state": issue.get("state"),
                        "html_url": issue.get("html_url"),
                        "created_at": issue.get("created_at"),
                        "user": issue.get("user", {}).get("login", "")
                    })
            
            return jsonify({
                "configured": True,
                "repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
                "issues": filtered_issues
            })
    except Exception as e:
        return jsonify({"error": f"Failed to fetch GitHub issues: {e}"}), 500

@app.route('/api/github/issues/create', methods=['POST'])
def handle_github_create_issue():
    if not GITHUB_KEY or not GITHUB_OWNER or not GITHUB_REPO:
        return jsonify({"error": "GitHub config not available"}), 400
        
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    body = data.get("body", "").strip()
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
        
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"token {GITHUB_KEY}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "Flask-Vercel"
    }
    
    post_body = json.dumps({"title": title, "body": body}).encode('utf-8')
    
    try:
        req = urllib.request.Request(url, data=post_body, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            res_data = json.loads(content)
            return jsonify({"success": True, "issue_number": res_data.get("number")})
    except Exception as e:
        return jsonify({"error": f"Failed to create GitHub issue: {e}"}), 500

@app.route('/api/github/issues/toggle', methods=['POST'])
def handle_github_toggle_issue():
    if not GITHUB_KEY or not GITHUB_OWNER or not GITHUB_REPO:
        return jsonify({"error": "GitHub config not available"}), 400
        
    data = request.get_json() or {}
    number = data.get("number")
    state = data.get("state", "").strip()
    
    if not number or state not in ['open', 'closed']:
        return jsonify({"error": "Invalid issue number or state"}), 400
        
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues/{number}"
    headers = {
        "Authorization": f"token {GITHUB_KEY}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "Flask-Vercel"
    }
    
    patch_body = json.dumps({"state": state}).encode('utf-8')
    
    try:
        req = urllib.request.Request(url, data=patch_body, headers=headers, method='PATCH')
        with urllib.request.urlopen(req, timeout=10) as response:
            return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to update GitHub issue: {e}"}), 500

# Local test runner
if __name__ == '__main__':
    app.run(port=8000, debug=True)
