# ==============================================
# logger_config.py - 统一日志配置 (V3.0)
# ==============================================
import logging
from logging.handlers import RotatingFileHandler

_logger_initialized = False

def setup_logger(name="CampusAI"):
    """
    创建并返回一个统一的 Logger 实例。
    - 控制台输出 INFO 及以上
    - 文件输出 DEBUG 及以上（滚动保留 5MB × 3 份）
    """
    global _logger_initialized
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if _logger_initialized:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # 控制台 Handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"
    ))
    
    # 文件 Handler (滚动 5MB, 保留 3 份)
    try:
        fh = RotatingFileHandler(
            "campus_ai.log", 
            maxBytes=5 * 1024 * 1024, 
            backupCount=3, 
            encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s/%(levelname)s] %(message)s"
        ))
        logger.addHandler(fh)
    except Exception:
        # 日志文件无法创建时不影响主流程
        pass
    
    logger.addHandler(ch)
    _logger_initialized = True
    return logger
