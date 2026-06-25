# 后台看板系统 · 部署指南

## 推荐方案：PythonAnywhere（免费 / Flask 原生支持）

PythonAnywhere 是目前**对 Flask 最友好的免费托管平台**：
- ✅ 免费套餐：1 个 Web App + 512MB 磁盘
- ✅ 原生 WSGI 支持，Flask 开箱即用
- ✅ 在线文件管理器 + Web 控制台（无需 SSH）
- ✅ HTTPS 自动提供
- ✅ Python 3.10/3.11/3.12/3.13 可选

> 已尝试的不可用方案：Render（需信用卡）、CloudStudio（仅支持静态站点）

---

## 第1步：注册 PythonAnywhere

1. 打开 https://www.pythonanywhere.com/registration/register/beginner/
2. 填写用户名、邮箱、密码
3. 邮箱验证 → 登录
4. 进入 Dashboard：https://www.pythonanywhere.com/user/<username>/

> ⚠️ 如果注册遇到机器人验证失败，换个浏览器/网络试试，或用 alwaysdata.com 备选方案。

---

## 第2步：上传项目文件

### 方法A：Web 界面上传（最简单）

1. 进入 **Files** 标签页
2. 在 `/home/<username>/` 下创建 `dashboard` 目录
3. 点击 `dashboard/` 进入，用 **Upload a file** 按钮上传以下文件：

```
/home/<username>/dashboard/
  ├── server.py          ← Flask 主程序
  ├── requirements.txt   ← 依赖清单
  ├── submissions.db     ← SQLite 数据库（初始可为空文件）
  └── templates/
      └── dashboard.html ← 看板 HTML 模板
```

4. 在 `dashboard/` 下创建子目录 `templates/`，进入后上传 `dashboard.html`

### 方法B：Git 克隆（推荐，如果你已有 GitHub 仓库）

在 **Consoles** 标签页打开一个 Bash console，执行：

```bash
cd ~
git clone https://github.com/catherine623/hotel-investment-calculator-v1.git
mv hotel-investment-calculator-v1/dashboard ~/dashboard
# 可选：清理多余文件
rm -rf hotel-investment-calculator-v1
```

---

## 第3步：创建虚拟环境 + 安装依赖

打开 **Consoles** → **Bash**，执行：

```bash
cd ~/dashboard
mkvirtualenv --python=/usr/bin/python3.13 dashboard-env
pip install flask
```

如果 Python 3.13 不可用，改用 3.12：

```bash
mkvirtualenv --python=/usr/bin/python3.12 dashboard-env
pip install flask
```

---

## 第4步：配置 Web App

1. 进入 **Web** 标签页 → **Add a new web app**
2. 选择 **Manual configuration**（不要选 Flask 快捷方式）
3. 选择 Python 版本：**Python 3.13**（或 3.12）

### 配置 Virtualenv

在 Web 页面 **Virtualenv** 部分，填入：
```
/home/<username>/dashboard-env
```

### 配置 WSGI 文件

点击 **WSGI configuration file** 链接，将内容替换为：

```python
import sys

project_home = '/home/<username>/dashboard'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from server import application
```

> ⚠️ 把 `<username>` 替换成你的实际用户名！

### 配置 Static Files（可选）

在 **Static files** 部分，无需额外配置（看板使用 Chart.js CDN，无本地静态资源）。

---

## 第5步：启动并验证

1. 回到 **Web** 标签页，点击绿色 **Reload** 按钮
2. 访问看板：
```
https://<username>.pythonanywhere.com/?auth=admin888
```

3. API 健康检查：
```
https://<username>.pythonanywhere.com/api/health
```
应该返回：`{"status":"ok","time":"..."}`

4. 测试数据收集：
```bash
curl -X POST https://<username>.pythonanywhere.com/api/collect \
  -H "Content-Type: application/json" \
  -d '{"city":"北京","rooms":100,"adr":400,"occupancy":80,"test":true}'
```

---

## 配置计算器前端

部署成功后，修改 `index.html` 中的 API 地址：

```javascript
// 约第 3311 行
const DASHBOARD_API = 'https://<username>.pythonanywhere.com/api/collect';
```

修改后 push 到 GitHub，GitHub Actions 自动部署到 Pages。

---

## 常见问题排查

### "Something went wrong" 错误页

在 **Web** 标签页查看 **Error log**，或在 Bash console 中手动测试：

```bash
cd ~/dashboard
workon dashboard-env
python -c "from server import application; print('OK')"
```

### 数据库权限错误

```bash
chmod 666 ~/dashboard/submissions.db
```

### 模板找不到

确认文件结构正确：
```bash
ls ~/dashboard/
ls ~/dashboard/templates/
```

### 修改看板密码

编辑 `server.py`:
```bash
nano ~/dashboard/server.py
# 搜索 DASHBOARD_PASSWORD 修改后保存
```
修改后点击 Web 页面的 **Reload** 按钮。

### 免费套餐限制

- 每 24 小时重置磁盘配额（512MB）
- 无外部网络访问（不能调外部 API）
- 每日处理能力有限（看板使用完全足够）

---

## 备选方案：alwaysdata.com

如果 PythonAnywhere 注册遇到问题，可用 alwaysdata.com：
- 免费 100MB，支持 SSH/SFTP
- 参考 `wsgi_reference.py` 中的配置方式
- Web 面板 → Sites → Add → Type: WSGI → Application path: `server:application`
