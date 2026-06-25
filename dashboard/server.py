#!/usr/bin/env python3
"""
酒店投资计算器 - 后台看板系统
=============================
数据收集 → 清洗 → 存储 → 可视化分析

Flask 后端服务:
  POST /api/collect   - 收集计算器提交数据
  GET  /api/dashboard  - 获取看板聚合数据
  GET  /api/submissions - 获取原始提交列表（分页）
  GET  /                - 看板前端页面

部署: python server.py (默认端口 5099)
"""

import os
import json
import sqlite3
import uuid
import re
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from contextlib import contextmanager
from functools import wraps

from flask import Flask, request, jsonify, render_template_string, g, abort

# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "submissions.db")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "admin888")

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# ---- CORS 支持（允许 GitHub Pages / 任意来源） ----
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response

@app.route('/api/collect', methods=['OPTIONS'])
@app.route('/api/dashboard', methods=['OPTIONS'])
@app.route('/api/submissions', methods=['OPTIONS'])
def handle_options():
    return '', 204

# ============================================================
# 数据库
# ============================================================
@contextmanager
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                
                -- 用户标识
                ip_hash TEXT,
                user_agent TEXT,
                referrer TEXT,
                
                -- 输入参数
                city_tier INTEGER,
                city TEXT,
                district TEXT,
                investment REAL,      -- 万元
                rooms INTEGER,
                annual_rent REAL,     -- 万元
                adr REAL,             -- 元
                occupancy REAL,       -- %
                non_room_pct REAL,    -- %
                hotel_mode TEXT,      -- standard|resort|esports
                invest_mode TEXT,     -- detail|direct
                admin_fee_rate REAL,  -- null = 使用默认
                
                -- 计算结果
                annual_revenue REAL,  -- 万元
                annual_cost REAL,     -- 万元
                gop REAL,            -- 万元
                gop_ratio REAL,      -- %
                cash_flow REAL,      -- 万元
                payback_years REAL,
                staff_count INTEGER,
                cost_ratio REAL,     -- %
                
                -- 判断
                poi_matched INTEGER DEFAULT 1,
                verdict TEXT,        -- feasible|challenging|difficult|impossible
                
                -- 数据质量标记
                is_suspicious INTEGER DEFAULT 0,
                clean_note TEXT
            )
        """)
        
        # 清洗缓存表
        db.execute("""
            CREATE TABLE IF NOT EXISTS clean_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_raw INTEGER DEFAULT 0,
                total_clean INTEGER DEFAULT 0,
                last_clean_at TEXT,
                outlier_thresholds TEXT
            )
        """)
        db.execute("INSERT OR IGNORE INTO clean_stats (id) VALUES (1)")
        
        # 索引
        db.execute("CREATE INDEX IF NOT EXISTS idx_created ON submissions(created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_city ON submissions(city)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_tier ON submissions(city_tier)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_verdict ON submissions(verdict)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_mode ON submissions(hotel_mode)")
        db.commit()
    print(f"✅ 数据库初始化完成: {DB_PATH}")

# ============================================================
# 数据清洗引擎
# ============================================================
class DataCleaner:
    """酒店投资数据清洗器"""
    
    # 合理范围阈值（剔除特别大/特别小的异常值）
    THRESHOLDS = {
        'rooms':         (10, 2000),       # 房间数
        'investment':    (80, 30000),       # 投资额(万元) — 剔除<80万和>3亿的极端值
        'annual_rent':   (0, 5000),         # 年租金(万元) — 剔除>5000万的极端值
        'adr':           (50, 5000),        # ADR(元)
        'occupancy':     (30, 100),         # 入住率(%)
        'non_room_pct':  (0, 60),           # 非客房收入占比(%)
        'gop_ratio':     (-20, 80),         # GOP率(%)
        'payback_years': (0.5, 100),        # 回本年限
        'annual_revenue':(5, 50000),        # 年营收(万元)
        'staff_count':   (1, 500),          # 员工数
    }
    
    # 关键字段：超出阈值直接标记为可疑（对应剔除逻辑）
    CRITICAL_FIELDS = {'investment', 'rooms', 'annual_revenue', 'payback_years'}
    
    # 城市名称标准化映射
    CITY_NORMALIZE = {
        'beijing': '北京', '北京': '北京', '北京市': '北京',
        'shanghai': '上海', '上海': '上海', '上海市': '上海',
        'guangzhou': '广州', '广州': '广州', '广州市': '广州',
        'shenzhen': '深圳', '深圳': '深圳', '深圳市': '深圳',
        'chengdu': '成都', '成都': '成都', '成都市': '成都',
        'hangzhou': '杭州', '杭州': '杭州', '杭州市': '杭州',
        'wuhan': '武汉', '武汉': '武汉', '武汉市': '武汉',
        'nanjing': '南京', '南京': '南京', '南京市': '南京',
        'chongqing': '重庆', '重庆': '重庆', '重庆市': '重庆',
        'suzhou': '苏州', '苏州': '苏州', '苏州市': '苏州',
        'xian': '西安', '西安': '西安', '西安市': '西安',
        'changsha': '长沙', '长沙': '长沙', '长沙市': '长沙',
    }
    
    @classmethod
    def clean(cls, data: dict) -> dict:
        """清洗单条数据，返回清洗后的数据 + 标记"""
        flags = []
        cleaned = dict(data)
        
        # 1. 城市名称标准化
        raw_city = data.get('city', '').strip()
        cleaned['city'] = cls.CITY_NORMALIZE.get(raw_city, raw_city)
        if cleaned['city'] != raw_city and raw_city:
            flags.append(f'city_normalized:{raw_city}->{cleaned["city"]}')
        
        # 2. 数值范围检查
        for field, (lo, hi) in cls.THRESHOLDS.items():
            val = data.get(field)
            if val is None:
                continue
            try:
                val = float(val)
            except (ValueError, TypeError):
                flags.append(f'{field}_invalid:{val}')
                cleaned[field] = None
                continue
            
            if val < lo:
                flags.append(f'{field}_low:{val}<{lo}')
                cleaned[field] = lo  # clamp to min
            elif val > hi:
                flags.append(f'{field}_high:{val}>{hi}')
                cleaned[field] = hi  # clamp to max
            else:
                cleaned[field] = val
        
        # 3. 逻辑一致性检查
        # 投资额 vs 房间数: 单房投资应在5-60万之间（剔除极端值）
        if cleaned.get('rooms') and cleaned.get('investment'):
            per_room = cleaned['investment'] / cleaned['rooms']
            if per_room < 5 or per_room > 60:
                flags.append(f'per_room_suspicious:{per_room:.1f}万/间')
        
        # ADR vs 入住率: 高入住率+低ADR可疑
        if cleaned.get('occupancy') and cleaned.get('adr'):
            if cleaned['occupancy'] > 90 and cleaned['adr'] < 150:
                flags.append('high_occ_low_adr')
        
        # 年营收合理性: 营收 = ADR × 间夜数 × 入住率
        if all(k in cleaned for k in ['adr', 'rooms', 'occupancy']):
            if cleaned['adr'] and cleaned['rooms'] and cleaned['occupancy']:
                expected = cleaned['adr'] * cleaned['rooms'] * 365 * (cleaned['occupancy']/100) / 10000
                actual = cleaned.get('annual_revenue', 0) or 0
                if actual > 0 and abs(expected - actual) / expected > 0.3:
                    flags.append(f'revenue_mismatch:expected~{expected:.1f},actual={actual:.1f}')
        
        # 4. 设置标记
        # 任一关键字段超阈值 → 标记为可疑
        has_critical_flag = any(
            any(keyword in f for keyword in [f'{cf}_low', f'{cf}_high', f'{cf}_invalid'])
            for cf in cls.CRITICAL_FIELDS
            for f in flags
        )
        cleaned['is_suspicious'] = 1 if (has_critical_flag or len(flags) >= 2 or any('suspicious' in f for f in flags)) else 0
        cleaned['clean_note'] = '; '.join(flags) if flags else None
        
        return cleaned
    
    @classmethod
    def detect_outliers(cls, values: list) -> tuple:
        """IQR异常检测，返回 (lower_bound, upper_bound, outliers)"""
        if len(values) < 4:
            return None, None, []
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[3 * n // 4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = [v for v in values if v < lower or v > upper]
        return lower, upper, outliers

# ============================================================
# API 路由
# ============================================================

@app.route('/api/collect', methods=['POST'])
def collect():
    """
    接收计算器提交数据
    请求体: JSON, 包含所有输入参数和计算结果
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400
    
    # ---- 数据清洗 ----
    cleaner = DataCleaner()
    cleaned = cleaner.clean(data)
    
    # ---- 保存到数据库 ----
    submission_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()
    
    # 匿名化IP
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
    ip_hash = hashlib.sha256(f"salt_dcf_2024_{ip}".encode()).hexdigest()[:16]
    
    # 生成判词
    pb = cleaned.get('payback_years')
    gop = cleaned.get('gop_ratio', 0)
    if pb is None or pb >= 100:
        verdict = 'impossible'
    elif pb <= 4 and gop >= 50:
        verdict = 'feasible'
    elif pb <= 8:
        verdict = 'challenging'
    else:
        verdict = 'difficult'
    
    with get_db() as db:
        db.execute("""
            INSERT INTO submissions (
                id, created_at, ip_hash, user_agent, referrer,
                city_tier, city, district, investment, rooms, annual_rent,
                adr, occupancy, non_room_pct, hotel_mode, invest_mode, admin_fee_rate,
                annual_revenue, annual_cost, gop, gop_ratio,
                cash_flow, payback_years, staff_count, cost_ratio,
                poi_matched, verdict, is_suspicious, clean_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            submission_id, now, ip_hash,
            request.headers.get('User-Agent', '')[:500],
            request.headers.get('Referer', '')[:500],
            cleaned.get('city_tier'), cleaned.get('city'), cleaned.get('district'),
            cleaned.get('investment'), cleaned.get('rooms'), cleaned.get('annual_rent'),
            cleaned.get('adr'), cleaned.get('occupancy'), cleaned.get('non_room_pct'),
            cleaned.get('hotel_mode', 'standard'), cleaned.get('invest_mode', 'detail'),
            cleaned.get('admin_fee_rate'),
            cleaned.get('annual_revenue'), cleaned.get('annual_cost'),
            cleaned.get('gop'), cleaned.get('gop_ratio'),
            cleaned.get('cash_flow'), cleaned.get('payback_years'),
            cleaned.get('staff_count'), cleaned.get('cost_ratio'),
            cleaned.get('poi_matched', 1), verdict,
            cleaned.get('is_suspicious', 0), cleaned.get('clean_note')
        ))
        
        # 更新统计
        db.execute("UPDATE clean_stats SET total_raw = total_raw + 1, total_clean = total_clean + 1, last_clean_at = ? WHERE id = 1", (now,))
        db.commit()
    
    return jsonify({
        'status': 'ok',
        'id': submission_id,
        'verdict': verdict,
        'cleaned': cleaned.get('is_suspicious', 0) == 0
    }), 201

@app.route('/api/dashboard', methods=['GET'])
def dashboard_data():
    """获取看板聚合数据"""
    days = request.args.get('days', 30, type=int)
    mode = request.args.get('mode', 'all')  # all|standard|resort|esports
    
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    with get_db() as db:
        # 基础计数
        mode_clause = "" if mode == 'all' else "AND hotel_mode = ?"
        mode_params = () if mode == 'all' else (mode,)
        
        total = db.execute(
            f"SELECT COUNT(*) as c, COUNT(DISTINCT ip_hash) as u FROM submissions WHERE created_at >= ? {mode_clause}",
            (since, *mode_params)
        ).fetchone()
        
        clean_count = db.execute(
            f"SELECT COUNT(*) FROM submissions WHERE created_at >= ? AND is_suspicious = 0 {mode_clause}",
            (since, *mode_params)
        ).fetchone()[0]
        
        # ---- 汇总统计 ----
        stats = db.execute(f"""
            SELECT 
                AVG(adr) as avg_adr, AVG(occupancy) as avg_occ,
                AVG(gop_ratio) as avg_gop, AVG(payback_years) as avg_pb,
                AVG(rooms) as avg_rooms, AVG(investment) as avg_invest,
                AVG(annual_revenue) as avg_rev,
                COUNT(CASE WHEN verdict='feasible' THEN 1 END) as feasible_count,
                COUNT(CASE WHEN verdict='challenging' THEN 1 END) as challenging_count,
                COUNT(CASE WHEN verdict='difficult' THEN 1 END) as difficult_count,
                COUNT(CASE WHEN verdict='impossible' THEN 1 END) as impossible_count
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 {mode_clause}
        """, (since, *mode_params)).fetchone()
        
        # ---- 时间趋势(按天) ----
        trend = db.execute(f"""
            SELECT 
                DATE(created_at) as day,
                COUNT(*) as count,
                AVG(payback_years) as avg_pb,
                AVG(gop_ratio) as avg_gop,
                AVG(adr) as avg_adr
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 {mode_clause}
            GROUP BY DATE(created_at)
            ORDER BY day
        """, (since, *mode_params)).fetchall()
        
        # ---- 城市排行 Top 20 ----
        cities = db.execute(f"""
            SELECT city, COUNT(*) as count, AVG(payback_years) as avg_pb, AVG(gop_ratio) as avg_gop
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 AND city IS NOT NULL AND city != '' {mode_clause}
            GROUP BY city
            ORDER BY count DESC
            LIMIT 20
        """, (since, *mode_params)).fetchall()
        
        # ---- 城市等级分布 ----
        tiers = db.execute(f"""
            SELECT city_tier, COUNT(*) as count, AVG(payback_years) as avg_pb, AVG(gop_ratio) as avg_gop
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 {mode_clause}
            GROUP BY city_tier
            ORDER BY city_tier
        """, (since, *mode_params)).fetchall()
        
        # ---- 酒店模式分布 ----
        hotel_modes = db.execute(f"""
            SELECT hotel_mode, COUNT(*) as count, AVG(payback_years) as avg_pb
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 
            GROUP BY hotel_mode
        """, (since,)).fetchall()
        
        # ---- ADR区间分布 ----
        adr_bins = db.execute(f"""
            SELECT 
                CASE 
                    WHEN adr < 200 THEN '0-200'
                    WHEN adr < 400 THEN '200-400'
                    WHEN adr < 600 THEN '400-600'
                    WHEN adr < 800 THEN '600-800'
                    WHEN adr < 1000 THEN '800-1000'
                    ELSE '1000+'
                END as bin,
                COUNT(*) as count,
                AVG(gop_ratio) as avg_gop
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 {mode_clause}
            GROUP BY bin
            ORDER BY MIN(adr)
        """, (since, *mode_params)).fetchall()
        
        # ---- 回本年限分布 ----
        pb_bins = db.execute(f"""
            SELECT 
                CASE 
                    WHEN payback_years <= 3 THEN '0-3年'
                    WHEN payback_years <= 5 THEN '3-5年'
                    WHEN payback_years <= 7 THEN '5-7年'
                    WHEN payback_years <= 10 THEN '7-10年'
                    WHEN payback_years <= 15 THEN '10-15年'
                    ELSE '15年+'
                END as bin,
                COUNT(*) as count
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 AND payback_years IS NOT NULL {mode_clause}
            GROUP BY bin
            ORDER BY MIN(payback_years)
        """, (since, *mode_params)).fetchall()
        
        # ---- 房间数 vs 投资额散点数据 ----
        scatter = db.execute(f"""
            SELECT rooms, investment, payback_years, gop_ratio, city, city_tier
            FROM submissions 
            WHERE created_at >= ? AND is_suspicious = 0 {mode_clause}
            LIMIT 500
        """, (since, *mode_params)).fetchall()
        
        # ---- 最近提交 ----
        recent = db.execute(f"""
            SELECT id, created_at, city, district, adr, occupancy, gop_ratio, payback_years, verdict, rooms, investment
            FROM submissions 
            WHERE created_at >= ? {mode_clause}
            ORDER BY created_at DESC
            LIMIT 20
        """, (since, *mode_params)).fetchall()
    
    return jsonify({
        'summary': {
            'total_submissions': total['c'],
            'unique_users': total['u'],
            'clean_submissions': clean_count,
            'suspicious_removed': total['c'] - clean_count
        },
        'averages': {
            'adr': round(stats['avg_adr'] or 0, 1),
            'occupancy': round(stats['avg_occ'] or 0, 1),
            'gop_ratio': round(stats['avg_gop'] or 0, 1),
            'payback_years': round(stats['avg_pb'] or 0, 1),
            'rooms': round(stats['avg_rooms'] or 0, 1),
            'investment': round(stats['avg_invest'] or 0, 1),
            'revenue': round(stats['avg_rev'] or 0, 1)
        },
        'verdicts': {
            'feasible': stats['feasible_count'] or 0,
            'challenging': stats['challenging_count'] or 0,
            'difficult': stats['difficult_count'] or 0,
            'impossible': stats['impossible_count'] or 0
        },
        'trend': [dict(row) for row in trend],
        'cities': [dict(row) for row in cities],
        'tiers': [dict(row) for row in tiers],
        'hotel_modes': [dict(row) for row in hotel_modes],
        'adr_distribution': [dict(row) for row in adr_bins],
        'payback_distribution': [dict(row) for row in pb_bins],
        'scatter': [dict(row) for row in scatter],
        'recent': [dict(row) for row in recent],
        'generated_at': datetime.now().isoformat()
    })

@app.route('/api/submissions', methods=['GET'])
def submissions_list():
    """获取原始提交列表（分页），需要密码"""
    auth = request.args.get('auth', '')
    if auth != DASHBOARD_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    offset = (page - 1) * per_page
    
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        rows = db.execute(
            "SELECT * FROM submissions ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
    
    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'data': [dict(row) for row in rows]
    })

@app.route('/api/clean', methods=['POST'])
def trigger_clean():
    """手动触发全量数据清洗"""
    auth = request.args.get('auth', '')
    if auth != DASHBOARD_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with get_db() as db:
        rows = db.execute("SELECT * FROM submissions WHERE is_suspicious IS NULL OR 1=1").fetchall()
        
        cleaned_count = 0
        for row in rows:
            data = dict(row)
            cleaned = DataCleaner.clean(data)
            db.execute("""
                UPDATE submissions SET 
                    city = ?, adr = ?, occupancy = ?, investment = ?, rooms = ?,
                    annual_rent = ?, annual_revenue = ?, gop_ratio = ?, payback_years = ?,
                    is_suspicious = ?, clean_note = ?
                WHERE id = ?
            """, (
                cleaned['city'], cleaned['adr'], cleaned['occupancy'],
                cleaned['investment'], cleaned['rooms'], cleaned['annual_rent'],
                cleaned['annual_revenue'], cleaned['gop_ratio'], cleaned['payback_years'],
                cleaned['is_suspicious'], cleaned['clean_note'], row['id']
            ))
            cleaned_count += 1
        
        db.commit()
    
    return jsonify({'status': 'ok', 'cleaned': cleaned_count})


# ============================================================
# 看板页面
# ============================================================
@app.route('/')
def dashboard():
    """看板首页"""
    auth = request.args.get('auth', '')
    if auth != DASHBOARD_PASSWORD:
        return '''
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>后台看板 - 访问验证</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0a0a1a; color: #e0e0e0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
                .login-box { background: #12122a; border: 1px solid #2a2a4a; border-radius: 12px; padding: 40px; text-align: center; max-width: 400px; width: 90%; }
                h1 { font-size: 24px; margin-bottom: 8px; color: #8b5cf6; }
                p { color: #888; margin-bottom: 24px; font-size: 14px; }
                input { width: 100%; padding: 12px; border: 1px solid #2a2a4a; border-radius: 8px; background: #0a0a1a; color: #e0e0e0; font-size: 16px; text-align: center; outline: none; }
                input:focus { border-color: #8b5cf6; }
                button { width: 100%; padding: 12px; border: none; border-radius: 8px; background: #8b5cf6; color: white; font-size: 16px; cursor: pointer; margin-top: 16px; }
                button:hover { background: #7c3aed; }
                .hint { margin-top: 16px; font-size: 12px; color: #555; }
            </style>
        </head>
        <body>
            <div class="login-box">
                <h1>🔐 后台看板</h1>
                <p>请输入访问密码</p>
                <form onsubmit="event.preventDefault(); window.location.href='/?auth='+document.getElementById('pwd').value">
                    <input type="password" id="pwd" placeholder="输入密码" autofocus>
                    <button type="submit">进入看板</button>
                </form>
                <div class="hint">酒店投资计算器 · 数据看板系统</div>
            </div>
        </body>
        </html>
        '''
    
    # 读取看板 HTML 模板
    template_path = os.path.join(BASE_DIR, 'dashboard.html')
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    # fallback: templates/ 子目录
    template_path = os.path.join(BASE_DIR, 'templates', 'dashboard.html')
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Dashboard template not found", 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

# ============================================================
# WSGI 入口 (用于 alwaysdata/uWSGI 等生产环境)
# ============================================================
init_db()
application = app

# ============================================================
# 启动 (本地开发)
# ============================================================
if __name__ == '__main__':
    print(f"\n{'='*60}")
    print(f"  酒店投资计算器 · 后台看板系统")
    print(f"  数据存储: {DB_PATH}")
    print(f"  访问密码: {DASHBOARD_PASSWORD}")
    print(f"  运行地址: http://localhost:5099")
    print(f"  看板地址: http://localhost:5099/?auth={DASHBOARD_PASSWORD}")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=5099, debug=False)
