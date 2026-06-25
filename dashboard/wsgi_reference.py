"""
PythonAnywhere WSGI 配置文件 (参考)
===================================
将此内容粘贴到 PythonAnywhere Web 面板的 WSGI configuration file 中。
路径: /var/www/<username>_pythonanywhere_com_wsgi.py

使用前替换所有 <username> 为你的 PythonAnywhere 用户名。
"""

import sys

# ============================================================
# 1. 添加项目路径
# ============================================================
project_home = '/home/<username>/dashboard'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# ============================================================
# 2. 导入 Flask 应用
# ============================================================
from server import application  # noqa: E402, F401
