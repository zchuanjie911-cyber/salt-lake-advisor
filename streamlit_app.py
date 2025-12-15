import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import datetime

# ==========================================
# 1. 页面配置 (手机优先)
# ==========================================
st.set_page_config(page_title="盐湖军师(云端版)", page_icon="☁️", layout="centered")
hide_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stApp {padding-top: 10px;}
/* 增大手机上的字体可读性 */
.big-font {font-size:24px !important; font-weight: bold;}
</style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# ==========================================
# 2. 核心逻辑：互联网数据获取
# ==========================================
@st.cache_data(ttl=60) # 缓存60秒，防止刷新太快被封IP
def get_web_data(symbol="000792.SZ"):
    """
    从 Yahoo Finance 获取实时数据
    """
    stock = yf.Ticker(symbol)
    
    # 1. 获取今日实时行情
    # yfinance 有时实时数据会有延迟，获取最近5天数据比较稳
    hist = stock.history(period="1y") 
    
    if hist.empty:
        return None, None
    
    current_price = hist['Close'].iloc[-1]
    prev_close = hist['Close'].iloc[-2]
    change_pct = (current_price - prev_close) / prev_close
    
    return hist, current_price, change_pct

def calculate_signals(df, current_price):
    """
    在本地计算策略信号 (不依赖 QMT)
    """
    # --- A. 模拟 AI 趋势打分 (基于技术指标) ---
    # 计算 MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = exp12 - exp26
    signal = macd.ewm(span=9, adjust=False).mean()
    
    # 计算 RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    
    # 综合打分 (0~100)
    # MACD金叉 +30分, RSI在50以上 +20分...
    ai_score = 50
    if macd.iloc[-1] > signal.iloc[-1]: ai_score += 20
    if rsi < 30: ai_score += 30 (超跌反弹)
    elif rsi > 70: ai_score -= 30 (超买风险)
    else: ai_score += 10
    
    ai_score = max(0, min(100, ai_score)) # 限制在0-100
    
    return ai_score, rsi

# ==========================================
# 3. 手机 UI 界面
# ==========================================

# --- 侧边栏：输入参数 ---
with st.sidebar:
    st.header("⚙️ 参数设置")
    symbol = st.text_input("股票代码", "000792.SZ")
    eps = st.number_input("最新 EPS (每股收益)", value=1.5, help="用于计算PE估值")
    fair_pe = st.slider("合理 PE 倍数", 5, 20, 12)

# --- 主程序 ---
try:
    hist_df, price, change = get_web_data(symbol)
    
    if hist_df is None:
        st.error("无法获取数据，请检查股票代码或网络。")
        st.stop()

    ai_score, rsi = calculate_signals(hist_df, price)
    
    # 计算估值状态
    pe_ratio = price / eps
    fair_price = eps * fair_pe
    val_status = "低估" if price < fair_price * 0.85 else "高估" if price > fair_price * 1.15 else "合理"

    # --- 1. 顶部状态卡片 ---
    st.markdown(f"### {symbol} 实时监控")
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        color = "red" if change > 0 else "green"
        st.markdown(f"<h1 style='color:{color}; margin:0'>¥ {price:.2f}</h1>", unsafe_allow_html=True)
    with col_b:
        st.metric("涨跌幅", f"{change*100:.2f}%")

    # --- 2. 核心决策大字 ---
    st.divider()
    decision = "😴 观望"
    bg_color = "#f0f0f0"
    
    if val_status == "低估" and ai_score > 60:
        decision = "💎 机会: 底部启动"
        bg_color = "#d4edda" # 浅绿
    elif val_status == "高估" and ai_score < 40:
        decision = "⚠️ 风险: 高位见顶"
        bg_color = "#f8d7da" # 浅红
    elif ai_score > 80:
        decision = "🔥 趋势: 强势上涨"
        bg_color = "#fff3cd" # 浅黄

    st.markdown(f"""
        <div style="background-color: {bg_color}; padding: 15px; border-radius: 10px; text-align: center;">
            <h2 style="margin:0; color: #333;">{decision}</h2>
            <p style="margin:5px 0 0 0; color: gray;">AI信心: {ai_score:.0f}分 | 估值: {val_status}</p>
        </div>
    """, unsafe_allow_html=True)

    # --- 3. 价值 & 网格 参考 ---
    st.subheader("📊 操盘参考")
    
    tab1, tab2 = st.tabs(["价值锚点", "网格挂单"])
    
    with tab1:
        c1, c2 = st.columns(2)
        c1.metric("当前 PE", f"{pe_ratio:.1f}倍")
        c2.metric("合理价格", f"{fair_price:.1f} 元")
        
        if val_status == "低估":
            st.success(f"股价低于合理价 {((fair_price-price)/fair_price)*100:.1f}%，具备安全边际。")
        else:
            st.info("耐心等待价格回归价值中枢。")

    with tab2:
        st.caption("基于 ATR 波动的日内网格参考：")
        grid_step = price * 0.015 # 假设1.5%网格
        st.table(pd.DataFrame([
            {"方向": "🔴 压力卖出", "价格": f"¥ {price + grid_step:.2f}"},
            {"方向": "⚪ 当前基准", "价格": f"¥ {price:.2f}"},
            {"方向": "🟢 支撑买入", "价格": f"¥ {price - grid_step:.2f}"},
        ]))

    # --- 4. 走势图 (Plotly 交互式) ---
    st.subheader("📈 趋势分析")
    # 只画最近 60 天
    recent_df = hist_df.tail(60)
    fig = go.Figure(data=[go.Candlestick(x=recent_df.index,
                    open=recent_df['Open'], high=recent_df['High'],
                    low=recent_df['Low'], close=recent_df['Close'])])
    fig.update_layout(height=300, margin=dict(l=0,r=0,t=0,b=0))
    st.plotly_chart(fig, use_container_width=True)
    
    if st.button("🔄 刷新数据"):
        st.rerun()

except Exception as e:
    st.error(f"网络连接错误，无法获取 Internet 数据。\n\n错误信息: {e}")
    st.caption("提示：请确保您的电脑可以访问 Yahoo Finance (或者后续改为 akshare 国内源)。")