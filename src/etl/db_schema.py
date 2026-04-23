# src/etl/db_schema.py
"""
空气质量监测数据库初始化脚本
设计：sites（站点元数据） + latest_aqi（实时快照） + history_aqi（历史时序）
"""

import sqlite3
import os
import csv

# 项目根目录和路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'air_quality.db')
SITES_CSV = os.path.join(DATA_DIR, 'sites_metadata.csv')

os.makedirs(DATA_DIR, exist_ok=True)


def create_tables():
    """创建三张核心表"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. 站点元数据表（静态）
    c.execute('''
        CREATE TABLE IF NOT EXISTS sites (
            station_code TEXT PRIMARY KEY,
            station_name TEXT NOT NULL,
            city TEXT,
            longitude REAL,
            latitude REAL
        )
    ''')

    # 2. 实时数据表（只保留最新一条）
    c.execute('''
        CREATE TABLE IF NOT EXISTS latest_aqi (
            station_code TEXT PRIMARY KEY,
            station_name TEXT,
            time TEXT NOT NULL,
            aqi INTEGER,
            pm25 REAL,
            pm10 REAL,
            so2 REAL,
            no2 REAL,
            co REAL,
            o3 REAL,
            longitude REAL,
            latitude REAL,
            UNIQUE(station_code) ON CONFLICT REPLACE
        )
    ''')

    # 3. 历史时序数据表
    c.execute('''
        CREATE TABLE IF NOT EXISTS history_aqi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_code TEXT NOT NULL,
            station_name TEXT,
            city TEXT,
            time TEXT NOT NULL,
            aqi INTEGER,
            pm25 REAL,
            pm10 REAL,
            so2 REAL,
            no2 REAL,
            co REAL,
            o3 REAL,
            longitude REAL,
            latitude REAL,
            UNIQUE(station_code, time) ON CONFLICT REPLACE
        )
    ''')

    # 索引
    c.execute('CREATE INDEX IF NOT EXISTS idx_history_station ON history_aqi (station_code)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_history_time ON history_aqi (time)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_history_city ON history_aqi (city)')

    conn.commit()
    conn.close()
    print(f"✅ 三张表创建成功：{DB_PATH}")


def import_sites_from_csv():
    """从 CSV 导入站点经纬度，自动处理编码"""
    if not os.path.exists(SITES_CSV):
        print(f"⚠️ 站点元数据文件不存在：{SITES_CSV}")
        print("   请将站点列表 CSV 文件放入 data/ 目录，命名为 sites_metadata.csv")
        return

    # 尝试多种编码
    encodings_to_try = ['gbk', 'gb2312', 'utf-8-sig', 'utf-8']
    lines = None

    for enc in encodings_to_try:
        try:
            with open(SITES_CSV, 'r', encoding=enc) as f:
                lines = f.readlines()
            print(f"✅ 成功使用 {enc} 编码读取 CSV 文件")
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if lines is None:
        print("❌ 无法识别文件编码，请用 VS Code 将 CSV 保存为 UTF-8 再试")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0

    for i, line in enumerate(lines):
        row = line.strip().split(',')
        # 跳过标题行
        if i == 0 and not row[0].strip().isdigit():
            print(f"   跳过标题行：{line.strip()}")
            continue

        if len(row) >= 5:
            try:
                station_code = row[0].strip()
                station_name = row[1].strip()
                city = row[2].strip()
                longitude = float(row[3].strip()) if row[3].strip() else None
                latitude = float(row[4].strip()) if row[4].strip() else None

                if longitude is None or latitude is None:
                    print(f"⚠️ 跳过无经纬度站点：{station_code} {station_name}")
                    continue

                c.execute('''
                    INSERT OR REPLACE INTO sites
                    (station_code, station_name, city, longitude, latitude)
                    VALUES (?, ?, ?, ?, ?)
                ''', (station_code, station_name, city, longitude, latitude))
                count += 1
            except (ValueError, IndexError) as e:
                print(f"⚠️ 跳过无效行：{row[:5]}，错误：{e}")

    conn.commit()
    conn.close()
    print(f"✅ 从 CSV 成功导入 {count} 个站点的元数据")


def init_db():
    """完整初始化数据库"""
    create_tables()
    import_sites_from_csv()
    print("\n🎉 数据库初始化完成！")


if __name__ == "__main__":
    init_db()