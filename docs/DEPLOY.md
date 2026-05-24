# HK Racing Quant — 部署指南

## 架構

```
Vercel (前端 React)  ──→  Render (後端 FastAPI)  ──→  HKJC GraphQL API
   ↑                          ↑
   └── cron 每14分鐘 ping ────┘  (保持 Render 不休眠)
```

## 一、Render 部署（後端）

### 1. 建立 GitHub Repo
把整個 `hk-racing-quant` 推到你的 GitHub。

### 2. Render Dashboard 建立 Web Service
- New → Web Service → Connect GitHub repo
- **Root Directory**: `backend`
- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements-render.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Plan**: Free

### 3. 設定環境變數
在 Render Dashboard → Environment：
| Key | Value |
|-----|-------|
| `ENABLE_DB_ROUTES` | `false` |
| `CORS_ORIGINS` | `https://你的vercel域名.vercel.app,http://localhost:3000` |

### 4. 部署完成後記下 URL
例如：`https://hk-racing-quant-api.onrender.com`

驗證：`curl https://hk-racing-quant-api.onrender.com/health`
應返回 `{"status":"healthy","mode":"live-only"}`

---

## 二、Vercel 部署（前端）

### 1. Vercel Dashboard 建立 Project
- New Project → Import Git Repository → 選你的 repo
- **Root Directory**: `frontend`
- **Framework Preset**: Vite
- **Build Command**: `npm run build`
- **Output Directory**: `dist`

### 2. 設定環境變數
在 Vercel Dashboard → Settings → Environment Variables：
| Key | Value |
|-----|-------|
| `VITE_API_BASE` | `https://hk-racing-quant-api.onrender.com/api` |

### 3. 部署
Vercel 會自動 build 並部署。完成後得到 URL，例如：
`https://hk-racing-quant.vercel.app`

### 4. 更新 Render 的 CORS
回到 Render Dashboard → Environment，把 `CORS_ORIGINS` 加上 Vercel URL：
```
https://hk-racing-quant.vercel.app,http://localhost:3000
```

---

## 三、喚醒機制

Render 免費 tier 15 分鐘無流量會休眠，重新啟動需 ~30 秒。

**自動喚醒**：

> ⚠️ **Vercel 免費版不支援 Cron Jobs**（需 Pro 計劃）。請用以下替代方案：

### 方案 A：cron-job.org（推薦，免費）
1. 註冊 https://cron-job.org
2. 建立新任務：
   - URL: `https://你的render域名.onrender.com/health`
   - Schedule: 每 14 分鐘
   - HTTP Method: GET

### 方案 B：UptimeRobot（免費）
1. 註冊 https://uptimerobot.com
2. 建立新 monitor：
   - Monitor Type: HTTP(s)
   - URL: `https://你的render域名.onrender.com/health`
   - Monitoring Interval: 5 分鐘

### 方案 C：Vercel Pro
如果你有 Vercel Pro，`frontend/vercel.json` 已配置好 cron：
```json
{
  "crons": [{
    "path": "/api/ping",
    "schedule": "*/14 * * * *"
  }]
}
```

`frontend/api/ping.js` 是 Vercel Serverless Function，負責打 Render health endpoint。

---

## 四、本地開發

```bash
# 後端
cd backend
pip install -r requirements-render.txt
uvicorn app.main:app --port 8000

# 前端
cd frontend
npm install
npm run dev  # 自動 proxy /api → localhost:8000
```

---

## 五、文件結構

```
hk-racing-quant/
├── backend/
│   ├── app/
│   │   ├── __init__.py          # 空，不導入 DB 依賴
│   │   ├── main.py              # FastAPI 入口（支援 live-only 模式）
│   │   ├── database.py          # 懶加載 DB，無 DB 時不崩潰
│   │   ├── routers/
│   │   │   ├── __init__.py      # 空，不強制導入
│   │   │   ├── live.py          # /api/live/* — 即時數據（不需 DB）
│   │   │   ├── racing.py        # /api/v1/* — 需 DB
│   │   │   └── import_data.py   # /api/v1/import/* — 需 DB
│   │   ├── services/
│   │   │   ├── quant_engine.py  # 量化引擎
│   │   │   └── signal_detector.py  # 暗號偵測
│   │   ├── scraper/
│   │   │   └── hkjc_fetcher.py  # HKJC GraphQL 客戶端
│   │   └── models/
│   │       └── schema.py        # ORM 表定義（僅 DB 模式使用）
│   ├── requirements-render.txt  # Render 輕量依賴
│   ├── requirements.txt         # 完整依賴（含 DB/ML）
│   └── build.sh
├── frontend/
│   ├── api/
│   │   └── ping.js              # Vercel Serverless Function（喚醒 Render）
│   ├── src/
│   │   ├── utils/
│   │   │   └── api.ts           # API_BASE 支援環境變數
│   │   └── components/
│   │       └── ValueBetSignals.tsx
│   ├── vercel.json              # SPA rewrite + cron 設定
│   └── .env.example
├── render.yaml                  # Render Blueprint
└── .gitignore
```
