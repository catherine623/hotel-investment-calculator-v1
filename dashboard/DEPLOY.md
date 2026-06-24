# 后台看板系统 - 部署指南

## 架构

```
用户浏览器(catherine623.github.io) → POST → Flask API(公开服务器)
                                              ↓ SQLite
管理员浏览器 → GET /?auth=密码 → 看板页面(Flask渲染)
```

## 方案一：Render.com 免费部署（推荐）

### 1. 创建 Render 账号
访问 https://render.com/ → Sign up with GitHub

### 2. 创建 Web Service
- 点击 "New +" → "Web Service"
- 连接 GitHub 仓库 `catherine623/hotel-investment-calculator-v1`
- 配置:
  - **Root Directory**: `dashboard`
  - **Runtime**: Python 3
  - **Build Command**: `pip install -r requirements.txt`
  - **Start Command**: `python server.py`
  - **Plan**: Free
- 点击 "Create Web Service"

### 3. 获取公开地址
部署完成后，Render 会分配一个地址如:
`https://hotel-dashboard.onrender.com`

### 4. 配置计算器
修改 `index.html` 中第 3311 行的:
```javascript
const DASHBOARD_API = 'https://hotel-dashboard.onrender.com/api/collect';
```

### 5. 访问看板
`https://hotel-dashboard.onrender.com/?auth=admin888`

### 注意事项
- Free plan 首次访问有 30-50 秒冷启动
- 每月 750 小时免费额度
- 15 分钟无请求后自动休眠


## 方案二：PythonAnywhere 免费部署

### 1. 创建账号
https://www.pythonanywhere.com/ → Create a Beginner account

### 2. 上传文件
- Web → Add a new web app → Flask → Python 3.10+
- Upload `server.py`, `requirements.txt` 和 `templates/` 目录
- 路径设为 `/home/<username>/dashboard/`

### 3. 配置 WSGI
编辑 WSGI 文件:
```python
import sys
sys.path.insert(0, '/home/<username>/dashboard')
from server import app as application
```

### 4. 获取地址
`https://<username>.pythonanywhere.com`


## 方案三：本地运行（仅开发测试）

### Windows
双击 `dashboard/start.bat`

### 手动启动
```bash
cd dashboard
pip install flask
python server.py
```

访问: http://localhost:5099/?auth=admin888


## 安全配置

### 修改密码
```bash
# 方式1: 环境变量
set DASHBOARD_PASSWORD=你的密码
python server.py

# 方式2: 直接修改 server.py 第35行
DASHBOARD_PASSWORD = "你的密码"
```

### 生产环境（可选）
```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5099 server:app
```
