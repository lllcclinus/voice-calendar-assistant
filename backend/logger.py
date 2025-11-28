# backend/logger.py
import logging
import sys

def setup_logger():
    # 確保用 UTF-8，避免中文字錯誤（在新一點的 Windows 終端效果會比較好）
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 避免重複加 handler
    if not root.handlers:
        root.addHandler(handler)

    return root

logger = setup_logger()