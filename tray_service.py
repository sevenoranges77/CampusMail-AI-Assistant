# ==============================================
# tray_service.py (V3.0 - 系统托盘守护进程)
# ==============================================
import subprocess
import sys
import os
import threading
import pystray
from PIL import Image, ImageDraw
from scheduler import TaskScheduler
from logger_config import setup_logger

logger = setup_logger("CampusAI.Tray")


def create_default_icon():
    """
    生成一个简单的默认托盘图标（蓝色圆形带 C 字母）。
    如果项目中有 icon.png 则优先使用。
    """
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if os.path.exists(icon_path):
        try:
            return Image.open(icon_path)
        except Exception:
            pass

    # 程序化生成默认图标
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill="#274753")
    try:
        draw.text((20, 14), "C", fill="white")
    except Exception:
        pass
    return img


class TrayService:
    """
    系统托盘守护服务：
    - 后台驻留，保持 APScheduler 运行
    - 右键菜单提供：打开面板 / 立即扫描 / 退出
    - 关闭浏览器不影响后台任务
    """

    def __init__(self):
        self.scheduler = TaskScheduler()
        self.streamlit_process = None
        self.icon = None

    def start(self):
        """启动托盘服务（阻塞主线程）"""
        logger.info("🖥️ 启动系统托盘服务...")

        # 启动后台调度器
        self.scheduler.start()

        # 创建托盘图标
        self.icon = pystray.Icon(
            name="CampusAI",
            icon=create_default_icon(),
            title="CampusAI 校招助手 - 运行中",
            menu=pystray.Menu(
                pystray.MenuItem("📊 打开面板", self._open_dashboard),
                pystray.MenuItem("🔄 立即扫描", self._manual_scan),
                pystray.MenuItem(
                    lambda item: f"⏰ 下次扫描: {self.scheduler.next_run_time}",
                    None,
                    enabled=False
                ),
                pystray.MenuItem(
                    lambda item: f"📋 上次扫描: {self.scheduler.last_scan_time}",
                    None,
                    enabled=False
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("❌ 退出", self._quit),
            )
        )

        logger.info("✅ 托盘服务已启动")
        self.icon.run()  # 阻塞主线程，托盘驻留

    def _open_dashboard(self):
        """按需启动 Streamlit Dashboard"""
        # 检查是否已在运行
        if self.streamlit_process and self.streamlit_process.poll() is None:
            logger.info("Dashboard 已在运行")
            return

        logger.info("📊 启动 Dashboard...")
        try:
            python_exe = sys.executable
            run_app_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "run_app.py"
            )

            # 使用 CREATE_NO_WINDOW 标志避免闪出终端窗口
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW

            self.streamlit_process = subprocess.Popen(
                [python_exe, run_app_path],
                creationflags=creation_flags
            )
            logger.info("✅ Dashboard 已启动")
        except Exception as e:
            logger.error(f"Dashboard 启动失败: {e}")

    def _manual_scan(self):
        """在后台线程中执行手动扫描"""
        logger.info("🔄 用户触发手动扫描")
        thread = threading.Thread(target=self.scheduler.run_scan_now, daemon=True)
        thread.start()

    def _quit(self, icon):
        """完全退出"""
        logger.info("🛑 用户退出托盘服务")
        self.scheduler.shutdown()

        if self.streamlit_process and self.streamlit_process.poll() is None:
            self.streamlit_process.terminate()
            logger.info("Dashboard 子进程已终止")

        icon.stop()


if __name__ == "__main__":
    service = TrayService()
    service.start()
