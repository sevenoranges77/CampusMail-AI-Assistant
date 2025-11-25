import socks
import socket
from config import Config

def apply_proxy():
    """
    智能代理补丁 (Smart Proxy Patch)
    逻辑更新：只有在 Config 中明确配置了代理 IP 和端口时才启用。
    """
    # [关键修改] 检查配置是否为空
    if not Config.PROXY_HOST or not Config.PROXY_PORT:
        print("🌐 [Network] 未配置代理，将使用直连模式 (Direct Connection)。")
        return

    print(f"💉 [Proxy Patch] 正在注入代理: {Config.PROXY_HOST}:{Config.PROXY_PORT} ...")
    
    try:
        # 定义智能 Socket 类
        class SmartSocket(socks.socksocket):
            def connect(self, dest_pair):
                host = dest_pair[0]
                # 本地地址直连
                if host in ["localhost", "127.0.0.1", "::1"]:
                    self.set_proxy(None)
                else:
                    # 外网走配置的代理
                    self.set_proxy(socks.HTTP, Config.PROXY_HOST, Config.PROXY_PORT)
                super().connect(dest_pair)

        # 替换全局 Socket
        socket.socket = SmartSocket
        print("✅ [Proxy Patch] 代理注入成功！")
        
    except Exception as e:
        print(f"⚠️ [Proxy Patch] 代理配置失败，回退到直连模式: {e}")