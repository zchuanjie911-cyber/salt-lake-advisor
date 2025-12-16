import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值猎手 v3.5 (自由搜索版)", page_icon="🦁", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    div[data-testid="stDataFrame"] {font-size: 14px;}
    .big-font {font-size:20px !important; font-weight: bold;}
    div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 核心股票池 (固定列表)
# ==========================================
STOCK_MAP = {
    # 常用字典，用于显示中文名。如果是自选股，代码会自动尝试获取名称。
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊", "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达",
    "BABA": "阿里(美)", "PDD": "拼多多", "JD": "京东", "BIDU": "百度", "NTES": "网易",
    "BRK-B": "伯克希尔", "V": "Visa", "MA": "万事达", "COST": "开市客", "MCD": "麦当劳", "KO": "可口可乐", "PEP": "百事",
    "LLY": "礼来", "NVO": "诺和诺德", "UNH": "联合健康", "JPM": "摩根大通", "JNJ": "强生", "PG": "宝洁", "WMT": "沃尔玛",
    "0700.HK": "腾讯", "9988.HK": "阿里(港)", "3690.HK": "美团", "0388.HK": "港交所", "0941.HK": "中移动", "0883.HK": "中海油",
    "600519.SS": "茅台", "000858.SZ": "五粮液", "600900.SS": "长电", "300750.SZ": "宁德时代", "002594.SZ": "比亚迪", "600660.SS": "福耀"
}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (AI & Chips)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "TSM", "ASML", "INTC", "CRM", "ORCL", "BABA", "PDD"],
    "🇺🇸 美股护城河 (Moat & Value)": ["BRK-B", "V", "MA", "COST", "MCD", "KO", "PEP", "LLY", "NVO", "UNH", "JPM", "JNJ", "PG", "XOM", "CVX", "DIS", "NKE", "O", "WMT"],
    "🇭🇰 港股核心 (High Div & Tech)": ["0700.HK", "9988.HK", "3690.HK", "0388.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK", "1810.HK", "2015.HK"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ", "600036.SS", "601318.SS", "601857.SS", "601225.SS", "000792.SZ", "600030.SS", "600276.SS"]
}

# ==========================================
# 2. DCF 引擎与数据获取
# ==========================================
def calculate_dcf(fcf, growth_rate, discount_rate, terminal_rate=0.03, years=10):
    """简易两阶段DCF计算器"""
    if fcf <= 0: return 0
    future_cash_flows = []
    for i in range(1, years + 1):
        cash = fcf * ((1 + growth_rate) ** i)
        discounted_cash = cash / ((1 + discount_rate) ** i)
        future_cash_flows.append(discounted_cash)
    sum_stage1 = sum(future_cash_flows)
    final_year_cash = fcf * ((1 + growth_rate) ** years)
    terminal_value = final_year_cash * (1 + terminal_rate) / (discount_rate - terminal_rate)
    discounted_terminal_value = terminal_value / ((1 + discount_rate) ** years)
    return sum_stage1 + discounted_terminal_value

@st.cache_data(ttl=300) # 自选模式缓存时间缩短
def fetch_financials(ticker_list, group_name_for_growth, discount_rate_input):
    data_list = []
    
    # 汇率修正字典 (常用)
    ADR_FIX = {"PDD": 7.25, "BABA": 7.25, "BIDU": 7.25, "JD": 7.25, "TSM": 32.5, "NTES": 7.25, "TCEHY": 7.8}
    
    # 行业默认增长率假设 (如果没有分析师数据，用这个兜底)
    DEFAULT_GROWTH = {
        "🇺🇸 美股科技 (AI & Chips)": 0.12, 
        "🇺🇸 美股护城河 (Moat & Value)": 0.06,
        "🇭🇰 港股核心 (High Div & Tech)": 0.05, 
        "🇨🇳 A股核心 (Core Assets)": 0.08,
        "🔍 自选/搜索 (Custom)": 0.08 # 自选默认给8%
    }
    base_growth = DEFAULT_GROWTH.get(group_name_for_growth, 0.06)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(ticker_list):
        # 尝试获取中文名，如果没有则显示代码
        cn_name = STOCK_MAP.get(symbol, symbol)
        status_text.text(f"🧮 正在分析: {cn_name} ({symbol})...")
        progress_bar.progress((i + 1) / len(ticker_list))
        
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # 如果是自选股且没有中文映射，尝试用API里的名字
            if cn_name == symbol:
                cn_name = info.get('shortName', symbol)

            mkt_cap = info.get('marketCap', 0)
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            roe = info.get('returnOnEquity', 0) or 0
            
            # --- FCF 获取 ---
            fcf = info.get('freeCashflow', 0)
            if fcf is None: 
                op_cash = info.get('operatingCashflow', 0) or 0
                capex = info.get('capitalExpenditures', 0) or 0 
                fcf = op_cash + capex if capex < 0 else op_cash - capex
            
            # --- 增长率获取 ---
            analyst_growth = info.get('earningsGrowth', None)
            if analyst_growth: 
                growth_rate = min(max(analyst_growth, 0.02), 0.25)
            else: 
                growth_rate = base_growth

            # --- 汇率修正 ---
            fix_rate = ADR_FIX.get(symbol, 1.0)
            fcf_usd = fcf / fix_rate
            
            # --- DCF 计算 ---
            intrinsic_value = calculate_dcf(fcf_usd, growth_rate, discount_rate_input/100)
            upside = (intrinsic_value - mkt_cap) / mkt_cap if mkt_cap > 0 else 0
            fair_price = price * (1 + upside) if price > 0 else 0
            fcf_yield = (fcf_usd / mkt_cap) if mkt_cap > 0 else 0

            data_list.append({
                "代码": symbol, "名称": cn_name, "现价": price, "DCF估值": round(fair_price, 2),
                "潜在涨幅%": round(upside * 100, 2), "增长假设%": round(growth_rate * 100, 1),
                "FCF收益率%": round(fcf_yield * 100, 2), "ROE%": round(roe * 100, 2), "raw_upside": upside
            })
        except Exception:
            continue
            
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(data_list)

# ==========================================
# 3. 侧边栏与主界面
# ==========================================
with st.sidebar:
    st.header("🦁 猎手控制台 (v3.5)")
    
    # 增加 "自选搜索" 选项
    options = list(MARKET_GROUPS.keys()) + ["🔍 自选/搜索 (Custom)"]
    group_choice = st.selectbox("选择战场", options)
    
    target_tickers = []
    
    # 自选逻辑
    if group_choice == "🔍 自选/搜索 (Custom)":
        st.info("💡 输入代码用逗号隔开。如: `NVDA, 600519.SS, 0700.HK`")
        user_input = st.text_area("输入股票代码:", value="NVDA, TSLA, 600519.SS, 0700.HK")
        if user_input:
            # 清洗用户输入，去除空格
            target_tickers = [x.strip() for x in user_input.split(',') if x.strip()]
    else:
        target_tickers = MARKET_GROUPS[group_choice]

    st.divider()
    discount_rate = st.slider("折现率 (Discount Rate)", 6, 15, 9)
    min_upside = st.slider("最低潜在涨幅 (%)", -50, 50, 0)
    st.caption(f"DCF参数: 折现率 {discount_rate}% / 永续 3%")

st.title(f"🌍 全球价值猎手")
if group_choice == "🔍 自选/搜索 (Custom)":
    st.caption("模式：自由狩猎 (Analyzing Custom Portfolio)")
else:
    st.caption(f"模式：{group_choice}")

# 获取数据
if not target_tickers:
    st.warning("请在左侧输入股票代码。")
    st.stop()

raw_df = fetch_financials(target_tickers, group_choice, discount_rate)

if raw_df.empty:
    st.error("⚠️ 数据获取失败。请检查股票代码后缀 (A股 .SS/.SZ, 港股 .HK)")
    st.stop()

df = raw_df[raw_df["潜在涨幅%"] >= min_upside].sort_values(by="潜在涨幅%", ascending=False)

# KPI
c1, c2, c3 = st.columns(3)
with c1: st.metric("🎯 分析数量", f"{len(df)} 支")
with c2:
    if not df.empty:
        best = df.iloc[0]
        st.metric("💎 最佳潜力", best["名称"], f"+{best['潜在涨幅%']}%")
    else: st.metric("💎 最佳潜力", "无")
with c3:
    if not df.empty:
        overvalued = df.sort_values("潜在涨幅%", ascending=True).iloc[0]
        val = overvalued['潜在涨幅%']
        st.metric("⚠️ 最高估/风险", overvalued["名称"], f"{val}%", delta_color="inverse")
    else: st.metric("⚠️ 最高估/风险", "无")

# 表格
st.subheader("📋 估值审计表")
if not df.empty:
    st.dataframe(
        df.drop(columns=["raw_upside"]).style
        .background_gradient(subset=["潜在涨幅%"], cmap="RdYlGn", vmin=-50, vmax=50)
        .background_gradient(subset=["增长假设%"], cmap="Blues")
        .format({"现价": "{:.2f}", "DCF估值": "{:.2f}"}),
        use_container_width=True, height=400, hide_index=True
    )

# 哑铃图
st.divider()
if not df.empty:
    st.subheader("⚖️ 价格 vs 价值 (哑铃图)")
    chart_df = df.head(15).copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=chart_df["现价"], y=chart_df["名称"], mode='markers', name='当前股价', marker=dict(color='#ff4b4b', size=12, symbol='circle')))
    fig.add_trace(go.Scatter(x=chart_df["DCF估值"], y=chart_df["名称"], mode='markers', name='DCF价值', marker=dict(color='#00c853', size=12, symbol='diamond')))
    for i in range(len(chart_df)):
        row = chart_df.iloc[i]
        color = '#00c853' if row['DCF估值'] > row['现价'] else '#ff4b4b'
        fig.add_shape(type="line", x0=row['现价'], y0=row['名称'], x1=row['DCF估值'], y1=row['名称'], line=dict(color=color, width=3))
    fig.update_layout(title="绿钻在右 = 低估(机会) | 绿钻在左 = 高估(风险)", xaxis_title="价格", yaxis=dict(autorange="reversed"), height=600, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)

    st.info("💡 **自选股提示**: 1. 美股直接输代码 (如 `NVDA`); 2. 港股加后缀 (如 `0700.HK`); 3. 上海加 `.SS` (如 `600519.SS`); 4. 深圳加 `.SZ` (如 `000858.SZ`)。")
