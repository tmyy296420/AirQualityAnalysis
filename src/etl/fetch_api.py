"""
空气质量数据采集脚本（eia-data.com 正式授权接口）
数据源自中国环境监测总站，每小时更新一次。
"""

import requests
import pandas as pd
import json
import os
import sqlite3
from datetime import datetime

# ====== 安全读取 AccessKey（不硬编码） ======
ACCESS_KEY = os.environ.get("CNEMC_ACCESS_KEY")
if not ACCESS_KEY:
    print("❌ 错误：未设置环境变量 CNEMC_ACCESS_KEY")
    print("   PowerShell: $env:CNEMC_ACCESS_KEY='你的Key'")
    print("   CMD: set CNEMC_ACCESS_KEY=你的Key")
    exit(1)

API_URL = f"http://eia-data.com:8080/getPmNowJson?accessKey={ACCESS_KEY}"

# 项目根目录（兼容 Windows / Linux / macOS）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'air_quality.db')
os.makedirs(DATA_DIR, exist_ok=True)
# ==========================================

def fetch_data():
    """获取实时空气质量数据，返回 DataFrame"""
    try:
        resp = requests.get(API_URL, timeout=30)
        print(f"状态码: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            df = pd.DataFrame(data)
            print(f"获取站点数量: {len(df)}")
            return df
        else:
            print(f"请求失败: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"获取数据时出错: {e}")
        return None

def save_to_database(df):
    """将数据存入数据库：实时表（覆盖）+ 历史表（追加）"""
    if df is None or df.empty:
        print("无数据可入库")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ========== 1. 自动创建表（如果不存在） ==========
    c.execute('''
        CREATE TABLE IF NOT EXISTS sites (
            station_code TEXT PRIMARY KEY,
            station_name TEXT NOT NULL,
            city TEXT,
            longitude REAL,
            latitude REAL
        )
    ''')
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

    # ========== 2. 从 CSV 导入站点数据（如果 sites 表为空） ==========
    sites_csv = os.path.join(DATA_DIR, 'sites_metadata.csv')
    if os.path.exists(sites_csv):
        c.execute("SELECT COUNT(*) FROM sites")
        if c.fetchone()[0] == 0:
            import csv
            # 尝试多种编码
            for enc in ['gbk', 'utf-8', 'utf-8-sig']:
                try:
                    with open(sites_csv, 'r', encoding=enc) as f:
                        reader = csv.reader(f)
                        # 跳过标题行
                        next(reader)
                        count = 0
                        for row in reader:
                            if len(row) >= 5 and row[3].strip() and row[4].strip():
                                try:
                                    c.execute('''
                                        INSERT OR IGNORE INTO sites
                                        (station_code, station_name, city, longitude, latitude)
                                        VALUES (?, ?, ?, ?, ?)
                                    ''', (row[0].strip(), row[1].strip(), row[2].strip(),
                                          float(row[3].strip()), float(row[4].strip())))
                                    count += 1
                                except:
                                    continue
                        print(f"✅ 已从 CSV 导入 {count} 个站点元数据")
                    break
                except UnicodeDecodeError:
                    continue
    conn.commit()

    # ========== 3. 关联经纬度（重命名列等） ==========
    df_db = df.rename(columns={
        'Station_ID_C': 'station_code',
        'PositionName': 'station_name',
        'aqi': 'aqi',
        'CO': 'co',
        'NO2': 'no2',
        'O3': 'o3',
        'PM10': 'pm10',
        'PM2_5': 'pm25',
        'SO2': 'so2'
    })

    df_db['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df_db['station_code'] = df_db['station_code'].str.strip().str.upper()

    # 读取站点表（此时已保证存在）
    sites_df = pd.read_sql("SELECT station_code, city, longitude, latitude FROM sites", conn)
    sites_df['station_code'] = sites_df['station_code'].str.strip().str.upper()
    df_db = df_db.merge(sites_df, on='station_code', how='left')

    cols = ['station_code', 'station_name', 'city', 'time', 'aqi',
            'pm25', 'pm10', 'so2', 'no2', 'co', 'o3', 'longitude', 'latitude']
    df_to_save = df_db[cols]

    # ========== 4. 写入表 ==========
    df_to_save.to_sql('latest_aqi', conn, if_exists='replace', index=False)
    df_to_save.to_sql('history_aqi', conn, if_exists='append', index=False)

    conn.close()

    matched = df_db['longitude'].notna().sum()
    total = len(df_db)
    print(f"✅ 实时表已更新，历史表追加 {total} 条记录")
    print(f"📍 经纬度匹配：{matched}/{total} 个站点")


def save_raw_files(df, timestamp):
    """保存原始 JSON 和 CSV 备份"""
    json_path = os.path.join(DATA_DIR, f"cnemc_{timestamp}.json")
    csv_path = os.path.join(DATA_DIR, f"cnemc_{timestamp}.csv")
    
    # 保存 JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(df.to_dict(orient='records'), f, ensure_ascii=False, indent=2)
    
    # 保存 CSV
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    print(f"📁 原始数据已备份: {json_path} / {csv_path}")

def main():
    print("=" * 60)
    print("空气质量数据采集（eia-data.com 授权接口）")
    print(f"执行时间: {datetime.now()}")
    print("=" * 60)
    
    df = fetch_data()
    if df is not None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_raw_files(df, timestamp)
        save_to_database(df)
        print(f"\n📊 数据预览:")
        print(df[['PositionName', 'aqi', 'PM2_5', 'PM10']].head())
    else:
        print("❌ 数据获取失败")

if __name__ == "__main__":
    main()
