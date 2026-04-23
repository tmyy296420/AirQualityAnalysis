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

    # 重命名列以匹配数据库
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

    # 构造时间字段
    df_db['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 从 sites 表获取经纬度和城市信息
    sites_df = pd.read_sql("SELECT station_code, city, longitude, latitude FROM sites", conn)
    df_db = df_db.merge(sites_df, on='station_code', how='left')

    # 只选择需要的字段
    cols = ['station_code', 'station_name', 'city', 'time', 'aqi',
            'pm25', 'pm10', 'so2', 'no2', 'co', 'o3', 'longitude', 'latitude']
    df_to_save = df_db[cols]

    # 1. 写入实时表（覆盖模式，只保留最新数据）
    df_to_save.to_sql('latest_aqi', conn, if_exists='replace', index=False)

    # 2. 追加到历史表
    df_to_save.to_sql('history_aqi', conn, if_exists='append', index=False)

    conn.close()

    # 统计经纬度匹配情况
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
