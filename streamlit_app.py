import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值猎手 v2.0", page_icon="🦁", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    /* 调整表格字体大小，手机看更舒服 */
    div[data-testid="stDataFrame"] {font-size: 14px;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 核心股票池 & 中文名称映射
# ==========================================
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
    "BRK-B": "伯克希尔",
    "JPM": "摩根大通",
    "KO": "可口可乐",
    "JNJ": "强生",
    "PG": "宝洁",
    "XOM": "埃克森美孚",
    "MCD": "麦当劳",
    "DIS": "迪士尼",
    "NKE": "耐克",
    "O": "Realty Income",
    "PFE": "辉瑞",

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
    "600900.SS": "长江电力",
    "600030.SS": "中信证券"
}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (MAG 7)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "INTC", "BABA", "PDD"],
    "🇺🇸 美股价值 (Buffett)": ["BRK-B", "JPM", "KO", "JNJ", "PG", "XOM", "MCD", "DIS", "NKE", "O", "PFE"],
    "🇭🇰 港股核心 (High Div)": ["0700.HK", "9988.HK", "3690.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600036.SS", "002594.SZ", "000792.SZ", "601318.SS", "601857.SS", "600900.SS", "600030.SS"]
}

# ==========================================
# 2. 数据获取与处理核心
# ==========================================
def format_large_num(num):
    """辅助函数：把长数字转为'亿'单位"""
    if num is None: return "N/A"
    return f"{num / 100000000:.2f}亿"

@st.cache_data(ttl=3600)
def fetch_and_screen(group_name):
    tickers = MARKET_GROUPS[group_name]
    data_list = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(tickers):
        cn_name = STOCK_MAP.get(symbol, symbol)
        status_text.text(f"🔍 正在深度扫描: {cn_name} ({symbol}) ...")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # --- 核心指标获取 ---
            price = info.get('currentPrice', 0)
            if price == 0 and 'regularMarketPrice' in info: price = info['regularMarketPrice']
            
            pe = info.get('trailingPE', 999)
            if pe is None: pe = 999
            
            roe = info.get('returnOnEquity', 0)
            if roe is None: roe = 0
            
            div_yield = info.get('dividendYield', 0)
            if div_yield is None: div_yield = 0
            
            # ✅ 新增：毛利率 (护城河指标)
            gross_margin = info.get('grossMargins', 0)
            if gross_margin is None: gross_margin = 0
            
            # ✅ 新增：自由现金流 (真钱指标)
            fcf = info.get('freeCashflow', 0)
            # 如果取不到FCF，尝试用 经营现金流 代替展示
            if fcf is None: fcf = info.get('operatingCashflow', 0)

            # 组合展示名称
            display_name = f"{cn_name} ({symbol})"
            
            data_list.append({
                "名称": display_name,
                "现价": price,
                "PE (市盈率)": round(pe, 2),
                "ROE%": round(roe * 100, 2),
                "毛利率%": round(gross_margin * 100, 2), # 新增
                "股息率%": round(div_yield * 100, 2),
                "自由现金流": format_large_num(fcf),      # 新增
                "raw_roe": roe, # 排序用
                "raw_gm": gross_margin # 绘图用
            })
        except Exception as e:
            continue
            
    progress_bar.empty()
    status_text.empty()
    
    return pd.DataFrame(data_list)

# ==========================================
# 3. 侧边栏筛选
# ==========================================
with st.sidebar:
    st.header("🦁 猎手参数设置")
    
    group_choice = st.selectbox("选择狩猎战场", list(MARKET_GROUPS.keys()))
    
    st.divider()
    st.subheader("🎯 价值漏斗")
    
    col_a, col_b = st.columns(2)
    with col_a:
        max_pe = st.number_input("PE 上限", value=30, step=5)
        min_roe = st.number_input("ROE 下限%", value=10, step=1)
    with col_b:
        min_gm = st.number_input("毛利 下限%", value=20, step=5, help="低于20%通常竞争激烈")
        min_div = st.number_input("股息 下限%", value=0.0, step=0.5)

    st.info("""
    **指标说明：**
    1. **ROE**: 赚钱能力的统帅 (>15%为优)
    2. **毛利率**: 护城河的深浅 (>40%为优)
    3. **自由现金流**: 公司的真金白银
    """)

# ==========================================
# 4. 主界面展示
# ==========================================
st.title(f"🌍 全球价值猎手: {group_choice}")

df = fetch_and_screen(group_choice)

if df.empty:
    st.error("无法连接全球市场数据，请检查网络。")
    st.stop()

# --- 筛选逻辑 ---
filtered_df = df[
    (df["PE (市盈率)"] <= max_pe) & 
    (df["PE (市盈率)"] > 0) & 
    (df["ROE%"] >= min_roe) &
    (df["毛利率%"] >= min_gm) & # 新增筛选
    (df["股息率%"] >= min_div)
].sort_values(by="raw_roe", ascending=False)

# 删除辅助列
display_df = filtered_df.drop(columns=["raw_roe", "raw_gm"])

# --- 核心数据表 ---
st.subheader(f"🏆 幸存名单 ({len(display_df)}/{len(df)})")

if not display_df.empty:
    # 颜色高亮逻辑：ROE越深绿越好，毛利率越深蓝越好
    st.dataframe(
        display_df.style
        .background_gradient(subset=["ROE%"], cmap="Greens")
        .background_gradient(subset=["毛利率%"], cmap="Blues")
        .format({"现价": "{:.2f}", "PE (市盈率)": "{:.1f}"}),
        use_container_width=True,
        height=500,
        hide_index=True
    )
else:
    st.warning("🧹 全军覆没！当前标准太严苛，请放宽条件（试试降低毛利率或ROE要求）。")

# --- 可视化图表 ---
st.divider()
col1, col2 = st.columns(2)

with col1:
    st.subheader("💰 护城河 vs 赚钱能力")
    if not filtered_df.empty:
        # X轴毛利，Y轴ROE
        fig = px.scatter(
            filtered_df,
            x="毛利率%",
            y="ROE%",
            size="PE (市盈率)", # 气泡大小反直觉：这里越大越贵
            color="名称",
            hover_data=["现价", "自由现金流"],
            title="右上角为【高毛利+高ROE】黄金区"
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("💸 谁是现金奶牛？")
    if not filtered_df.empty:
        # 简单的柱状图对比现金流
        # 注意：这里仅仅是数字对比，不同货币单位（美元/人民币）混合在一起，仅作粗略参考
        fig2 = px.bar(
            filtered_df.sort_values(by="毛利率%", ascending=True),
            x="毛利率%",
            y="名称",
            orientation='h',
            color="ROE%",
            title="毛利率排行榜"
        )
        st.plotly_chart(fig2, use_container_width=True)
