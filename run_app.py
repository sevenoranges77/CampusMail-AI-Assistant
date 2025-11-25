import streamlit.web.cli as stcli
import os, sys

def resolve_path(path):
    """获取资源绝对路径 (兼容打包后的环境)"""
    if getattr(sys, '_MEIPASS', False):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath("."), path)

if __name__ == "__main__":
    # 伪造命令行参数
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("dashboard.py"),
        "--global.developmentMode=false",
        # [关键修改] 禁用统计信息收集，从而跳过邮箱输入环节
        "--browser.gatherUsageStats=false",
        # [可选] 强制指定地址，防止某些电脑防火墙弹窗
        "--server.address=127.0.0.1"
    ]
    sys.exit(stcli.main())