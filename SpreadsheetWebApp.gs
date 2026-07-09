/**
 * =====================================================================
 *  兵庫県社交ダンス情報 - スプレッドシート書き込みWebApp
 *  GAS（Google Apps Script）版
 *
 *  【設置手順】
 *  1. スプレッドシートのメニュー「拡張機能」→「Apps Script」
 *  2. このコードを貼り付けて保存（Ctrl+S）
 *  3. 「デプロイ」→「新しいデプロイ」
 *  4. 種類：「ウェブアプリ」
 *     実行ユーザー：「自分」
 *     アクセスできるユーザー：「全員」
 *  5. 「デプロイ」→ 表示されたURLをコピー
 *  6. GitHub Secret「GAS_WEBHOOK_URL」にそのURLを登録
 * =====================================================================
 */

// ── 設定 ──────────────────────────────────────────────────────────
const SHEET_NAME = "📋 回答データ"; // 書き込み先シートのタブ名
const SECRET_KEY = "hyogo-dance-2026"; // 不正アクセス防止用の合言葉
                                        // GitHub Secret「GAS_SECRET」にも同じ値を登録

// ── POSTリクエストを受け取る関数（メイン） ─────────────────────────
function doPost(e) {
  try {
    // リクエストボディをJSONとして解析
    const payload = JSON.parse(e.postData.contents);

    // 合言葉チェック（簡易セキュリティ）
    if (payload.secret !== SECRET_KEY) {
      return response({ status: "error", message: "Unauthorized" }, 403);
    }

    const parties = payload.parties;
    if (!parties || parties.length === 0) {
      return response({ status: "ok", message: "No data", count: 0 });
    }

    // スプレッドシートに書き込み
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let ws;
    try {
      ws = ss.getSheetByName(SHEET_NAME);
      if (!ws) ws = ss.getSheets()[0]; // シートが見つからない場合は最初のシート
    } catch (err) {
      ws = ss.getSheets()[0];
    }

    const now = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy/MM/dd HH:mm");

    const rows = parties.map(p => [
      now,                                          // A: タイムスタンプ
      "",                                           // B: 掲載ID（管理者が入力）
      "審査中",                                     // C: 承認ステータス
      "",                                           // D: 承認日
      `自動収集:${p.source || ""}`,                 // E: 管理者メモ
      p.name    || "",                              // F: パーティー名
      p.date    || "",                              // G: 開催日
      p.time    || "",                              // H: 開催時間
      p.region  || "",                              // I: 開催地域
      p.venue   || "",                              // J: 会場名
      "",                                           // K: 会場住所
      p.fee > 0 ? String(p.fee) : "",              // L: 参加費
      "",                                           // M: 参加費補足
      "",                                           // N: リボン情報
      "",                                           // O: 予約方法
      "",                                           // P: 主催サークル名
      p.contact || "",                              // Q: 問い合わせ先
      "",                                           // R: 投稿者メール
      p.pr      || "",                              // S: PR文
      p.source_url || "",                           // T: URL
    ]);

    ws.getRange(ws.getLastRow() + 1, 1, rows.length, rows[0].length)
      .setValues(rows);

    console.log(`✅ ${rows.length}件追記完了`);
    return response({ status: "ok", message: "Success", count: rows.length });

  } catch (err) {
    console.error("エラー:", err.toString());
    return response({ status: "error", message: err.toString() }, 500);
  }
}

// ── GETリクエスト（動作確認用） ────────────────────────────────────
function doGet(e) {
  return response({ status: "ok", message: "WebApp is running!" });
}

// ── レスポンス生成ヘルパー ─────────────────────────────────────────
function response(data, code) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
