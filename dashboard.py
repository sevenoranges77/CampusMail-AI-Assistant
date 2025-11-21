import streamlit as st
import pandas as pd
import plotly.express as px
import threading
import time
import json
import os

# 引入我们的核心逻辑
# 注意：这里只是为了调用类，实际运行要防止 main() 自动执行
from sheet_writer import SheetWriter
# 我们稍后会改造 main.py 以便在这里调用，现在先占位
import main 

# ================== 页面配置 ==================
st.set_page_config(
    page_title="LLM 校招助手驾驶舱",
    page_icon="🚀",
    layout="wide"
)

# ================== 侧边栏：设置中心 ==================
with st.sidebar:
    st.header("⚙️ 参数配置")
    st.info("非技术用户请在此填写配置，将自动保存到本地。")
    
    # 读取现有的 config.json (如果存在)
    # 这里我们做一个假设：未来打包后，不再用 config.py，而是读取 config.json
    # 为了演示，我们先手动输入
    
    with st.expander("📧 邮箱设置 (QQ Mail)", expanded=True):
        email_user = st.text_input("QQ邮箱账号", placeholder="123456@qq.com")
        email_pass = st.text_input("IMAP授权码", type="password", help="不是QQ密码，是开启IMAP后的授权码")
    
    with st.expander("🤖 AI 模型设置", expanded=True):
        llm_base = st.text_input("API Base URL", value="https://api.openai.com/v1")
        llm_key = st.text_input("API Key", type="password")
        llm_model = st.text_input("Model Name", value="gpt-4o")
    
    with st.expander("📅 Google服务设置"):
        sheet_id = st.text_input("Sheet ID", help="Google Sheet 链接中的 ID")
        cal_id = st.text_input("Calendar ID", value="primary")
    
    if st.button("💾 保存配置"):
        # 这里未来可以写逻辑生成 config.py 或 config.json
        st.success("配置已保存 (模拟)！")

# ================== 主界面：控制台 ==================
st.title("🚀 LLM 校招作战驾驶舱")
st.markdown("---")

col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("🕹️ 操作")
    if st.button("Run CampusAI (启动扫描)", type="primary", use_container_width=True):
        with st.status("正在运行中...", expanded=True) as status:
            st.write("正在初始化网络补丁...")
            time.sleep(1)
            st.write("正在连接邮箱...")
            # 这里未来调用 main.main()
            # 为了不卡死界面，通常需要把 print 重定向或者用回调显示进度
            # 暂时模拟一下
            time.sleep(2) 
            st.write("正在解析邮件...")
            status.update(label="运行完成！", state="complete", expanded=False)
            st.rerun() # 刷新页面看数据

with col2:
    st.subheader("📊 实时数据看板")
    
    # 尝试读取数据
    try:
        # 初始化 SheetWriter (需要 config 配置正确才能运行，这里先假设你本地config.py是对的)
        sw = SheetWriter() 
        df = sw.read_logs_as_df()
        
        if not df.empty:
            # 1. 关键指标 (KPI)
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            total_emails = len(df)
            # 统计 Action 列包含 'Created' 的数量
            action_count = df[df['Action'].str.contains("Created", na=False)].shape[0]
            # 统计 Category 是 DDL 的数量
            ddl_count = df[df['Category'] == "DDL"].shape[0]
            # 统计 Category 是面试的
            interview_count = df[df['Category'] == "FIXED_SLOT"].shape[0]

            kpi1.metric("已扫描邮件", str(total_emails))
            kpi2.metric("已创建日程", str(action_count))
            kpi3.metric("发现 DDL", str(ddl_count))
            kpi4.metric("发现面试", str(interview_count))
            
            st.markdown("---")
            
            # 2. 图表区域
            chart1, chart2 = st.columns(2)
            
            with chart1:
                st.markdown("##### 📧 邮件分类占比")
                # 饼图
                category_counts = df['Category'].value_counts().reset_index()
                category_counts.columns = ['Category', 'Count']
                fig_pie = px.pie(category_counts, values='Count', names='Category', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with chart2:
                st.markdown("##### 📅 每日处理趋势")
                # 按日期统计
                if pd.api.types.is_datetime64_any_dtype(df['Time']):
                    daily_counts = df.groupby(df['Time'].dt.date).size().reset_index(name='Count')
                    fig_bar = px.bar(daily_counts, x='Time', y='Count')
                    st.plotly_chart(fig_bar, use_container_width=True)
            
            # 3. 详细日志表
            with st.expander("查看详细日志记录"):
                st.dataframe(df, use_container_width=True)
                
        else:
            st.warning("暂无日志数据，请先点击运行。")
            
    except Exception as e:
        st.error(f"无法加载数据，请检查配置或网络连接。错误信息: {e}")