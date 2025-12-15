import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值猎手", page_icon="🌍", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    div[data-testid="stMetricValue"] {font-size: 18px;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 定义核心股票池 (The Core Universe)
# ==========================================
# 这是一个精选的全球核心资产池，您可以随时在代码里添加
STOCK_POOL = {
    "🇺🇸 美股科技": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "INTC"],
    "🇺🇸 美股价值": ["BRK-B", "JPM", "KO", "JNJ", "PG", "XOM", "CVX", "MCD", "DIS", "NKE"],
    "🇭🇰 港股核心": ["0700.HK", "9988.HK", "3690.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK"],
    "🇨🇳 A股核心": ["600519.SS", "000858.SZ", "600036.SS", "002594.SZ", "000792.SZ", "601318.SS", "601857.SS"]
}

# ==========================================
# 2. 数据获取与筛选核心
# ==========================================
@st.cache_data(ttl=3600) # 缓存1小时，避免每次刷新都请求
def fetch_and_screen(market_choice):
    """
    批量获取股票基本面数据
    """
    tickers = STOCK_POOL[market_choice]
    data_list = []
    
    # 创建进度条
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(tickers):
        status_text.text(f"正在扫描: {symbol} ...")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # 提取核心价值指标
            # 注意：不同市场的数据可能缺失，需要容错处理
            pe = info.get('trailingPE', 999)
            pb = info.get('priceToBook', 999)
            roe = info.get('returnOnEquity', 0)
            div_yield = info.get('dividendYield', 0)
            if div_yield is None: div_yield = 0
            
            name = info.get('shortName', symbol)
            price = info.get('currentPrice', 0)
            
            data_list.append({
                "代码": symbol,
                "名称": name,
                "现价": price,
                "PE (市盈率)": round(pe, 2) if pe else 999,
                "PB (市净率)": round(pb, 2) if pb else 999,
                "ROE (净资产收益率)": round(roe * 100, 2) if roe else 0,
                "股息率%": round(div_yield * 100, 2)
            })
        except Exception as e:
            continue
            
    progress_bar.empty()
    status_text.empty()
    
    return pd.DataFrame(data_list)

# ==========================================
# 3. 侧边栏：筛选条件
# ==========================================
with st.sidebar:
    st.header("🎯 价值筛选器")
    
    market = st.selectbox("选择市场", list(STOCK_POOL.keys()))
    
    st.divider()
    st.subheader("设定标准")
    max_pe = st.slider("最高 PE (越低越便宜)", 0, 100, 25)
    max_pb = st.slider("最高 PB (越低越安全)", 0.0, 10.0, 3.0)
    min_roe = st.slider("最低 ROE (越高越赚钱)", 0, 50, 15)
    min_div = st.slider("最低 股息率%", 0.0, 10.0, 2.0)
    
    st.info("💡 经典价值公式：低 PE + 高 ROE + 稳定股息")

# ==========================================
# 4. 主界面
# ==========================================
st.title(f"🌍 全球价值猎手: {market}")

# 1. 获取数据
df = fetch_and_screen(market)

if df.empty:
    st.error("无法获取数据，请检查网络连接 (Streamlit Cloud 最佳)")
    st.stop()

# 2. 执行筛选逻辑
# 使用 Pandas 进行过滤
filtered_df = df[
    (df["PE (市盈率)"] <= max_pe) & 
    (df["PE (市盈率)"] > 0) & # 过滤亏损股
    (df["PB (市净率)"] <= max_pb) & 
    (df["ROE (净资产收益率)"] >= min_roe) & 
    (df["股息率%"] >= min_div)
].sort_values(by="ROE (净资产收益率)", ascending=False) # 按赚钱能力排序

# 3. 结果展示
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader(f"🔍 筛选结果 ({len(filtered_df)} 只)")
    if not filtered_df.empty:
        # 高亮显示数据表
        st.dataframe(
            filtered_df.style.background_gradient(subset=["ROE (净资产收益率)"], cmap="Greens")
                             .format({"现价": "{:.2f}", "PE (市盈率)": "{:.1f}"}),
            use_container_width=True,
            height=400
        )
    else:
        st.warning("⚠️ 当前条件下没有符合的标的，请尝试放宽筛选标准。")

with col2:
    st.subheader("📊 估值气泡图")
    if not filtered_df.empty:
        # 画图：X轴=PE, Y轴=ROE, 大小=股息率
        fig = px.scatter(
            filtered_df, 
            x="PE (市盈率)", 
            y="ROE (净资产收益率)", 
            size="股息率%", 
            color="代码",
            hover_name="名称",
            size_max=40,
            title="性价比分布 (右上角为优质区)"
        )
        st.plotly_chart(fig, use_container_width=True)

# 4. 个股深度透视 (One-Click Analysis)
st.divider()
st.subheader("🔬 个股深度透视")
selected_stock = st.selectbox("选择一只股票查看详情:", df["代码"].tolist())

if st.button("开始 AI 诊断"):
    stock_info = df[df["代码"] == selected_stock].iloc[0]
    
    # 模拟一个简单的 AI 评语
    score = 0
    if stock_info["PE (市盈率)"] < 15: score += 30
    if stock_info["ROE (净资产收益率)"] > 20: score += 30
    if stock_info["股息率%"] > 3: score += 20
    score += 20 # 基础分
    
    c1, c2, c3 = st.columns(3)
    c1.metric("当前价格", f"{stock_info['现价']}")
    c2.metric("价值评分", f"{score} 分")
    
    decision = "买入" if score > 80 else "持有" if score > 60 else "观望"
    color = "green" if score > 80 else "orange"
    c3.markdown(f"### 建议: :{color}[{decision}]")
    
    st.json(stock_info.to_dict()) # 显示原始数据详情
