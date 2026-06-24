# 后台看板系统 - 完成概览

## 已完成

### 1. Flask 后端 API (`dashboard/server.py`)
- **POST /api/collect** - 接收计算器提交数据，自动清洗后存入 SQLite
- **GET /api/dashboard** - 看板聚合数据（含城市排行、趋势、分布等 10+ 维度）
- **GET /api/submissions** - 原始提交列表（分页，需密码）
- **GET /** - 看板前端页面（密码保护）
- **数据清洗引擎**: 范围校验、IQR异常检测、城市名标准化、逻辑一致性检查

### 2. 看板前端 (`dashboard/templates/dashboard.html`)
- 概览卡片：总提交数、独立用户、平均GOP率/ADR/投资额
- 判词分布：✅可行 / 🔶有挑战 / 🔴压力大 / ⚠不可行
- 时间趋势图：提交数 + 平均回本年限（双轴）
- 酒店模式饼图 / 城市排行条形图
- 城市等级分析（提交数 + GOP率对比）
- ADR房价区间 × GOP率 / 回本年限分布
- 房间数 vs 投资额散点图（气泡大小=回本，颜色=GOP率）
- 最近提交实时表格
- 模式筛选 + 时间范围选择 + 60秒自动刷新

### 3. 计算器集成 (`index.html`)
- `generateReport()` 末尾自动调用 `collectToDashboard()` 发送数据
- 静默发送，不阻塞用户体验
- 需配置实际后端地址后生效

### 4. 部署方案 (`dashboard/DEPLOY.md`)
- Render.com 免费部署（推荐）
- PythonAnywhere 免费部署
- 本地运行（start.bat 一键启动）

## 下一步操作

部署到 Render.com（免费，5分钟）:

1. 打开 https://render.com → Sign up with GitHub
2. New + → Web Service → 连接 `catherine623/hotel-investment-calculator-v1` 仓库
3. Root Directory: `dashboard` → Start Command: `python server.py`
4. 获得地址后，修改 `index.html` 中的 `DASHBOARD_API` 常量
5. 推送到 GitHub → 计算器数据自动流入看板
