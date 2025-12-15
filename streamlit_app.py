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
    /* 优化表格字体 */
    div[data-testid="stDataFrame"] {font-size: 14px;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 核心股票池 & 中文名称映射 (The Dictionary)
# ==========================================
# 这里的 Key 是代码，Value 是我们想显示的中文名
STOCK_MAP = {
    # --- 🇺🇸 美股科技 ---
    "AAPL": "苹果",
    "MSFT": "微软",
    "GOOG": "谷歌",
    "AMZN": "亚马逊",
    "META": "Meta(脸书)",
    "TSLA": "特斯拉",
    "NVDA": "英伟达",
    "AMD": "超威半导体",
    "INTC": "英特尔",
    "BABA": "阿里巴巴(美)",
    "PDD": "拼多多",
    
    # --- 🇺🇸 美股价值 ---
    "BRK-B": "伯克希尔(巴菲特)",
    "JPM": "摩根大通",
    "KO": "可口可乐",
    "JNJ": "强生",
    "PG": "宝洁",
    "XOM": "埃克森美孚",
    "MCD": "麦当劳",
    "DIS": "迪士尼",
    "NKE": "耐克",
    "O": "Realty Income(月月付)",

    # --- 🇭🇰 港股核心 ---
    "0700.HK": "腾讯控股",
    "9988.HK": "阿里巴巴(港)",
    "3690.HK": "美团",
    "0941.HK": "中国移动",
    "0883.HK": "中国海洋石油",
    "1299.HK": "友邦保险",
    "0005.HK": "汇丰控股",
    "1088.HK": "中国神华",

    # --- 🇨🇳 A股核心 ---
    "600519.SS": "贵州茅台",
    "000858.SZ": "五粮液",
    "600036.SS": "招商银行",
    "002594.SZ": "比亚迪",
    "000792.SZ": "盐湖股份",
    "601318.SS": "中国平安",
    "601857.SS": "中国石油",
    "600900.SS": "长江电力"
}

# 定义分组，用于侧边栏选择
MARKET_GROUPS = {
    "🇺🇸 美股科技": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "INTC", "BABA", "PDD"],
    "🇺🇸 美股价值": ["BRK-B", "JPM", "KO", "JNJ", "PG", "XOM", "MCD", "DIS", "NKE", "O"],
    "🇭🇰 港股核心": ["0700.HK", "9988.HK", "3690.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK"],
    "🇨🇳 A股核心": ["600519.SS", "000858.SZ", "600036.SS", "002594.SZ", "000792.SZ", "601318.SS", "601857.SS", "600900.SS"]
}

# ==========================================
# 2. 数据获取与筛选核心
# ==========================================
@st.cache_data(ttl=3600)
def fetch_and_screen(group_name):
    tickers = MARKET_GROUPS[group_name]
    data_list = []
    
    # 进度条
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(tickers):
        # 获取中文名，如果没有定义，就用代码本身代替
        cn_name = STOCK_MAP.get(symbol, symbol)
        status_text.text(f"正在扫描: {cn_name} ({symbol}) ...")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # 容错处理：获取不到就填 0 或 999
            price = info.get('currentPrice', 0)
            if price == 0 and 'regularMarketPrice' in info: # 备用字段
                price = info['regularMarketPrice']

            pe = info.get('trailingPE', 999)
            pb = info.get('priceToBook', 999)
            roe = info.get('returnOnEquity', 0)
            div_yield = info.get('dividendYield', 0)
            
            # None值处理
            if pe is None: pe = 999
            if pb is None: pb = 999
            if roe is None: roe = 0
            if div_yield is None: div_yield = 0
            
            # 组合名称列：中文名 + (代码)
            # 比如: 苹果 (AAPL)
            display_name = f"{cn_name} ({symbol})"
            
            data_list.append({
                "名称 (代码)": display_name,
                "现价": price,
                "PE (市盈率)": round(pe, 2),
                "PB (市净率)": round(pb, 2),
                "ROE": round(roe * 100, 2),   # 简化表头
                "股息率%": round(div_yield * 100, 2),
                "raw_roe": roe # 用于排序的隐藏列
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
    
    group_choice = st.selectbox("选择板块", list(MARKET_GROUPS.keys()))
    
    st.divider()
    st.caption("筛选标准 (漏斗)")
    max_pe = st.slider("PE (市盈率) 上限", 0, 100, 30)
    min_roe = st.slider("ROE (净资产收益率) 下限", 0, 40, 10)
    min_div = st.slider("股息率% 下限", 0.0, 8.0, 1.0)
    
# ==========================================
# 4. 主界面
# ==========================================
st.title(f"🌍 全球价值猎手: {group_choice}")

# 1. 获取数据
df = fetch_and_screen(group_choice)

if df.empty:
    st.error("数据获取失败，请刷新重试。")
    st.stop()

# 2. 执行筛选
filtered_df = df[
    (df["PE (市盈率)"] <= max_pe) & 
    (df["PE (市盈率)"] > 0) & 
    (df["ROE"] >= min_roe) & 
    (df["股息率%"] >= min_div)
].sort_values(by="raw_roe", ascending=False) # 按ROE真实值排序

# 删除辅助排序列，不显示给用户
display_df = filtered_df.drop(columns=["raw_roe"])

# 3. 结果展示
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader(f"🏆 优选名单 ({len(display_df)}/{len(df)})")
    if not display_df.empty:
        # 样式美化：ROE 背景色
        st.dataframe(
            display_df.style.background_gradient(subset=["ROE"], cmap="Greens")
                             .format({"现价": "{:.2f}", "PE (市盈率)": "{:.1f}"}),
            use_container_width=True,
            height=500,
            hide_index=True # 隐藏索引列，更像APP
        )
    else:
        st.info("🧹 当前标准下没有股票入选，请放宽条件。")

with col2:
    st.subheader("📊 价值分布图")
    if not display_df.empty:
        # 气泡图优化
        fig = px.scatter(
            display_df, 
            x="PE (市盈率)", 
            y="ROE", 
            size="股息率%", 
            color="名称 (代码)", # 颜色区分不同股票
            hover_name="名称 (代码)",
            size_max=45,
            title="越靠左上角越好 (低PE, 高ROE)"
        )
        st.plotly_chart(fig, use_container_width=True)

# 4. 底部声明
st.divider()
st.caption("数据来源: Yahoo Finance | 仅包含核心资产池 | 延迟约 15 分钟")
