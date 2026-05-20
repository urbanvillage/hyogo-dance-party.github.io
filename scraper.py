"""
兵庫県 社交ダンスパーティー 自動収集スクリプト
================================================
対象サイト：
  1. JDSF兵庫（https://www.jdsf-hyogo.com/）
  2. 兵庫県社交ダンス教師協会（http://www.jbdf-hsdta.jp/carnival.html）
  3. 乾さんのHP・三田近郊（http://tatsumi-n.private.coocan.jp/PartySch1.htm）
  4. ビデオフォーダンス（https://video4dance.com/DP/index.php）

実行方法：
  python3 scraper.py

GitHub Actionsで自動実行する場合：
  .github/workflows/scrape.yml を設定（このファイルの末尾参照）

必要ライブラリのインストール：
  pip install requests beautifulsoup4 gspread google-auth
"""

import re
import json
import time
import smtplib
import logging
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── ログ設定 ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  設定（ここを編集してください）
# ══════════════════════════════════════════════════════════════
CONFIG = {
    # 管理者メールアドレス（通知の送信先）
    "ADMIN_EMAIL":   "hirarinx@gmail.com",

    # Gmailの送信設定（Gmailのアプリパスワードを使用）
    # ※ GitHub Actionsで使う場合はSecretsに設定
    "GMAIL_USER":    "hirarinx@gmail.com",
    "GMAIL_PASS":    "oyre rlfo kslc gpaf",  # Gmailアプリパスワード

    # 既知パーティーIDを記録するファイル（重複通知を防ぐ）
    "KNOWN_IDS_FILE": "known_parties.json",

    # 収集結果のJSONファイル
    "OUTPUT_FILE":    "scraped_parties.json",

    # HTTPリクエスト設定
    "TIMEOUT": 15,
    "RETRY":   2,
    "HEADERS": {
        "User-Agent": (
            "Mozilla/5.0 (compatible; HyogoDanceBot/1.0; "
            "+https://urbanvillage.github.io/hyogo-dance-party.github.io/)"
        )
    },
}

# ══════════════════════════════════════════════════════════════
#  ユーティリティ
# ══════════════════════════════════════════════════════════════

def fetch(url: str, encoding: str = None) -> BeautifulSoup | None:
    """URLを取得してBeautifulSoupを返す。失敗時はNone。"""
    for attempt in range(CONFIG["RETRY"] + 1):
        try:
            r = requests.get(
                url,
                headers=CONFIG["HEADERS"],
                timeout=CONFIG["TIMEOUT"],
            )
            r.raise_for_status()
            if encoding:
                r.encoding = encoding
            else:
                r.encoding = r.apparent_encoding
            log.info(f"  取得成功: {url} ({r.status_code})")
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            log.warning(f"  取得失敗 (試行{attempt+1}): {url} → {e}")
            time.sleep(2)
    return None


def normalize_date(text: str) -> str | None:
    """
    様々な形式の日付文字列を YYYY-MM-DD に変換する。
    対応例: '2026/6/7', '6月7日', '令和8年6月7日', '2026年6月7日(土)'
    """
    text = text.strip()

    # YYYY/MM/DD or YYYY-MM-DD
    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # YYYY年MM月DD日
    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # MM月DD日（年なし → 今年または来年と判断）
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        today = date.today()
        mo, da = int(m.group(1)), int(m.group(2))
        yr = today.year
        # 過去の日付なら来年と判断
        try:
            candidate = date(yr, mo, da)
            if candidate < today:
                yr += 1
        except ValueError:
            return None
        return f"{yr}-{mo:02d}-{da:02d}"

    return None


def is_future(date_str: str) -> bool:
    """日付が今日以降かチェック"""
    try:
        return date.fromisoformat(date_str) >= date.today()
    except Exception:
        return False


def party_id(party: dict) -> str:
    """パーティーの一意IDを生成（日付＋名前のハッシュ）"""
    raw = f"{party.get('date','')}-{party.get('name','')}"
    return str(hash(raw) & 0xFFFFFFFF)


def load_known() -> set:
    """既知パーティーIDをロード"""
    p = Path(CONFIG["KNOWN_IDS_FILE"])
    if p.exists():
        return set(json.loads(p.read_text(encoding="utf-8")))
    return set()


def save_known(ids: set):
    """既知パーティーIDを保存"""
    Path(CONFIG["KNOWN_IDS_FILE"]).write_text(
        json.dumps(list(ids), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════
#  サイト別スクレイパー
# ══════════════════════════════════════════════════════════════

# ── 1. JDSF兵庫 ──────────────────────────────────────────────
def scrape_jdsf_hyogo() -> list[dict]:
    """
    https://www.jdsf-hyogo.com/
    お知らせ・イベント一覧から日程と内容を抽出する
    """
    log.info("【1】JDSF兵庫 を巡回中...")
    results = []

    soup = fetch("https://www.jdsf-hyogo.com/")
    if not soup:
        return results

    # 投稿記事を検索（WordPressベースのサイト）
    articles = soup.select("article, .post, .entry, li.news-item")
    if not articles:
        # フォールバック：aタグからパーティー関連記事を探す
        articles = soup.find_all("a", href=re.compile(r"/\d{4}/\d{2}/"))

    for article in articles[:20]:  # 最新20件
        try:
            # タイトル取得
            title_el = article.select_one("h1,h2,h3,h4,.entry-title,.post-title,a")
            title = title_el.get_text(strip=True) if title_el else ""

            # パーティー関連かチェック
            if not any(kw in title for kw in ["パーティー","party","Party","カーニバル","交流会"]):
                continue

            # 本文テキスト
            body = article.get_text(" ", strip=True)

            # 日付を探す
            date_str = normalize_date(body)
            if not date_str or not is_future(date_str):
                continue

            # リンク
            link_el = article.find("a", href=True)
            link = link_el["href"] if link_el else "https://www.jdsf-hyogo.com/"
            if link.startswith("/"):
                link = "https://www.jdsf-hyogo.com" + link

            results.append({
                "source":  "JDSF兵庫",
                "source_url": link,
                "name":    title,
                "date":    date_str,
                "venue":   "",
                "time":    "",
                "fee":     "",
                "region":  "神戸市内",
                "raw":     body[:200],
            })
            log.info(f"    検出: {title} ({date_str})")
        except Exception as e:
            log.debug(f"    記事パースエラー: {e}")

    log.info(f"  → {len(results)}件検出")
    return results


# ── 2. 兵庫県社交ダンス教師協会 ──────────────────────────────
def scrape_jbdf_hsdta() -> list[dict]:
    """
    http://www.jbdf-hsdta.jp/carnival.html
    カーニバル・パーティー情報ページを解析する
    """
    log.info("【2】兵庫県社交ダンス教師協会 を巡回中...")
    results = []

    urls = [
        "http://www.jbdf-hsdta.jp/carnival.html",
        "http://www.jbdf-hsdta.jp/schedule.html",
        "http://www.jbdf-hsdta.jp/",
    ]

    for url in urls:
        soup = fetch(url)
        if not soup:
            continue

        text = soup.get_text(" ", strip=True)

        # テーブル行から情報を抽出
        for row in soup.select("tr"):
            cells = [td.get_text(strip=True) for td in row.select("td,th")]
            if len(cells) < 2:
                continue
            row_text = " ".join(cells)

            # パーティー・カーニバル関連
            if not any(kw in row_text for kw in ["パーティー","カーニバル","party","交流","Party"]):
                continue

            date_str = normalize_date(row_text)
            if not date_str or not is_future(date_str):
                continue

            # 名前候補（日付以外の最長セル）
            name = max(cells, key=lambda c: len(c) if not re.search(r"\d{4}[年/]", c) else 0)

            results.append({
                "source":    "兵庫県社交ダンス教師協会",
                "source_url": url,
                "name":      name or "（詳細はサイトを確認）",
                "date":      date_str,
                "venue":     "",
                "time":      "",
                "fee":       "",
                "region":    "神戸市内",
                "raw":       row_text[:200],
            })
            log.info(f"    検出: {name} ({date_str})")

        if results:
            break  # 1ページで見つかれば終了

    log.info(f"  → {len(results)}件検出")
    return results


# ── 3. 乾さんのHP（三田近郊パーティー） ──────────────────────
def scrape_tatsumi() -> list[dict]:
    """
    http://tatsumi-n.private.coocan.jp/PartySch1.htm
    兵庫県のパーティー情報テーブルを解析する（Shift-JIS）
    """
    log.info("【3】乾さんのHP（三田近郊） を巡回中...")
    results = []

    soup = fetch(
        "http://tatsumi-n.private.coocan.jp/PartySch1.htm",
        encoding="shift_jis"
    )
    if not soup:
        return results

    # テーブル行を解析
    for row in soup.select("tr"):
        cells = [td.get_text(strip=True) for td in row.select("td")]
        if len(cells) < 3:
            continue

        row_text = " ".join(cells)

        # 日付が含まれる行を対象に
        date_str = normalize_date(row_text)
        if not date_str or not is_future(date_str):
            continue

        # 列の推測（典型パターン：日付|会場|時間|費用|主催|...）
        name    = cells[1] if len(cells) > 1 else ""
        venue   = cells[2] if len(cells) > 2 else ""
        time_   = cells[3] if len(cells) > 3 else ""
        fee     = cells[4] if len(cells) > 4 else ""

        if not name:
            continue

        # 地域判定
        region = "三田・北摂"
        if any(kw in row_text for kw in ["神戸","三宮","ポートピア"]):
            region = "神戸市内"
        elif any(kw in row_text for kw in ["姫路","明石","加古川","播磨"]):
            region = "播磨（姫路・明石・加古川等）"
        elif any(kw in row_text for kw in ["西宮","尼崎","芦屋"]):
            region = "阪神（西宮・尼崎・芦屋等）"

        results.append({
            "source":    "乾さんのHP（三田近郊）",
            "source_url": "http://tatsumi-n.private.coocan.jp/PartySch1.htm",
            "name":      name,
            "date":      date_str,
            "venue":     venue,
            "time":      time_,
            "fee":       fee,
            "region":    region,
            "raw":       row_text[:200],
        })
        log.info(f"    検出: {name} / {venue} ({date_str})")

    log.info(f"  → {len(results)}件検出")
    return results


# ── 4. ビデオフォーダンス（関西パーティー情報） ────────────────
def scrape_video4dance() -> list[dict]:
    """
    https://video4dance.com/DP/index.php
    関西ダンスパーティー情報から兵庫県のものを抽出する
    """
    log.info("【4】ビデオフォーダンス を巡回中...")
    results = []

    soup = fetch("https://video4dance.com/DP/index.php", encoding="utf-8")
    if not soup:
        # Shift-JISで再試行
        soup = fetch("https://video4dance.com/DP/index.php", encoding="shift_jis")
    if not soup:
        return results

    # テーブル行を解析
    for row in soup.select("tr"):
        cells = [td.get_text(strip=True) for td in row.select("td")]
        if len(cells) < 3:
            continue

        row_text = " ".join(cells)

        # 兵庫県関連かチェック
        hyogo_keywords = [
            "神戸","兵庫","三宮","ポートピア",
            "西宮","尼崎","芦屋","宝塚",
            "三田","姫路","明石","加古川","播磨",
            "丹波","但馬","淡路","豊岡",
        ]
        if not any(kw in row_text for kw in hyogo_keywords):
            continue

        date_str = normalize_date(row_text)
        if not date_str or not is_future(date_str):
            continue

        # 地域判定
        region = "神戸市内"
        if any(kw in row_text for kw in ["三田","川西","宝塚","猪名川"]):
            region = "三田・北摂"
        elif any(kw in row_text for kw in ["姫路","明石","加古川","播磨","高砂","小野","三木"]):
            region = "播磨（姫路・明石・加古川等）"
        elif any(kw in row_text for kw in ["西宮","尼崎","芦屋","伊丹","川西"]):
            region = "阪神（西宮・尼崎・芦屋等）"
        elif any(kw in row_text for kw in ["丹波","但馬","豊岡","篠山","淡路"]):
            region = "丹波・但馬・淡路"

        # 名前・会場を最長セルから推測
        name = max(cells, key=lambda c: len(c))

        results.append({
            "source":    "ビデオフォーダンス",
            "source_url": "https://video4dance.com/DP/index.php",
            "name":      name,
            "date":      date_str,
            "venue":     "",
            "time":      "",
            "fee":       "",
            "region":    region,
            "raw":       row_text[:200],
        })
        log.info(f"    検出: {name} ({date_str})")

    log.info(f"  → {len(results)}件検出")
    return results


# ══════════════════════════════════════════════════════════════
#  重複チェック・通知・保存
# ══════════════════════════════════════════════════════════════

def deduplicate(parties: list[dict]) -> list[dict]:
    """日付＋名前が同じものを除去"""
    seen = set()
    result = []
    for p in parties:
        key = f"{p['date']}-{p['name'][:20]}"
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def filter_new(parties: list[dict], known_ids: set) -> list[dict]:
    """既知でないパーティーだけを返す"""
    return [p for p in parties if party_id(p) not in known_ids]


def send_notify_email(new_parties: list[dict]):
    """
    管理者に新着パーティー通知メールを送る。
    Gmail のアプリパスワードを使用。
    """
    if not new_parties:
        return
    if not CONFIG["GMAIL_USER"] or CONFIG["GMAIL_PASS"] == "xxxx-xxxx-xxxx-xxxx":
        log.warning("Gmailの設定が未完了のため、メール通知をスキップします")
        return

    subject = f"【新着通知】社交ダンスパーティー {len(new_parties)}件を検出しました"

    lines = [
        f"自動収集スクリプトが {len(new_parties)} 件の新着パーティーを検出しました。",
        f"実行日時：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}",
        "",
        "=" * 50,
    ]
    for i, p in enumerate(new_parties, 1):
        lines += [
            f"【{i}】{p['name']}",
            f"  日付　：{p['date']}",
            f"  会場　：{p['venue'] or '（要確認）'}",
            f"  時間　：{p['time'] or '（要確認）'}",
            f"  参加費：{p['fee'] or '（要確認）'}",
            f"  地域　：{p['region']}",
            f"  情報源：{p['source']}",
            f"  URL　 ：{p['source_url']}",
            f"  本文抜粋：{p['raw'][:80]}…",
            "",
        ]
    lines += [
        "=" * 50,
        "※ 内容を確認してスプレッドシートの承認ステータスを「公開」に変更してください。",
        "※ 情報が不正確な場合は「非掲載」にしてください。",
    ]

    body = "\n".join(lines)

    try:
        msg = MIMEMultipart()
        msg["From"]    = CONFIG["GMAIL_USER"]
        msg["To"]      = CONFIG["ADMIN_EMAIL"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(CONFIG["GMAIL_USER"], CONFIG["GMAIL_PASS"])
            server.send_message(msg)
        log.info(f"通知メール送信完了 → {CONFIG['ADMIN_EMAIL']}")
    except Exception as e:
        log.error(f"メール送信失敗: {e}")


def save_results(parties: list[dict]):
    """収集結果をJSONファイルに保存"""
    output = {
        "scraped_at": datetime.now().isoformat(),
        "count":      len(parties),
        "parties":    parties,
    }
    Path(CONFIG["OUTPUT_FILE"]).write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info(f"収集結果を保存しました → {CONFIG['OUTPUT_FILE']}")


# ══════════════════════════════════════════════════════════════
#  メイン
# ══════════════════════════════════════════════════════════════

def main():
    log.info("=" * 55)
    log.info("兵庫県 社交ダンスパーティー 自動収集スクリプト")
    log.info(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    # 全サイト巡回
    all_parties = []
    scrapers = [
        scrape_jdsf_hyogo,
        scrape_jbdf_hsdta,
        scrape_tatsumi,
        scrape_video4dance,
    ]
    for scraper in scrapers:
        try:
            results = scraper()
            all_parties.extend(results)
        except Exception as e:
            log.error(f"スクレイパーエラー: {e}")
        time.sleep(1)  # サーバー負荷軽減

    log.info(f"\n合計検出数（重複含む）: {len(all_parties)}件")

    # 重複除去
    all_parties = deduplicate(all_parties)
    log.info(f"重複除去後: {len(all_parties)}件")

    # 新着のみ抽出
    known_ids = load_known()
    new_parties = filter_new(all_parties, known_ids)
    log.info(f"新着: {len(new_parties)}件")

    # 結果を保存
    save_results(all_parties)

    if new_parties:
        log.info("\n── 新着パーティー一覧 ──")
        for p in new_parties:
            log.info(f"  {p['date']} {p['name']} [{p['source']}]")

        # 管理者に通知
        send_notify_email(new_parties)

        # 既知IDを更新
        for p in new_parties:
            known_ids.add(party_id(p))
        save_known(known_ids)
    else:
        log.info("新着パーティーはありませんでした")

    log.info("\n完了！")


if __name__ == "__main__":
    main()
