"""
run_scheduler.py
项目根目录入口脚本
"""

import os
import sys

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.scheduler.scheduler import main

if __name__ == "__main__":
    main()