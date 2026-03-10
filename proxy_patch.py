# ==============================================
# proxy_patch.py (V3.0 - 环境变量代理，移除猴子补丁)
# ==============================================
import os
from config import Config
from logger_config import setup_logger

logger = setup_logger("CampusAI.Proxy")

def apply_proxy():
    """
    标准代理配置：通过环境变量设置代理。
    OpenAI SDK、requests、httpx 等均原生支持 HTTP_PROXY/HTTPS_PROXY。
    """
    if not Config.PROXY_HOST or not Config.PROXY_PORT:
        # 清理环境变量，确保直连
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
        os.environ.pop("NO_PROXY", None)
        logger.info("🌐 [Network] 未配置代理，将使用直连模式 (Direct Connection)。")
        return

    proxy_url = f"http://{Config.PROXY_HOST}:{Config.PROXY_PORT}"
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
    
    logger.info(f"🌐 [Network] 已通过环境变量设置代理: {proxy_url}")