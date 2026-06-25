# 后台看板系统 · 部署指南

## 推荐方案：alwaysdata.com（免费 / 100MB / 无休眠）

alwaysdata.com 是目前**唯一可用的免费 Python Flask 托管平台**：
- ✅ 免费 100MB 磁盘，无请求限制
- ✅ 支持 SSH/SFTP 上传文件
- ✅ 原生 WSGI 支持，无需额外配置
- ✅ HTTPS 自动签发
- ✅ **不会休眠**（Render 15分钟休眠，PythonAnywhere 机器人验证）

> 已尝试的不可用方案：Render（需信用卡）、PythonAnywhere（注册机器人拦截）

---

## 部署步骤（手动，约10分钟）

### 第1步：注册 alwaysdata

1. 打开 https://www.alwaysdata.com/en/register/
2. 填写邮箱、密码、姓名
3. 邮箱验证 → 登录
4. 进入管理面板 https://admin.alwaysdata.com

### 第2步：上传文件

**方法A：SFTP（推荐）**

```
服务器: ssh-alwaysdata.com
端口: 22
用户名: (在 admin → SSH 中查看)
密码: (你的账户密码)
```

上传 `dashboard/` 目录下的所有文件到远程 `/dashboard/` 目录：

```
远程目录结构：
/home/<username>/dashboard/
  ├── server.py          ← Flask 主程序
  ├── requirements.txt   ← 依赖清单
  ├── submissions.db     ← SQLite 数据库（初始为空）
  └── templates/
      └── dashboard.html ← 看板模板
```

**方法B：用 WinSCP/FileZilla 上传**

- 主机名: `ssh-alwaysdata.com`
- 协议: SFTP
- 将本地 `dashboard/` 文件夹内容拖到远程

### 第3步：创建虚拟环境 + 安装依赖

SSH 登录后执行：

```bash
ssh <username>@ssh-alwaysdata.com
cd ~/dashboard
python3.12 -m venv env
env/bin/pip install flask
```

### 第4步：创建网站

1. 在 admin.alwaysdata.com → **Web** → **Sites** → **Add a site**
2. 填写配置：

| 字段 | 值 |
|------|-----|
| **Name** | `dashboard` |
| **Addresses** | 使用默认分配的域名 `username.alwaysdata.net`，或添加自定义域名 |
| **Type** | **WSGI** |
| **Python version** | 3.12 |
| **Working directory** | `/home/<username>/dashboard` |
| **Virtualenv directory** | `/home/<username>/dashboard/env` |
| **Application path** | `server:application` |
| **Trim path** | ✅ 勾选 |

3. 点击 **Create**

⚠️ 重要：`Application path` 填 `server:application`（`server.py` 中的 `application` 变量）

### 第5步：验证部署

访问看板：
```
https://<username>.alwaysdata.net/?auth=admin888
```

API 健康检查：
```
https://<username>.alwaysdata.net/api/health
```

---

## 配置计算器前端

部署成功后，修改 `index.html` 中的 API 地址：

```javascript
// 第 3311 行附近
const DASHBOARD_API = 'https://<username>.alwaysdata.net/api/collect';
```

修改后 push 到 GitHub，GitHub Actions 会自动部署到 Pages。

---

## 常见问题排查

### 500 Internal Server Error
SSH 登录后手动测试：
```bash
cd ~/dashboard
env/bin/python -c "from server import app; print('OK')"
```
查看错误日志：admin → Sites → 点击 dashboard → Logs

### 数据库权限错误
```bash
chmod 666 ~/dashboard/submissions.db
```

### 模板找不到
确认 `templates/` 目录在上传时没有遗漏：
```bash
ls ~/dashboard/templates/
# 应该看到 dashboard.html
```

### 修改看板密码
编辑远程 `server.py`:
```bash
nano ~/dashboard/server.py
# 搜索 DASHBOARD_PASSWORD 修改
```

---

## 安全建议

1. **修改默认密码**：上线后立即改 `server.py` 中的 `DASHBOARD_PASSWORD`
2. **HTTPS**：alwaysdata 自动提供，无需额外配置
3. **数据库备份**：定期备份 `submissions.db`
4. **日志监控**：关注是否有异常请求
