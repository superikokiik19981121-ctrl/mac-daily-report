# マクドナルド日次レポート

マクドナルドに関するニュース・YouTube・競合情報を毎日自動収集し、Groq AI（LLaMA 3.3）で要約・分析する日次インテリジェンスダッシュボード。

## 機能

- **多ソース収集**：Google News / YouTube Data API / 国立国会図書館 API / Nitter（@McDonaldsJapan）
- **AI 日次サマリー**：Groq LLaMA 3.3 が毎日200〜300文字で要約を自動生成
- **競合4社分析**：モスバーガー・バーガーキング・KFC・ロッテリアを企業別に表示
- **書籍情報**：マクドナルド関連書籍を自動収集
- **GitHub Actions**：毎朝 6:00 JST に自動更新
- **McDonald's デザイン**：ゴールデンアーチロゴ・赤×黄色のブランドカラー

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| バックエンド | Python 3.12 / FastAPI / SQLite |
| AI 分析 | Groq API（llama-3.3-70b-versatile） |
| データ収集 | YouTube Data API v3 / Google News RSS / NDL API |
| フロントエンド | Jinja2 テンプレート / Vanilla JS |
| 自動化 | GitHub Actions（毎朝 6:00 JST） |

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # APIキーを設定
python main.py serve
```

ブラウザで http://127.0.0.1:8000/ を開く。

## 環境変数

| 変数 | 説明 |
|---|---|
| `GROQ_API_KEY` | Groq API キー（AI 分析） |
| `YOUTUBE_API_KEY` | YouTube Data API v3 キー |
| `CRON_SECRET` | `/trigger` エンドポイント認証用 |

## CLI コマンド

```powershell
# 特定日を収集
python main.py collect --date 2026-05-31

# 期間まとめて収集
python main.py backfill --from 2026-05-25 --to 2026-05-31

# 日次更新（昨日の全データ収集 + AI 分析）
python main.py daily-update

# サーバー起動
python main.py serve --port 8000
```
