import PyInstaller.__main__
import os
import streamlit
import streamlit_calendar
import shutil

# 获取库的安装路径
streamlit_path = os.path.dirname(streamlit.__file__)
calendar_path = os.path.dirname(streamlit_calendar.__file__)

def build():
    print("🚀 开始打包 (终极防漏版)...")
    
    # 1. 清理旧的构建文件
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('校招助手_V3.spec'):
        os.remove('校招助手_V3.spec')

    # 2. 运行 PyInstaller
    PyInstaller.__main__.run([
        'tray_service.py',
        '--name=校招助手_V3',
        '--onefile',
        '--clean',
        '--windowed',  # 无终端窗口
        
        # --- 核心修复：强制包含所有标准库和第三方库 ---
        
        # 1. 邮件与网络相关 (修复你当前的报错)
        '--hidden-import=imaplib',
        '--hidden-import=email',
        '--hidden-import=email.message',
        '--hidden-import=email.utils',
        '--hidden-import=email.header',
        '--hidden-import=socket',
        '--hidden-import=httpx',
        '--hidden-import=tenacity',
        
        # 2. 数据处理相关
        '--hidden-import=pandas',
        '--hidden-import=numpy',
        '--hidden-import=json',
        '--hidden-import=datetime',
        '--hidden-import=time',
        '--hidden-import=re',
        
        # 3. AI与界面相关
        '--hidden-import=openai',
        '--hidden-import=streamlit',
        '--hidden-import=streamlit_calendar',
        '--hidden-import=plotly',
        '--hidden-import=plotly.express',
        
        # 4. 辅助工具
        '--hidden-import=bs4',      # BeautifulSoup
        '--hidden-import=openpyxl', # Excel支持

        '--hidden-import=win10toast',
        '--hidden-import=ics',
        '--hidden-import=pystray',
        '--hidden-import=PIL',
        '--hidden-import=apscheduler',
        '--hidden-import=apscheduler.schedulers.background',
        '--hidden-import=apscheduler.triggers.cron',
        '--hidden-import=requests',
        '--hidden-import=difflib',
        # ----------------------------------------
        
        # 拷贝元数据 (Streamlit 必需)
        '--copy-metadata=streamlit',
        '--copy-metadata=streamlit_calendar',
        
        # copy 静态资源
        f'--add-data={streamlit_path};streamlit',
        f'--add-data={calendar_path};streamlit_calendar',
        
        # copy 源代码
        '--add-data=dashboard.py;.',
        '--add-data=main.py;.',
        '--add-data=config.py;.',
        '--add-data=mail_reader.py;.',
        '--add-data=llm_parser.py;.',
        '--add-data=storage_manager.py;.',
        '--add-data=proxy_patch.py;.',
        '--add-data=logger_config.py;.',
        '--add-data=time_validator.py;.',
        '--add-data=event_dedup.py;.',
        '--add-data=conflict_detector.py;.',
        '--add-data=feishu_pusher.py;.',
        '--add-data=scheduler.py;.',
        '--add-data=tray_service.py;.',
    ])
    
    print("✅ 打包完成！请查看 dist 文件夹。")

if __name__ == "__main__":
    build()