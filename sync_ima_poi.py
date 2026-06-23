#!/usr/bin/env python3
"""
商圈POI数据同步脚本
====================
支持两种输入格式，自动识别：
  A) 桌面 CSV（逗号分隔，从桌面直接编辑后同步）
  B) IMA Markdown Table（从 IMA 知识库导出）

功能：
  1. 读取 CSV 或 Markdown Table 格式的商圈数据
  2. 转换为 index.html 中的 CITY_POI_DATABASE JS 数组格式
  3. 替换 index.html 中的数据库数组
  4. 验证数据完整性（去重、计数、城市统计）

用法：
  python sync_ima_poi.py <csv_or_md_path> [index_html_path]

参数：
  csv_or_md_path     : CSV 文件（.csv）或 IMA Markdown Table（.md/.txt）
  index_html_path    : 目标 HTML 文件路径（默认: ./index.html）

示例：
  # 从桌面 CSV 同步（日常更新推荐）
  python sync_ima_poi.py "D:/...Desktop/城市商圈知识库.csv"

  # 从 IMA 导出文件同步
  python sync_ima_poi.py _ima_sync.md

桌面 CSV 格式要求（逗号分隔）：
  city,tier,district_name,occ_range,adr_range,competition_level,guest_mix,hotel_supply_desc,chain_rate,insight_text
  北京,1,国贸CBD,72%,1100元,高,商务52%|会议18%|...,...,65%,...

IMA Markdown Table 格式：
  | city | tier | district_name | occ_range | adr_range | competition_level | guest_mix | hotel_supply_desc | chain_rate | insight_text |
  |---|---|---|---|---|---|---|---|---|---|
  | 北京 | 1 | 国贸CBD | 72% | 1100元 | 高 | 商务52%... | ... | 65% | ... |
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime


# ── 配置 ────────────────────────────────────────────

COMPETITION_TAG_MAP = {
    '高':   'hot',
    '较高': 'hot',
    '中高': 'warm',
    '中':   'warm',
    '中低': 'cool',
    '低':   'cool',
    '较低': 'cool',
}

# ── 解析函数 ────────────────────────────────────────

def parse_markdown_table(content: str) -> list[dict]:
    """解析 Markdown Table 为 dict 列表"""
    lines = content.strip().split('\n')
    rows = []

    for line in lines:
        line = line.strip()
        if not line.startswith('|'):
            continue
        # 跳过分隔行 (|---|---|)
        if re.match(r'^\|[\s\-:]+\|', line):
            continue
        # 跳过表头
        cells = [c.strip() for c in line.strip('|').split('|')]
        if cells[0].lower() == 'city':
            continue
        if len(cells) < 13:
            continue  # 至少需要 13 列（4 段客源 + 后 3 列）

        # IMA Markdown Table 中 guest_mix 字段因内部含 | 被拆成多列
        # 格式: cells[0:6] = [city, tier, district, occ, adr, competition]
        #       cells[6:-3] = guest_mix 各段（4-5 段，用 | 拼接）
        #       cells[-3:]  = [hotel_supply_desc, chain_rate, insight_text]
        guest_parts = [c for c in cells[6:-3] if c]  # 过滤空段
        guest_mix = ' | '.join(guest_parts)

        rows.append({
            'city':              cells[0],
            'tier':              cells[1],
            'district_name':     cells[2],
            'occ_range':         cells[3],
            'adr_range':         cells[4],
            'competition_level': cells[5],
            'guest_mix':         guest_mix,
            'hotel_supply_desc': cells[-3],
            'chain_rate':        cells[-2],
            'insight_text':      cells[-1],
        })

    return rows


def parse_csv(content: str) -> list[dict]:
    """解析逗号分隔 CSV 为 dict 列表

    CSV 格式（10 列，guest_mix 内用 | 分隔）:
        city,tier,district_name,occ_range,adr_range,competition_level,guest_mix,hotel_supply_desc,chain_rate,insight_text
    """
    import io, csv

    # 去掉 BOM
    if content.startswith('\ufeff'):
        content = content[1:]

    reader = csv.DictReader(io.StringIO(content))
    rows = []

    for r in reader:
        # guest_mix 在 CSV 中是单字段（| 分隔），统一加空格保持与 Markdown Table 解析结果一致
        guest_mix_raw = r.get('guest_mix', '').strip()
        guest_mix = guest_mix_raw.replace('|', ' | ').replace('  ', ' ')

        rows.append({
            'city':              r.get('city', '').strip(),
            'tier':              r.get('tier', '').strip(),
            'district_name':     r.get('district_name', '').strip(),
            'occ_range':         r.get('occ_range', '').strip() + ('' if r.get('occ_range', '').strip().endswith('%') else '%'),
            'adr_range':         r.get('adr_range', '').strip(),
            'competition_level': r.get('competition_level', '').strip(),
            'guest_mix':         guest_mix,
            'hotel_supply_desc': r.get('hotel_supply_desc', '').strip(),
            'chain_rate':        r.get('chain_rate', '').strip(),
            'insight_text':      r.get('insight_text', '').strip(),
        })

    return rows


def detect_format(content: str) -> str:
    """自动检测输入格式: 'csv' | 'markdown' | 'json'"""
    stripped = content.strip()

    # JSON 包裹的 markdown（IMA fetch_media_content 输出）
    if stripped.startswith('{'):
        return 'json'

    # 逗号分隔 CSV（以 city,tier 开头或以 \ufeffcity,tier 开头）
    first_line = stripped.split('\n')[0].replace('\ufeff', '')
    if first_line.startswith('city,tier') or first_line.startswith('city,'):
        return 'csv'

    # Markdown Table（以 | 开头）
    if stripped.startswith('|'):
        return 'markdown'

    return 'unknown'


def make_id(city: str, district: str) -> str:
    """生成唯一 ID: 城市-商圈（/ 替换为 -，全小写）"""
    raw = f'{city}-{district}'
    raw = raw.replace('/', '-').replace('·', '-').replace(' ', '')
    return raw.lower()


def make_name(city: str, district: str) -> str:
    """生成显示名称: 城市商圈（/ 替换为 ·，全市略去）"""
    # 商圈为"全市"时只显示城市名
    if district == '全市':
        return city
    d = district.replace('/', '·').replace('-', '·')
    return f'{city}{d}'


def competition_tag(level: str) -> str:
    """竞争等级 → 热度标签"""
    return COMPETITION_TAG_MAP.get(level, 'warm')


def row_to_js(row: dict) -> str:
    """单行 dict → JS 对象字符串"""
    _id   = make_id(row['city'], row['district_name'])
    _name = make_name(row['city'], row['district_name'])
    _tier = int(row['tier'])
    _city = row['city']
    _occ  = row['occ_range']
    _adr  = row['adr_range'].replace('元', '')
    _comp = row['competition_level']
    _tag  = competition_tag(_comp)
    _guest = row['guest_mix']
    _supply = row['hotel_supply_desc']
    _chain  = row['chain_rate']
    _insight = row['insight_text']

    return (
        f"{{ id:'{_id}', name:'{_name}', tier:{_tier}, city:'{_city}', "
        f"occ:'{_occ}', adr:'{_adr}', competition:'{_comp}', "
        f"competitionTag:'{_tag}', guestType:'{_guest}', "
        f"hotelSupply:'{_supply}', chainRate:'{_chain}', "
        f"insight:'{_insight}' }}"
    )


def rows_to_js_array(rows: list[dict]) -> str:
    """多行转 JS 数组字符串"""
    items = []
    for r in rows:
        items.append(f'  {row_to_js(r)}')
    return 'const CITY_POI_DATABASE = [\n' + ',\n'.join(items) + '\n];'


# ── 替换逻辑 ────────────────────────────────────────

def replace_database(html_path: str, new_array: str) -> bool:
    """替换 index.html 中的 CITY_POI_DATABASE"""
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    pattern = r'const CITY_POI_DATABASE = \[[\s\S]*?\n\];'
    match = re.search(pattern, html)
    if not match:
        print('❌ 未在 HTML 中找到 CITY_POI_DATABASE 数组')
        return False

    new_html = html[:match.start()] + new_array + html[match.end():]

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html)

    return True


# ── 验证 ───────────────────────────────────────────

def validate(rows: list[dict]) -> bool:
    """验证数据完整性"""
    ok = True

    # 1. 检查必需字段
    required = ['city', 'tier', 'district_name', 'occ_range', 'adr_range',
                'competition_level', 'guest_mix', 'hotel_supply_desc',
                'chain_rate', 'insight_text']
    for i, row in enumerate(rows):
        for field in required:
            if field not in row or not row[field]:
                print(f'  ⚠ 第 {i+2} 行缺少字段: {field}')
                ok = False

    # 2. 检查重复 ID
    ids = [make_id(r['city'], r['district_name']) for r in rows]
    dupes = [id_ for id_ in set(ids) if ids.count(id_) > 1]
    if dupes:
        print(f'  ❌ 发现 {len(dupes)} 个重复 ID: {dupes[:5]}')
        ok = False
    else:
        print(f'  ✅ ID 去重检查通过 ({len(set(ids))} 个唯一 ID)')

    # 3. 统计
    cities = sorted(set(r['city'] for r in rows))
    tiers = {}
    for r in rows:
        t = r['tier']
        tiers[t] = tiers.get(t, 0) + 1

    print(f'  📊 总记录: {len(rows)}')
    print(f'  🏙 覆盖城市: {len(cities)}')
    print(f'  📈 城市等级分布: {dict(sorted(tiers.items()))}')

    return ok


# ── 备份 ───────────────────────────────────────────

def backup(html_path: str):
    """备份当前 HTML"""
    bak = Path(html_path).with_suffix(f'.bak-{datetime.now():%Y%m%d-%H%M%S}.html')
    with open(html_path, 'r', encoding='utf-8') as src:
        with open(bak, 'w', encoding='utf-8') as dst:
            dst.write(src.read())
    print(f'  💾 已备份: {bak.name}')


# ── 主流程 ─────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    html_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('index.html')

    if not csv_path.exists():
        print(f'❌ 找不到文件: {csv_path}')
        sys.exit(1)
    if not html_path.exists():
        print(f'❌ 找不到文件: {html_path}')
        sys.exit(1)

    # 尝试多种编码读取（UTF-8 → GBK → GB18030）
    content = None
    for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030']:
        try:
            with open(csv_path, 'r', encoding=enc) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if content is None:
        print('❌ 无法识别文件编码，请确认文件为 UTF-8 或 GBK 编码')
        sys.exit(1)

    fmt = detect_format(content)
    print(f'📥 读取数据: {csv_path}')
    print(f'  检测到格式: {fmt}')

    # 根据格式解析
    if fmt == 'json':
        data = json.loads(content)
        if 'content' in data:
            content = data['content']
            print('  (从 JSON 包裹中提取内容)')
        fmt = detect_format(content)
        print(f'  内部格式: {fmt}')

    if fmt == 'csv':
        print('  使用 CSV（逗号分隔）解析 ...')
        rows = parse_csv(content)
    elif fmt == 'markdown':
        print('  使用 Markdown Table 解析 ...')
        rows = parse_markdown_table(content)
    else:
        print('❌ 无法识别数据格式')
        print('  支持: CSV (逗号分隔) / Markdown Table / JSON 包裹')
        sys.exit(1)

    print(f'  解析到 {len(rows)} 条记录')

    if not rows:
        print('❌ 未解析到任何数据')
        sys.exit(1)

    print(f'\n🔍 验证数据...')
    if not validate(rows):
        print('\n⚠ 数据验证发现问题，请检查后重试')
        sys.exit(1)

    new_array = rows_to_js_array(rows)

    print(f'\n🔧 更新 {html_path}...')
    backup(html_path)

    if replace_database(str(html_path), new_array):
        print(f'  ✅ 已替换 CITY_POI_DATABASE ({len(rows)} 条)')
    else:
        print(f'  ❌ 替换失败')
        sys.exit(1)

    print(f'\n🎉 同步完成！')
    print(f'  → 下一步: git add {html_path.name} && git commit -m "sync: 更新商圈POI数据 ({len(rows)}条/{len(set(r["city"] for r in rows))}城)"')


if __name__ == '__main__':
    main()
