import google.generativeai as genai
import os

# ==========================================
# 【核心修改】必须添加这两行，强行让Python走代理
# 请将 '7890' 改为你实际上使用的代理软件端口
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'
# ==========================================

# 1. 填入你的 Key
API_KEY = "AIzaSyDoG1ikHBCaBFULe-UbBP8UsTcUZ10OEeI" 

try:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

    print(f"正在通过代理 {os.environ.get('HTTP_PROXY')} 发送请求测试...")
    
    # 为了防止无限死等，我们这次加上 request_options (如果库支持) 或者单纯依赖代理的连通性
    # 大部分情况下，加上上面两行环境变量就能解决问题
    response = model.generate_content("你好，现在能收到了吗？")

    print("-" * 20)
    print(response.text)
    print("-" * 20)
    print("测试通过！代码终于翻出去了。")

except Exception as e:
    print("\n!!! 依然报错 !!!")
    print(f"错误类型: {type(e)}")
    print(f"错误详情: {e}")
    
    # 帮你诊断
    if "ConnectTimeout" in str(e) or "ProxyError" in str(e):
        print(">> 诊断: 端口填错了！请检查你的代理软件设置显示的端口到底是几。")