# HK Racing Quant — 香港賽馬量化分析系統

> 通過反向工程馬會賠率，計算每匹馬的「真實勝率」，自動識別 +EV 價值投注

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
rm -rf node_modules package-lock.json   # clean if needed
npm install
npm run dev
```
打开 http://localhost:3000

## 架构

```
Frontend (React + Tailwind + Recharts)
  ├─ Panel A: 赛事 Dashboard (排位表/步速预报)
  ├─ Panel B: 量化模型计算机 (P_true vs P_market 对比图)
  └─ Panel C: +EV 讯号发射器 (价值投注卡片/聪明钱警报)
         │
         ▼
Backend (FastAPI)
  ├─ /api/racing/*     — 赛事查询 + 量化分析
  ├─ /api/import/*     — CSV 数据导入
  └─ quant_engine.py   — 核心量化引擎
         │
         ▼
Data Layer
  ├─ HKJC GraphQL API  — 即时赔率/排位表 (已打通!)
  ├─ HTML 解析器        — 历史赛果
  └─ PostgreSQL + Redis — 持久化 + 赔率缓存
```

## 量化模型

### P_true (真实胜率)
Softmax 加权评分法，特征权重可调：
- 档位优势 / 骑师胜率 / 练马师胜率
- 近况 (last6run) / 负磅 / 步速适配 / 擅水 / 路程适配

### P_market (市场概率)
`P_market = (1/Odds) / (1 - Takeout)` — Takeout = 17.5%

### +EV 筛选 (三重验证)
1. EV > 5% → `P_true × (Odds - 1) - (1 - P_true) > 0.05`
2. Edge > 10% → `P_true - P_market > 0.10`
3. P_true > 4% → 排除冷门噪音

### Kelly 准则
采用 1/3 Kelly：`f = [(P × (O-1) - (1-P)) / (O-1)] × 1/3`

## 已验证的数据管道

| 管道 | 状态 | 数据类型 |
|------|------|----------|
| HKJC GraphQL (`info.cld.hkjc.com/graphql/base/`) | ✅ 已打通 | 排位表/即时赔率/彩池 |
| HTML 赛果解析 (`racing.hkjc.com`) | ✅ 已打通 | 历史赛果 |
| CSV 导入 | ✅ API 已建 | 批量历史数据 |

GraphQL query 来源: [hkjc-api npm package](https://github.com/Bobosky2005/hkjc-api)
