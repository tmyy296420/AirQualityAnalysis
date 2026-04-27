"""
空气质量定时采集调度器
每小时整点自动执行，存入 history_aqi（历史）并刷新 latest_aqi（实时）
"""

import os
import sys
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

# 将项目根目录加入 Python 路径，确保能导入 src.etl.fetch_api
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.etl.fetch_api import fetch_data, save_to_database, save_raw_files

# ---------- 日志配置 ----------
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f'scheduler_{datetime.now().strftime("%Y%m%d")}.log'),
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def scheduled_job():
    """定时采集任务：获取 → 备份 → 入库"""
    now = datetime.now()
    logger.info(f"{'='*60}")
    logger.info(f"⏰ 定时任务触发: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        df = fetch_data()
        if df is not None and not df.empty:
            # 保存原始备份
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            save_raw_files(df, timestamp)
            
            # 写入数据库：latest_aqi 覆盖 + history_aqi 追加
            save_to_database(df)
            
            logger.info(f"✅ 本次采集完成，共 {len(df)} 条记录存入数据库")
        else:
            logger.warning("⚠️ API 返回空数据，跳过本次存储")
            
    except Exception as e:
        logger.error(f"❌ 采集异常: {str(e)}", exc_info=True)


def main():
    scheduler = BlockingScheduler()
    
    # 每小时整点执行（08:00, 09:00...）
    scheduler.add_job(
        scheduled_job,
        trigger='cron',
        hour='*',
        minute='0',
        id='air_quality_hourly',
        replace_existing=True
    )
    
    logger.info("🚀 空气质量定时采集调度器启动")
    logger.info("📌 运行环境: Windows 11 | Python 3.11 | Conda")
    logger.info("📌 采集规则: 每小时整点自动执行")
    logger.info("🛑 停止方式: 按 Ctrl+C")
    
    # 启动时立即执行一次，不用等下一个整点
    logger.info("▶️ 执行首次采集...")
    scheduled_job()
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 调度器已安全停止")


if __name__ == "__main__":
    main()