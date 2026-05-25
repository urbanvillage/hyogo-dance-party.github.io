#!/usr/bin/env python3
"""
=====================================================================
  兵庫県 社交ダンス情報 自動収集ツール v4.0
  Hyogo Dance Party Auto Collector

  収集元（全8サイト）：
    1. 乾さんのHP 兵庫県版 (tatsumi-n.private.coocan.jp/PartySch1.htm)
    2. 乾さんのHP 三田近郊  (eonet.ne.jp/~dance-party/party.html)
    3. JDSF兵庫              (jdsf-hyogo.com)
    4. 兵庫県社交ダンス教師協会 (jbdf-hsdta.jp)
    5. ビデオフォーダンス    (video4dance.com/DP/index.php)
    6. 猪名川社交ダンス倶楽部 (tatsumi-n.private.coocan.jp/Inagawa_HP/)
    7. 神戸YMCA社交ダンスクラブ (so7348.wixsite.com/kobeymcadance)
    8. X（旧Twitter）キーワード検索

  出力：
    - Googleスプレッドシートに自動追記（新着のみ・審査中ステータス）
    - メール通知（Gmail）

  必要ライブラリ：
    pip install requests beautifulsoup4 gspread google-auth
=====================================================================
"""

import os, re, json, time, logging, smtplib, hashlib, base64
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  設定（GitHub Secrets から自動注入）
# ══════════════════════════════════════════════════════════════
CONFIG = {
    "GMAIL_USER":     os.getenv("GMAIL_USER",    "your-email@gmail.com"),
    "GMAIL_PASS":     os.getenv("GMAIL_PASS",    "xxxx-xxxx-xxxx-xxxx"),
    "ADMIN_EMAIL":    os.getenv("GMAIL_USER",    "your-email@gmail.com"),
    "GS_SHEET_ID":    os.getenv("GS_SHEET_ID",  None),
    "GS_CREDS":       os.getenv("GS_CREDS",     None),
    "GS_SHEET_NAME":  os.getenv("GS_SHEET_NAME","📋 回答データ"),
    "X_BEARER_TOKEN": os.getenv("X_BEARER_TOKEN", None),
    "X_QUERIES": [
        "兵庫 社交ダンス パーティー",
        "神戸 社交ダンス パーティー",
        "兵庫 ダンスパーティー 2026",
        "三田 社交ダンス パーティー",
        "尼崎 社交ダンス パーティー",
        "西宮 社交ダンス パーティー",
    ],
    "X_DAYS":       3,
    "KNOWN_FILE":   "known_parties.json",
    "OUTPUT_FILE":  "scraped_result.json",
    "TIMEOUT":      15,
    "RETRY":         2,
    "DELAY":         2,
    "HEADERS": {
        "User-Agent": (
            "Mozilla/5.0 (compatible; HyogoDanceBot/4.0; "
            "+https://urbanvillage.github.io/hyogo-dance-party.github.io/)"
        )
    },
}

# ══════════════════════════════════════════════════════════════
#  ユーティリティ
# ══════════════════════════════════════════════════════════════

def fetch_html(url, encoding=None):
    for attempt in range(CONFIG["RETRY"] + 1):
        try:
            r = requests.get(url, headers=CONFIG["HEADERS"],
                             timeout=CONFIG["TIMEOUT"])
            r.raise_for_status()
            r.encoding = encoding or r.apparent_encoding
            log.info(f"  取得成功: {url} ({r.status_code})")
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            log.warning(f"  取得失敗 (試行{attempt+1}): {e}")
            if attempt < CONFIG["RETRY"]:
                time.sleep(3)
    return None


def normalize_date(text):
    text = text.strip()
    for pat in [
        r"(20\d{2})[/\-](\d{1,2})[/\-](\d{1,2})",
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
    ]:
        m = re.search(pat, text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        today = date.today()
        mo, da = int(m.group(1)), int(m.group(2))
        for yr in [today.year, today.year + 1]:
            try:
                if date(yr, mo, da) >= today:
                    return f"{yr}-{mo:02d}-{da:02d}"
            except ValueError:
                pass
    return None


def is_future(ds):
    try:
        return date.fromisoformat(ds) >= date.today()
    except Exception:
        return False


def make_id(item):
    raw = f"{item.get('date','')}{item.get('name','')}{item.get('venue','')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def guess_region(text):
    if any(k in text for k in ["神戸","三宮","灘","垂水","長田","須磨","北区","中央区","兵庫区","東灘","西区"]):
        return "神戸市内"
    if any(k in text for k in ["三田","広野","ネスタ","北摂"]):
        return "三田・北摂"
    if any(k in text for k in ["姫路","明石","加古川","播磨","高砂","小野","三木","西脇"]):
        return "播磨（姫路・明石・加古川等）"
    if any(k in text for k in ["西宮","尼崎","芦屋","伊丹","宝塚","川西","猪名川","日生","箕面"]):
        return "阪神（西宮・尼崎・芦屋等）"
    if any(k in text for k in ["丹波","篠山","柏原","但馬","豊岡","朝来","淡路","洲本"]):
        return "丹波・但馬・淡路"
    return "兵庫県内"


def load_known():
    p = Path(CONFIG["KNOWN_FILE"])
    return set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()


def save_known(ids):
    Path(CONFIG["KNOWN_FILE"]).write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def extract_time(text):
    m = re.search(r"(\d{1,2}:\d{2})\s*[〜～]\s*(\d{1,2}:\d{2})", text)
    return f"{m.group(1)}〜{m.group(2)}" if m else ""


def extract_fee(text):
    m = re.search(r"[¥\\￥]?(\d{3,6})\s*円", text)
    return int(m.group(1)) if m else 0


# ══════════════════════════════════════════════════════════════
#  スクレイパー①：乾さんのHP（兵庫県版）
# ══════════════════════════════════════════════════════════════

def scrape_tatsumi_hyogo():
    log.info("【1】乾さんのHP（兵庫県版）を巡回中...")
    results = []
    url = "http://tatsumi-n.private.coocan.jp/PartySch1.htm"
    soup = fetch_html(url, encoding="shift_jis")
    if not soup:
        return results

    text = soup.get_text("\n", strip=True)
    pattern = re.compile(
        r"[・･]?\s*(\d{1,2}月\d{1,2}日)[（(]([月火水木金土日・祝]+)[）)]\s*"
        r"(\d{1,2}:\d{2}[～〜]\d{1,2}:\d{2})\s*"
        r"[\\¥￥]?(\d{1,5})\s*([^\n・]{1,30})"
    )

    current_venue = ""
    for line in text.split("\n"):
        line = line.strip()
        # 会場名行を検出（(数字) 会場名 パターン）
        vm = re.match(r"[（(]\d+[）)]\s*(.{4,30})", line)
        if vm and any(k in line for k in ["センター","ホール","会館","体育館","公民館","スタジオ"]):
            current_venue = vm.group(1).split("　")[0].strip()

        for m in pattern.finditer(line):
            date_raw, dow, time_, fee, circle = m.groups()
            date_str = normalize_date(date_raw)
            if not date_str or not is_future(date_str):
                continue
            circle = circle.strip()
            results.append({
                "source":     "乾さんのHP（兵庫）",
                "source_url": url,
                "name":       circle,
                "date":       date_str,
                "time":       time_,
                "venue":      current_venue,
                "fee":        int(fee),
                "region":     guess_region(current_venue + circle),
                "contact":    "",
                "pr":         "",
            })
            log.info(f"    {date_str} {circle} ¥{fee} ({current_venue})")

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  スクレイパー②：乾さんのHP（三田近郊版）
# ══════════════════════════════════════════════════════════════

def scrape_tatsumi_sanda():
    log.info("【2】乾さんのHP（三田近郊）を巡回中...")
    results = []
    url = "http://www.eonet.ne.jp/~dance-party/party.html"
    soup = fetch_html(url, encoding="shift_jis")
    if not soup:
        return results

    text = soup.get_text("\n", strip=True)
    # 三田近郊は会場ごとに「会場名：」で区切られた形式が多い
    pattern = re.compile(
        r"[・･]?\s*(\d{1,2}月\d{1,2}日)[（(]([月火水木金土日・祝]+)[）)]\s*"
        r"(\d{1,2}:\d{2}[～〜]\d{1,2}:\d{2})\s*"
        r"[\\¥￥]?(\d{1,5})\s*([^\n・]{1,30})"
    )

    current_venue = ""
    for line in text.split("\n"):
        line = line.strip()
        # 会場名を検出
        if any(k in line for k in ["市民センター","公民館","ホール","会館"]) and len(line) < 40:
            current_venue = line

        for m in pattern.finditer(line):
            date_raw, dow, time_, fee, circle = m.groups()
            date_str = normalize_date(date_raw)
            if not date_str or not is_future(date_str):
                continue
            circle = circle.strip()
            results.append({
                "source":     "乾さんのHP（三田近郊）",
                "source_url": url,
                "name":       circle,
                "date":       date_str,
                "time":       time_,
                "venue":      current_venue or "三田近郊",
                "fee":        int(fee),
                "region":     guess_region(current_venue + circle),
                "contact":    "",
                "pr":         "",
            })
            log.info(f"    {date_str} {circle} ¥{fee}")

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  スクレイパー③：JDSF兵庫
# ══════════════════════════════════════════════════════════════

def scrape_jdsf_hyogo():
    log.info("【3】JDSF兵庫 を巡回中...")
    results = []
    url = "https://www.jdsf-hyogo.com/"
    soup = fetch_html(url)
    if not soup:
        return results

    party_kws = ["パーティー","party","Party","カーニバル","交流会","大会","祭典","発表会"]

    for el in soup.select("article h2 a, article h3 a, .entry-title a, .post-title a, h2 > a"):
        title = el.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        if not any(kw in title for kw in party_kws):
            continue

        href = el.get("href", url)
        date_str = time_ = venue = ""
        fee = 0

        sub = fetch_html(href)
        if sub:
            body = sub.get_text(" ", strip=True)[:2000]
            date_str = normalize_date(body)
            fee      = extract_fee(body)
            time_    = extract_time(body)
            vm = re.search(r"会場[：:]\s*([^\n。、]{4,30})", body)
            venue = vm.group(1).strip() if vm else ""

        if not date_str or not is_future(date_str):
            continue

        results.append({
            "source":     "JDSF兵庫",
            "source_url": href,
            "name":       title,
            "date":       date_str,
            "time":       time_,
            "venue":      venue,
            "fee":        fee,
            "region":     guess_region(venue + title),
            "contact":    "www.jdsf-hyogo.com",
            "pr":         "",
        })
        log.info(f"    {date_str} {title[:30]}")
        time.sleep(1)

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  スクレイパー④：兵庫県社交ダンス教師協会
# ══════════════════════════════════════════════════════════════

def scrape_jbdf_hsdta():
    log.info("【4】兵庫県社交ダンス教師協会 を巡回中...")
    results = []
    urls = [
        "http://www.jbdf-hsdta.jp/carnival.html",
        "http://www.jbdf-hsdta.jp/schedule.html",
        "http://www.jbdf-hsdta.jp/",
    ]
    party_kws = ["パーティー","カーニバル","交流","Party","大会","祭典"]

    for url in urls:
        soup = fetch_html(url, encoding="shift_jis")
        if not soup:
            continue
        found = False
        for row in soup.select("tr"):
            cells = [td.get_text(" ", strip=True) for td in row.select("td,th")]
            if len(cells) < 2:
                continue
            row_text = " ".join(cells)
            if not any(kw in row_text for kw in party_kws):
                continue
            date_str = normalize_date(row_text)
            if not date_str or not is_future(date_str):
                continue
            name = max(
                (c for c in cells if c and not re.search(r"20\d{2}[年/]", c)),
                key=len, default="詳細要確認"
            )
            results.append({
                "source":     "兵庫県社交ダンス教師協会",
                "source_url": url,
                "name":       name,
                "date":       date_str,
                "time":       extract_time(row_text),
                "venue":      "",
                "fee":        extract_fee(row_text),
                "region":     "神戸市内",
                "contact":    "www.jbdf-hsdta.jp",
                "pr":         "",
            })
            log.info(f"    {date_str} {name[:30]}")
            found = True
        if found:
            break
        time.sleep(1)

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  スクレイパー⑤：ビデオフォーダンス
# ══════════════════════════════════════════════════════════════

def scrape_video4dance():
    log.info("【5】ビデオフォーダンス を巡回中...")
    results = []
    url = "https://video4dance.com/DP/index.php"

    # UTF-8 → Shift-JIS の順で試みる
    soup = fetch_html(url, encoding="utf-8")
    if not soup or len(soup.get_text()) < 100:
        soup = fetch_html(url, encoding="shift_jis")
    if not soup:
        return results

    hyogo_kws = [
        "神戸","兵庫","三宮","ポートピア",
        "西宮","尼崎","芦屋","宝塚","伊丹","川西","猪名川",
        "三田","姫路","明石","加古川","播磨",
        "丹波","但馬","淡路","豊岡",
    ]

    for row in soup.select("tr"):
        cells = [td.get_text(" ", strip=True) for td in row.select("td")]
        if len(cells) < 3:
            continue
        row_text = " ".join(cells)
        if not any(kw in row_text for kw in hyogo_kws):
            continue
        date_str = normalize_date(row_text)
        if not date_str or not is_future(date_str):
            continue
        name = max(cells, key=len)
        results.append({
            "source":     "ビデオフォーダンス",
            "source_url": url,
            "name":       name,
            "date":       date_str,
            "time":       extract_time(row_text),
            "venue":      "",
            "fee":        extract_fee(row_text),
            "region":     guess_region(row_text),
            "contact":    "",
            "pr":         "",
        })
        log.info(f"    {date_str} {name[:30]}")

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  スクレイパー⑥：猪名川社交ダンス倶楽部
# ══════════════════════════════════════════════════════════════

def scrape_inagawa():
    log.info("【6】猪名川社交ダンス倶楽部 を巡回中...")
    results = []
    url = "https://tatsumi-n.private.coocan.jp/Inagawa_HP/PartyInfo.htm"
    soup = fetch_html(url, encoding="shift_jis")
    if not soup:
        return results

    text = soup.get_text("\n", strip=True)
    pattern = re.compile(
        r"[・･]?\s*(\d{1,2}月\d{1,2}日)[（(]([月火水木金土日・祝]+)[）)]\s*"
        r"(\d{1,2}:\d{2}[～〜]\d{1,2}:\d{2})\s*"
        r"[\\¥￥]?(\d{1,5})"
    )

    for m in pattern.finditer(text):
        date_raw, dow, time_, fee = m.groups()
        date_str = normalize_date(date_raw)
        if not date_str or not is_future(date_str):
            continue
        results.append({
            "source":     "猪名川社交ダンス倶楽部",
            "source_url": url,
            "name":       "日生社交ダンス愛好会 練習会パーティー",
            "date":       date_str,
            "time":       time_,
            "venue":      "日生公民館2F 総合室（猪名川町松尾台1-2-20）",
            "fee":        int(fee),
            "region":     "阪神（西宮・尼崎・芦屋等）",
            "contact":    "長井 090-5168-9567",
            "pr":         "日生中央駅すぐ。500円で気軽に参加できます。",
        })
        log.info(f"    {date_str} 日生社交ダンス愛好会 ¥{fee}")

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  スクレイパー⑦：神戸YMCA社交ダンスクラブ
# ══════════════════════════════════════════════════════════════

def scrape_kobe_ymca():
    log.info("【7】神戸YMCA社交ダンスクラブ を巡回中...")
    results = []
    url = "https://so7348.wixsite.com/kobeymcadance"
    soup = fetch_html(url)
    if not soup:
        return results

    text = soup.get_text("\n", strip=True)
    party_kws = ["パーティー","party","Party"]
    if not any(kw in text for kw in party_kws):
        log.info("  パーティー情報なし")
        return results

    # 日付と参加費を抽出
    date_str = normalize_date(text)
    if not date_str or not is_future(date_str):
        log.info("  未来のパーティー情報なし")
        return results

    fee  = extract_fee(text) or 900   # 通常900円
    time_ = extract_time(text) or "13:00〜16:30"

    results.append({
        "source":     "神戸YMCA社交ダンスクラブ",
        "source_url": url,
        "name":       "神戸YMCA社交ダンスクラブ ダンスパーティー",
        "date":       date_str,
        "time":       time_,
        "venue":      "神戸市中央区文化センター（神戸市中央区東町115番地）",
        "fee":        fee,
        "region":     "神戸市内",
        "contact":    "090-1139-4871（徐）/ 090-3996-1328（北）",
        "pr":         "kobeymca@okura.jp",
    })
    log.info(f"    {date_str} 神戸YMCA ¥{fee}")

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  スクレイパー⑧：X（旧Twitter）API v2
# ══════════════════════════════════════════════════════════════

def scrape_x_twitter():
    token = CONFIG["X_BEARER_TOKEN"]
    if not token:
        log.info("【8】X（Twitter）: Bearer Token 未設定のためスキップ")
        return []

    log.info("【8】X（Twitter）を検索中...")
    results = []
    headers = {"Authorization": f"Bearer {token}"}

    from datetime import timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=CONFIG["X_DAYS"])).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    party_kws = ["パーティー","ダンスパーティ","party","Party","カーニバル"]

    for query_base in CONFIG["X_QUERIES"]:
        query = f'{query_base} -is:retweet lang:ja'
        params = {
            "query":        query,
            "max_results":  20,
            "start_time":   since,
            "tweet.fields": "created_at,text,author_id",
            "expansions":   "author_id",
            "user.fields":  "name,username",
        }
        try:
            r = requests.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers=headers, params=params, timeout=CONFIG["TIMEOUT"]
            )
            if r.status_code == 429:
                log.warning("  X API レート制限 → 15分待機")
                time.sleep(900)
                continue
            if r.status_code != 200:
                log.warning(f"  X API エラー: {r.status_code}")
                continue

            data = r.json()
            tweets = data.get("data", [])
            users  = {u["id"]: u for u in data.get("includes",{}).get("users",[])}
            log.info(f"  クエリ「{query_base}」: {len(tweets)}件")

            for tweet in tweets:
                text    = tweet.get("text","")
                tid     = tweet.get("id","")
                uid     = tweet.get("author_id","")
                uscreen = users.get(uid,{}).get("username","")

                if not any(kw in text for kw in party_kws):
                    continue

                date_str = normalize_date(text)
                if date_str and not is_future(date_str):
                    continue

                results.append({
                    "source":     f"X（@{uscreen}）",
                    "source_url": f"https://x.com/{uscreen}/status/{tid}",
                    "name":       text.replace("\n"," ")[:60],
                    "date":       date_str or f"（要確認）",
                    "time":       extract_time(text),
                    "venue":      "",
                    "fee":        extract_fee(text),
                    "region":     guess_region(text),
                    "contact":    f"@{uscreen}",
                    "pr":         text[:200],
                })
                log.info(f"    @{uscreen}: {text[:40]}")

        except Exception as e:
            log.error(f"  X API 例外: {e}")
        time.sleep(2)

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  重複除去・新着抽出
# ══════════════════════════════════════════════════════════════

def deduplicate(items):
    seen, result = set(), []
    for item in items:
        key = f"{item['date']}-{item['name'][:20]}"
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def filter_new(items, known):
    new = []
    for item in items:
        uid = make_id(item)
        if uid not in known:
            item["_id"] = uid
            new.append(item)
    return new


# ══════════════════════════════════════════════════════════════
#  Googleスプレッドシートに追記
# ══════════════════════════════════════════════════════════════

def append_to_spreadsheet(new_items):
    if not CONFIG["GS_SHEET_ID"] or not CONFIG["GS_CREDS"]:
        log.info("スプレッドシート未設定のためスキップ")
        return
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_json = base64.b64decode(CONFIG["GS_CREDS"]).decode("utf-8")
        creds = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(CONFIG["GS_SHEET_ID"])
        try:
            ws = sh.worksheet(CONFIG["GS_SHEET_NAME"])
        except Exception:
            ws = sh.sheet1

        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        rows = [[
            now, "", "審査中", "",
            f"自動収集:{item['source']}",
            item["name"], item["date"], item["time"],
            item["region"], item["venue"], "",
            str(item["fee"]) if item["fee"] else "",
            "", "", "",
            "", item["contact"], "",
            item.get("pr",""), item["source_url"],
        ] for item in new_items]

        ws.append_rows(rows, value_input_option="USER_ENTERED")
        log.info(f"✅ スプレッドシートに {len(rows)} 件追記")
    except ImportError:
        log.error("❌ pip install gspread google-auth が必要です")
    except Exception as e:
        log.error(f"❌ スプレッドシートエラー: {e}")


# ══════════════════════════════════════════════════════════════
#  メール通知
# ══════════════════════════════════════════════════════════════

def send_email(new_items, total):
    if CONFIG["GMAIL_PASS"] in ("xxxx-xxxx-xxxx-xxxx",""):
        log.warning("Gmail未設定のためスキップ")
        return

    n = len(new_items)
    subject = f"【新着{n}件】兵庫県社交ダンス情報 {datetime.now().strftime('%Y/%m/%d')}"

    by_source = {}
    for item in new_items:
        by_source.setdefault(item["source"], []).append(item)

    lines = [
        "兵庫県社交ダンス情報 自動収集レポート",
        f"収集日時：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}",
        f"新着：{n}件　／　収集総数：{total}件",
        "", "【スプレッドシートで承認ステータスを「公開」に変更してください】",
        "", "="*56, "",
    ]
    for src, items in by_source.items():
        lines.append(f"■ {src}（{len(items)}件）")
        for item in items:
            lines += [
                f"  ・{item['name'][:50]}",
                f"    日付：{item['date']}　時間：{item['time'] or '未定'}",
                f"    会場：{item['venue'] or '未定'}　地域：{item['region']}",
                f"    費用：{item['fee']:,}円" if item['fee'] else "    費用：要確認",
                f"    URL ：{item['source_url']}", "",
            ]
    lines += ["="*56, "兵庫ダンスパーティー情報サイト 自動収集システム"]

    try:
        msg = MIMEMultipart()
        msg["From"]    = CONFIG["GMAIL_USER"]
        msg["To"]      = CONFIG["ADMIN_EMAIL"]
        msg["Subject"] = subject
        msg.attach(MIMEText("\n".join(lines),"plain","utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(CONFIG["GMAIL_USER"], CONFIG["GMAIL_PASS"])
            s.send_message(msg)
        log.info(f"✅ メール送信完了 → {CONFIG['ADMIN_EMAIL']}")
    except Exception as e:
        log.error(f"❌ メール送信失敗: {e}")


def save_json(all_items):
    Path(CONFIG["OUTPUT_FILE"]).write_text(
        json.dumps({"scraped_at": datetime.now().isoformat(),
                    "count": len(all_items), "parties": all_items},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"📄 保存: {CONFIG['OUTPUT_FILE']}")


# ══════════════════════════════════════════════════════════════
#  メイン
# ══════════════════════════════════════════════════════════════

def main():
    log.info("="*56)
    log.info("兵庫県社交ダンス情報 自動収集ツール v4.0")
    log.info(f"収集対象：乾さんHP×2・JDSF兵庫・教師協会・ビデオフォーダンス・猪名川・神戸YMCA・X")
    log.info(f"実行日時：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("="*56)

    all_items = []

    # サイト別スクレイパーを順番に実行
    scrapers = [
        ("乾さんHP（兵庫）",    scrape_tatsumi_hyogo),
        ("乾さんHP（三田近郊）", scrape_tatsumi_sanda),
        ("JDSF兵庫",            scrape_jdsf_hyogo),
        ("兵庫県教師協会",       scrape_jbdf_hsdta),
        ("ビデオフォーダンス",   scrape_video4dance),
        ("猪名川社交ダンス倶楽部", scrape_inagawa),
        ("神戸YMCA",            scrape_kobe_ymca),
        ("X（Twitter）",        scrape_x_twitter),
    ]

    for name, scraper in scrapers:
        try:
            items = scraper()
            all_items.extend(items)
            log.info(f"  ✓ {name}: {len(items)}件")
        except Exception as e:
            log.error(f"  ✗ {name}: {e}")
        time.sleep(CONFIG["DELAY"])

    total = len(all_items)
    log.info(f"\n合計検出: {total}件（重複含む）")

    all_items = deduplicate(all_items)
    log.info(f"重複除去後: {len(all_items)}件")

    known = load_known()
    new_items = filter_new(all_items, known)
    log.info(f"新着: {len(new_items)}件")

    save_json(all_items)

    if new_items:
        log.info("\n── 新着一覧 ─────────────────────────────────")
        for item in new_items:
            log.info(f"  {item['date']} {item['name'][:35]} [{item['source']}]")

        append_to_spreadsheet(new_items)
        send_email(new_items, total)

        for item in new_items:
            known.add(item["_id"])
        save_known(known)
    else:
        log.info("新着情報はありませんでした")

    log.info("✅ 完了")


if __name__ == "__main__":
    main()
