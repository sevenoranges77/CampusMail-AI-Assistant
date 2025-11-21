import os
import requests
from config import Config

# 1. 强制设置代理 (模拟 google_auth.py 的行为)
if hasattr(Config, 'PROXY_URL') and Config.PROXY_URL:
    os.environ['http_proxy'] = Config.PROXY_URL
    os.environ['https_proxy'] = Config.PROXY_URL
    print(f"⚙️ 正在使用代理: {Config.PROXY_URL}")
else:
    print("⚠️ 未配置代理！请检查 config.py")

print("------------------------------------------------")

# 2. 测试连接 Google
target_url = "https://www.google.com"
print(f"🚀 正在尝试连接: {target_url} ...")

try:
    # 设置5秒超时，避免干等
    response = requests.get(target_url, timeout=5)
    
    if response.status_code == 200:
        print("✅ 连接成功！Python 可以通过代理访问 Google。")
        print(f"   响应状态码: {response.status_code}")
    else:
        print(f"❌ 连接虽通，但返回异常状态码: {response.status_code}")

except requests.exceptions.ProxyError:
    print("❌ [关键错误] 代理错误 (ProxyError)")
    print("   原因可能是：")
    print("   1. 端口号填错了（比如填了 SOCKS 端口但协议写的 http）")
    print("   2. 代理软件没开")
except requests.exceptions.ConnectTimeout:
    print("❌ [关键错误] 连接超时 (Timeout)")
    print("   Python 找不到这个代理端口，或者代理没反应。")
except requests.exceptions.SSLError:
    print("❌ [关键错误] SSL 证书错误")
    print("   可能是代理软件的证书拦截设置问题。")
except Exception as e:
    print(f"❌ 其他错误: {e}")