import streamlit as st
import pandas as pd
import plotly.express as px
import time
import datetime
import json
import os
import sys
import urllib.request
from urllib.parse import urlparse
from openai import OpenAI
from storage_manager import StorageManager
import main
from ics import Calendar, Event

# ================== 0. 全局配置 (必须在第一行) ==================
st.set_page_config(
    page_title="CampusAI",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================== 1. 状态初始化 (解决 Widget Key 冲突的核心) ==================
# 必须在渲染任何组件前完成 Session State 的初始化

# 1.1 读取配置以确定初始状态
def load_config_for_init():
    default_conf = {
        "EMAIL_USER": "", "EMAIL_PASS": "",
        "LLM_API_BASE": "https://api.deepseek.com", "LLM_API_KEY": "", "LLM_MODEL": "deepseek-chat",
        "PROXY_HOST": "", "PROXY_PORT": ""
    }
    if os.path.exists("user_config.json"):
        try:
            with open("user_config.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
                default_conf.update(data)
        except: pass
    return default_conf

_init_conf = load_config_for_init()

# 1.2 初始化 Session State 变量
if "logs" not in st.session_state:
    st.session_state.logs = []

if "use_proxy" not in st.session_state:
    # 如果配置文件里有 host 和 port，则默认开启，否则关闭
    has_proxy_conf = bool(_init_conf["PROXY_HOST"]) and bool(_init_conf["PROXY_PORT"])
    st.session_state.use_proxy = has_proxy_conf

if "proxy_ip_input" not in st.session_state:
    st.session_state.proxy_ip_input = _init_conf["PROXY_HOST"] if _init_conf["PROXY_HOST"] else "127.0.0.1"

if "proxy_port_input" not in st.session_state:
    st.session_state.proxy_port_input = str(_init_conf["PROXY_PORT"]) if _init_conf["PROXY_PORT"] else "7890"

# ================== 2. 审美升级 (CSS Injection) ==================
# 风格：Sleek, Premium, Minimalist
st.markdown(
    """
    <style>
        /* 全局字体与背景 */
        .stApp {
            background-color: #FAFAFA; /* 极淡的灰白，护眼 */
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }
        
        /* 侧边栏美化 */
        [data-testid="stSidebar"] {
            background-color: #F4F6F8;
            border-right: 1px solid #E0E0E0;
        }
        
        /* 移除侧边栏宽度限制 (Done) */
        
        /* 调整 Toast 位置 */
        div[data-testid="stToast"] {
            top: 60px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        
        /* 卡片式容器风格 */
        div.block-container {
            padding-top: 3rem;
            padding-bottom: 3rem;
        }
        
        /* 标题样式 */
        h1, h2, h3 {
            color: #274753;
            font-weight: 600;
            letter-spacing: -0.5px;
        }
        
        /* 指标卡片 (Metric) */
        [data-testid="stMetric"] {
            background-color: #FFFFFF;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #EAEAEA;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        }
        
        /* 隐藏 Streamlit 默认的菜单 */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Tab 样式 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px;
            border-radius: 6px;
            padding-left: 20px;
            padding-right: 20px;
            background-color: transparent;
            border: none;
        }
        .stTabs [aria-selected="true"] {
            background-color: #FFFFFF;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            color: #274753;
            font-weight: bold;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ================== 3. 核心防御逻辑 (日历组件) ==================
try:
    from streamlit_calendar import calendar
    CALENDAR_AVAILABLE = True
except Exception:
    CALENDAR_AVAILABLE = False

# ================== 4. 常量定义 (莫兰迪色系) ==================
THEME_COLORS = ["#274753", "#297270", "#299d8f", "#8ab07c", "#e7c66b", "#f3a361", "#e66d50"]
CATEGORY_MAP = {
    "DDL": "测评/弹性笔试", 
    "FIXED_SLOT": "面试/定点笔试",
    "RESUME_UPDATE": "简历完善",
    "APPLICATION_RECEIVED": "投递反馈",
    "ADVERTISEMENT": "广告推广",
    "OTHER_RECRUITMENT": "其他招聘",
    "OTHER_PERSONAL": "其他邮件",
    "UNKNOWN": "未知类型"
}
STATUS_COLOR_MAP = {
    "FIXED_SLOT": THEME_COLORS[2], # 青色
    "DDL": THEME_COLORS[6],        # 砖红
    "RESUME_UPDATE": THEME_COLORS[5], # 橙色
    "DONE": THEME_COLORS[3]        # 草绿
}

# ================== 5. 核心函数 ==================
def auto_detect_proxy():
    """自动检测系统代理"""
    try:
        proxies = urllib.request.getproxies()
        proxy_url = proxies.get('http') or proxies.get('https')
        if proxy_url:
            if "://" not in proxy_url: proxy_url = "http://" + proxy_url
            parsed = urlparse(proxy_url)
            host, port = parsed.hostname, str(parsed.port)
            if host and port:
                st.session_state.proxy_ip_input = host
                st.session_state.proxy_port_input = port
                st.toast(f"✅ 已检测到系统代理: {host}:{port}")
                return
        st.toast("⚠️ 未检测到系统代理，请检查代理软件是否开启。", icon="⚠️")
    except Exception as e:
        st.toast(f"检测失败: {e}", icon="❌")

def fetch_available_models(api_base, api_key):
    try:
        # 使用 requests/httpx 的逻辑，暂不走 proxy_patch
        client = OpenAI(api_key=api_key, base_url=api_base)
        models_response = client.models.list()
        return sorted([m.id for m in models_response.data])
    except: return []

def generate_ics_file(df):
    c = Calendar()
    for _, row in df.iterrows():
        if str(row['Status']) == '已忽略': continue
        e = Event()
        e.name = f"[{CATEGORY_MAP.get(row['Category'], '待办')}] {row['Title']}"
        time_info = str(row['Time_Info'])
        try:
            if "~" in time_info:
                parts = time_info.split("~")
                date_part = parts[0].strip().split(" ")[0]
                e.begin = parts[0].strip()
                e.end = f"{date_part} {parts[1].strip()}"
            elif "(" in time_info:
                e.begin = time_info.split("(")[0].strip()
                e.make_all_day()
            else:
                clean = time_info.strip()
                e.begin = clean
                if len(clean) <= 10: e.make_all_day()
                else: e.duration = {"hours": 1}
            c.events.add(e)
        except: continue
    return c.serialize()

@st.cache_data
def parse_events_for_calendar(df):
    calendar_events = []
    if df.empty: return []
    for _, row in df.iterrows():
        if str(row['Status']) == '已忽略': continue
        title, category, status = str(row['Title']), str(row['Category']), str(row['Status'])
        color = STATUS_COLOR_MAP["DONE"] if status == '已完成' else STATUS_COLOR_MAP.get(category, "#888")
        event = {"title": title, "backgroundColor": color, "borderColor": color, "extendedProps": {"status": status}}
        time_info = str(row['Time_Info'])
        try:
            if not time_info or len(time_info) < 5 or "人工" in time_info: continue
            if "~" in time_info:
                parts = time_info.split("~")
                date_part = parts[0].strip().split(" ")[0]
                event["start"] = parts[0].strip().replace(" ", "T")
                event["end"] = f"{date_part} {parts[1].strip()}".replace(" ", "T")
            elif "(" in time_info:
                event["start"] = time_info.split("(")[0].strip()
                event["allDay"] = True
            else:
                clean = time_info.strip().replace(" ", "T")
                event["start"] = clean
                if len(clean) <= 10: event["allDay"] = True
            calendar_events.append(event)
        except: continue
    return calendar_events

# ================== 6. 侧边栏逻辑 ==================
with st.sidebar:
    st.markdown("### ⚙️ 控制台")
    st.markdown("---")
    
    # 1. 邮箱设置
    with st.expander("邮箱配置", expanded=True):
        email_user = st.text_input("QQ账号", value=_init_conf["EMAIL_USER"])
        email_pass = st.text_input(
            "IMAP 授权码", 
            value=_init_conf["EMAIL_PASS"], 
            type="password",
            help="IMAP授权码非邮箱密码。请至邮箱网页版→账号与安全→安全设置 开启并查询。"
        )
    
    # 2. 代理设置 (逻辑修复)
    with st.expander("网络代理", expanded=False):
        # 使用 session_state 控制开关，无需 default value
        enable_proxy = st.checkbox(
            "开启代理", 
            key="use_proxy",
            help="DeepSeek 等国内模型无需开启代理 (默认关闭)。"
        )
        
        proxy_host, proxy_port = "", ""
        if enable_proxy:
            col_p1, col_p2 = st.columns([3, 1])
            if col_p1.button("🔄 自动检测", use_container_width=True):
                auto_detect_proxy()
                st.rerun()
                
            st.caption("仅在连接 OpenAI 等海外服务时需要")
            host_val = st.text_input("IP地址", key="proxy_ip_input")
            port_val = st.text_input("端口", key="proxy_port_input")
            proxy_host, proxy_port = host_val, port_val

    # 3. 模型设置 (混合模式：拉取 + 保存)
    with st.expander("AI 模型", expanded=True):
        llm_base = st.text_input("API Base", value=_init_conf["LLM_API_BASE"])
        llm_key = st.text_input("API Key", value=_init_conf["LLM_API_KEY"], type="password")
        
        # 尝试拉取模型列表
        available_models = []
        if llm_base and llm_key:
            # 缓存模型列表避免频繁请求
            if "model_list_cache" not in st.session_state:
                st.session_state.model_list_cache = fetch_available_models(llm_base, llm_key)
            available_models = st.session_state.model_list_cache

        # 智能选择逻辑
        current_model_val = _init_conf["LLM_MODEL"]
        if available_models:
            # 如果当前配置的模型在列表里，设为默认索引
            idx = available_models.index(current_model_val) if current_model_val in available_models else 0
            llm_model = st.selectbox("选择模型", available_models, index=idx)
        else:
            # 降级为文本框
            llm_model = st.text_input("模型名称", value=current_model_val, help="未能自动拉取列表，请手动输入")
            if llm_key and st.button("刷新列表"):
                if "model_list_cache" in st.session_state:
                    del st.session_state.model_list_cache
                st.rerun()

    # 保存按钮
    if st.button("💾 保存系统配置", type="secondary", use_container_width=True):
        final_host = proxy_host if enable_proxy else ""
        final_port = proxy_port if enable_proxy else ""
        
        new_config = {
            "EMAIL_USER": email_user, "EMAIL_PASS": email_pass,
            "PROXY_HOST": final_host, "PROXY_PORT": final_port,
            "LLM_API_BASE": llm_base, "LLM_API_KEY": llm_key, "LLM_MODEL": llm_model
        }
        try:
            with open("user_config.json", "w", encoding='utf-8') as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)
            st.toast("✅ 配置已保存，下次启动生效", icon="💾")
            time.sleep(1)
        except Exception as e: st.error(f"保存失败: {e}")

    st.markdown("---")
    
    # 运行区域
    st.subheader("运行")
    if st.button("启动 CampusAI", type="primary", use_container_width=True):
        log_placeholder = st.empty()
        st.session_state.logs = ["⏳ 初始化引擎..."] 
        
        def ui_logger_callback(msg):
            st.session_state.logs.append(msg)
            if len(st.session_state.logs) > 50: st.session_state.logs.pop(0)
            log_placeholder.code("\n".join(st.session_state.logs), language="text")

        with st.status("处理任务队列中...", expanded=True) as status:
            try:
                main.main(ui_callback=ui_logger_callback)
                status.update(label="✅ 处理完成", state="complete", expanded=False)
                parse_events_for_calendar.clear()
                time.sleep(1)
                st.rerun()
            except Exception as e: st.error(f"运行中断: {e}")
    
    # 日志显示区
    if st.session_state.logs:
        with st.expander("运行日志", expanded=False):
            st.code("\n".join(st.session_state.logs), language="text")

    st.markdown("---")
    
    # 反馈区域
    with st.expander("💬 帮助与反馈", expanded=True):
        st.markdown(
            """
            <div style="font-size: 0.85em; color: #555;">
            <strong>遇到问题？想领免费 Key？</strong><br><br>
            加入 <b>CampusAI 内测交流群</b>！
            <ul style="padding-left: 20px; margin-top: 5px;">
                <li>🎁 获取最新 <b>免费 API Key</b></li>
                <li>🐞 反馈 Bug / 提新需求</li>
            </ul>
            👉 <a href="https://xhslink.com/m/" target="_blank" style="text-decoration: none; color: #274753; font-weight: bold;">点击跳转小红书主页</a><br>
            <i>(或搜小红书号：xxxx)</i><br><br>
            联系邮箱：<a href="mailto:xxxx@foxmail.com" style="color: #555;">xxxx@foxmail.com</a>
            </div>
            """, 
            unsafe_allow_html=True
        )

# ================== 7. 主界面逻辑 ==================
st.title("CampusAI Dashboard")
st.markdown(f"<div style='color: #888; margin-top: -15px; margin-bottom: 30px;'>智能校招邮件管理系统 V2.5</div>", unsafe_allow_html=True)

try:
    sm = StorageManager()
    df = sm.load_data()
except Exception as e:
    st.error(f"无法加载本地数据库: {e}")
    st.stop()

if not df.empty:
    display_df = df.copy()
    display_df['Category_CN'] = display_df['Category'].map(CATEGORY_MAP).fillna(display_df['Category'])
    
    valid_df = display_df[display_df['Status'] != '已忽略']
    done_count = len(valid_df[valid_df['Status'] == '已完成'])
    
    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("待办任务", f"{len(valid_df) - done_count}")
    c2.metric("面试", str(len(valid_df[valid_df['Category'] == 'FIXED_SLOT'])))
    c3.metric("笔试", str(len(valid_df[valid_df['Category'] == 'DDL'])))
    
    with c4:
        ics_data = generate_ics_file(df)
        st.download_button(
            label="📅 导出日历 (.ics)",
            data=ics_data,
            file_name="campus_schedule.ics",
            mime="text/calendar",
            help="下载后发送到手机（微信/文件传输助手），点击即可导入手机日历"
        )

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["清单", "视图", "洞察"])

    # Tab 1: 任务清单
    with tab1:
        st.markdown(
            """
            <div style="background-color: #E3F2FD; padding: 10px; border-radius: 5px; font-size: 0.9em; color: #0D47A1; margin-bottom: 15px;">
            💡 <b>提示：</b> 勾选左侧框标记完成。数据将自动同步至本地 Excel。如遇数据解析有误，请直接修改当前文件夹下的 <code>campus_data.xlsx</code> 文件。
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        task_view = display_df[display_df['Status'] != '已忽略'].copy()
        task_view['Done'] = task_view['Status'] == '已完成'
        
        edited_df = st.data_editor(
            task_view[["Done", "Category_CN", "Title", "Time_Info", "MsgID"]],
            column_config={
                "Done": st.column_config.CheckboxColumn("状态", width="small"),
                "Category_CN": st.column_config.TextColumn("类型", disabled=True),
                "Title": st.column_config.TextColumn("事项标题", width="large", disabled=True),
                "Time_Info": st.column_config.TextColumn("时间", width="medium", disabled=True),
                "MsgID": st.column_config.TextColumn("ID", disabled=True)
            },
            hide_index=True, use_container_width=True, key="editor"
        )
        if not edited_df.equals(task_view[["Done", "Category_CN", "Title", "Time_Info", "MsgID"]]):
            changes = False
            for index, row in edited_df.iterrows():
                msg_id = row['MsgID']
                new = "已完成" if row['Done'] else "未完成"
                old = df.loc[df['MsgID'] == msg_id, 'Status'].values[0]
                if old != new:
                    sm.update_status(msg_id, new)
                    changes = True
            if changes:
                st.toast("✅ 状态已同步", icon="💾")
                parse_events_for_calendar.clear()
                time.sleep(0.5)
                st.rerun()

    # Tab 2: 视图 (Timeline + Calendar)
    with tab2:
        view_mode = st.radio("模式", ["散点图 (Timeline)", "日历 (Calendar)"], horizontal=True, label_visibility="collapsed")
        
        if "散点" in view_mode:
            plot_data = []
            for _, row in valid_df.iterrows():
                try:
                    t_str = str(row['Time_Info'])
                    if len(t_str) < 5 or "人工" in t_str: continue
                    target_date = t_str.split("~")[0].split("(")[0].strip()
                    plot_data.append({
                        "Task": row['Title'], "Date": pd.to_datetime(target_date),
                        "Category": row['Category_CN'], "Status": row['Status']
                    })
                except: continue
            
            if plot_data:
                plot_df = pd.DataFrame(plot_data).sort_values("Date")
                fig = px.scatter(
                    plot_df, x="Date", y="Category", color="Category", symbol="Status",
                    hover_data=["Task"], color_discrete_sequence=THEME_COLORS, size_max=18, height=400
                )
                fig.update_layout(
                    plot_bgcolor="white",
                    xaxis=dict(showgrid=True, gridcolor='#EEE'),
                    yaxis=dict(showgrid=True, gridcolor='#EEE')
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("暂无有效时间数据")

        else:
            if CALENDAR_AVAILABLE:
                calendar_events = parse_events_for_calendar(df)
                if calendar_events:
                    calendar(
                        events=calendar_events, 
                        options={
                            "initialView": "dayGridMonth", 
                            "headerToolbar": {"left": "title", "center": "", "right": "today prev,next"}
                        },
                        key=f"cal_{len(df)}"
                    )
                    st.caption("🔵 面试 | 🔴 笔试 | 🟠 简历 | 🟢 完成")
                else:
                    st.info("暂无日历数据")
            else:
                st.warning("日历组件加载失败，请使用散点图。")

    # Tab 3: 洞察
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.funnel(
                dict(num=[len(df), len(valid_df), done_count], stage=["Total", "Valid", "Done"]), 
                x='num', y='stage', color_discrete_sequence=THEME_COLORS
            )
            fig.update_layout(plot_bgcolor="white", title_text="转化漏斗", title_x=0.5)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = px.pie(display_df, names='Category_CN', color_discrete_sequence=THEME_COLORS, hole=0.6)
            fig2.update_layout(title_text="类型分布", title_x=0.5)
            st.plotly_chart(fig2, use_container_width=True)
        
        with st.expander("🗑️ 已拦截邮件"):
            st.dataframe(display_df[display_df['Status'] == '已忽略'][['Category_CN', 'Title', 'Created_At']], use_container_width=True)

else:
    st.info("👋 欢迎使用！请在左侧配置参数并点击 Run 启动扫描。")