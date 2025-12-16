import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值猎手 v3.3", page_icon="🦁", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    div[data-testid="stDataFrame"] {font-size: 14px;}
    .big-font {font-size:20px !important; font-weight: bold;}
    div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 核心股票池
# ==========================================
STOCK_MAP = {
    # --- 🇺🇸 美股 ---
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊",
    "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威",
    "TSM": "台积电", "ASML": "阿斯麦", "CRM": "赛富时", "ORCL": "甲骨文",
    "INTC": "英特尔", "BABA": "阿里(美)", "PDD": "拼多多",
    "BRK-B": "伯克希尔", "V": "Visa", "MA": "万事达", "COST": "开市客",
    "MCD": "麦当劳", "KO": "可口可乐", "PEP": "百事", "LLY": "礼来",
    "NVO": "诺和诺德", "UNH": "联合健康", "JPM": "摩根大通", "JNJ": "强生",
    "PG": "宝洁", "XOM": "埃克森", "CVX": "雪佛龙", "DIS": "迪士尼",
    "NKE": "耐克", "O": "Realty Income", "WMT": "沃尔玛",
    
    # --- 🇭🇰 港股 ---
    "0700.HK": "腾讯", "9988.HK": "阿里(港)", "3690.HK": "美团",
    "0388.HK": "港交所", "0941.HK": "中移动", "0883.HK": "中海油",
    "1299.HK": "友邦", "0005.HK": "汇丰", "1088.HK": "神华",
    "1810.HK": "小米", "2015.HK": "理想",

    # --- 🇨🇳 A股 ---
    "600519.SS": "茅台", "000858.SZ": "五粮液", "600900.SS": "长电",
    "300750.SZ": "宁德时代", "002594.SZ": "比亚迪", "600660.SS": "福耀",
    "300760.SZ": "迈瑞", "600036.SS": "招行", "601318.SS": "平安",
    "601857.SS": "中石油", "601225.SS": "陕煤", "000792.SZ": "盐湖",
    "600030.SS": "中信", "600276.SS": "恒瑞"
}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (AI & Chips)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "TSM", "ASML", "INTC", "CRM", "ORCL", "BABA", "PDD"],
    "🇺🇸 美股护城河 (Moat & Value)": ["BRK-B", "V", "MA", "COST", "MCD", "KO", "PEP", "LLY", "NVO", "UNH", "JPM", "JNJ", "PG", "XOM", "CVX", "DIS", "NKE", "O", "WMT"],
    "🇭🇰 港股核心 (High Div & Tech)": ["0700.HK", "9988.HK", "3690.HK", "0388.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK", "1810.HK", "2015.HK"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ", "600036.SS", "601318.SS", "601857.SS", "601225.SS", "000792.SZ", "600030.SS", "600276.SS"]
}

# ==========================================
# 2. 数据获取 (含汇率修正)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_financials(group_name):
    tickers = MARKET_GROUPS[group_name]
    data_list = []
    
    # 汇率修正补丁
    ADR_FIX = {
        "PDD": 7.25, 
        "BABA": 7.25, 
        "BIDU": 7.25, 
        "JD": 7.25, 
        "TSM": 32.5
    }

    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(tickers):
        cn_name = STOCK_MAP.get(symbol, symbol)
        status_text.text(f"🔍 正在估值: {cn_name} ({symbol})...")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # --- 基础数据 ---
            mkt_cap = info.get('marketCap', 0)
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            
            # --- 商业模式 ---
            roe = info.get('returnOnEquity', 0) or 0
            net_margin = info.get('profitMargins', 0) or 0
            
            # --- 现金流修正 ---
            fcf = info.get('freeCashflow', 0)
            # 如果没有直接的FCF数据，尝试手动计算
            if fcf is None: 
                op_cash = info.get('operatingCashflow', 0) or 0
                capex = info.get('capitalExpenditures', 0) or 0 
                # FCF = 经营现金流 + 资本开支 (注意: capex通常是负数)
                fcf = op_cash + capex if capex < 0 else op_cash - capex

            # --- 应用汇率修正 ---
            fix_rate = ADR_FIX.get(symbol, 1.0) 
            
            # --- 核心估值计算 ---
            # FCF Yield = (FCF / 市值) / 汇率
            fcf_yield = ((fcf / mkt_cap) / fix_rate) if mkt_cap > 0 else 0
            
            # P/FCF 回本年限 = (市值 / FCF) * 汇率
            p_fcf = ((mkt_cap / fcf) * fix_rate) if fcf > 0 else 0
            
            div_yield = info.get('dividendYield', 0) or 0

            # 综合评分
            score = (fcf_yield * 100 * 5) + (roe * 100 * 3) + (div_yield * 100 * 2)

            data_list.append({
                "代码": symbol,
                "名称": cn_name,
                "现价": price,
                "ROE%": round(roe * 100, 2),
                "净利率%": round(net_margin * 100, 2),
                "FCF收益率%": round(fcf_yield * 100, 2),
                "回本年限(P/FCF)": round(p_fcf, 1),
                "股息率%": round(div_yield * 100, 2),
                "综合评分": round(score, 1),
                "raw_mkt_cap": mkt_cap
            })
        except Exception:
            continue
            
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(data_list)

# ==========================================
# 3. 侧边栏
# ==========================================
with st.sidebar:
    st.header("🦁 猎手参数 (终极版)")
    group_choice = st.selectbox("选择狩猎战场", list(MARKET_GROUPS.keys()))
    
    st.divider()
    st.subheader("🛠️ 筛选漏斗")
    min_roe = st.slider("最低 ROE (%)", 0, 50, 15)
    min_net_margin = st.slider("最低 净利率 (%)", 0, 60, 10)
    min_fcf_yield = st.slider("最低 FCF收益率 (%)", -2.0, 10.0, 2.5)
    
    st.info("✅ 汇率补丁已激活 (PDD/BABA/TSM 数据已修正)")

# ==========================================
# 4. 主界面
# ==========================================
st.title(f"🌍 全球价值猎手: {group_choice}")
st.caption("核心视角：【商业模式】有多性感 vs 【现在股价】有多划算")

raw_df = fetch_financials(group_choice)

if raw_df.empty:
    st.error("⚠️ 数据获取失败，请重试")
    st.stop()

# 筛选与排序
df = raw_df[
    (raw_df["ROE%"] >= min_roe) &
    (raw_df["净利率%"] >= min_net_margin) &
    (raw_df["FCF收益率%"] >= min_fcf_yield)
].sort_values(by="综合评分", ascending=False)

# KPI
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("🎯 幸存名单", f"{len(df)} / {len(raw_df)}")
with c2:
    if not df.empty:
        valid_p_fcf = df[df["回本年限(P/FCF)"] > 0]
        if not valid_p_fcf.empty:
            best_val = valid_p_fcf.sort_values("回本年限(P/FCF)").iloc[0]
            st.metric("💰 性价比之王", best_val["名称"], f"{best_val['回本年限(P/FCF)']}年")
        else: st.metric("💰 性价比之王", "无")
with c3:
    if not df.empty:
        best_biz = df.sort_values("ROE%", ascending=False).iloc[0]
        st.metric("🔥 赚钱机器", best_biz["名称"], f"ROE {best_biz['ROE%']}%")

# 列表
st.subheader("📋 深度估值审计表")
if not df.empty:
    st.dataframe(
        df.drop(columns=["raw_mkt_cap"]).style
        .background_gradient(subset=["FCF收益率%"], cmap="Greens")
        .background_gradient(subset=["回本年限(P/FCF)"], cmap="RdYlGn_r")
        .background_gradient(subset=["ROE%"], cmap="Reds")
        .format({"现价": "{:.2f}"}),
        use_container_width=True, height=400, hide_index=True
    )
else:
    st.warning("🧹 暂无符合条件的股票。")

# 可视化
st.divider()
if not df.empty:
    st.subheader("⚖️ 核心对决：股价 vs (商业价值+现金流)")
    col1, col2 = st.columns([3, 2])
    
    with col1:
        fig1 = px.scatter(
            df, x="ROE%", y="FCF收益率%", size="净利率%", color="回本年限(P/FCF)",
            color_continuous_scale="RdYlGn_r", hover_name="名称", text="名称",
            title="⬇️左下(贵且差) ⻠ ↗️右上(便宜且好)",
            labels={"ROE%": "商业价值 (ROE) →", "FCF收益率%": "现金回报率 (Yield) ↑"},
            height=550
        )
        fig1.add_hline(y=4.0, line_dash="dot", line_color="green", opacity=0.6)
        fig1.add_vline(x=15.0, line_dash="dot", line_color="red", opacity=0.6)
        fig1.add_shape(type="rect", x0=15, y0=4, x1=df["ROE%"].max()*1.05, y1=df["FCF收益率%"].max()*1.05,
            line=dict(color="rgba(0,0,0,0)"), fillcolor="rgba(0,255,0,0.1)", layer="below")
        fig1.update_traces(textposition='top center')
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("⏳ 回本年限排行榜")
        chart_df = df[(df["回本年限(P/FCF)"] > 0) & (df["回本年限(P/FCF)"] < 80)].sort_values("回本年限(P/FCF)").head(15)
        fig2 = px.bar(
            chart_df, x="回本年限(P/FCF)", y="名称", orientation='h', text="回本年限(P/FCF)",
            color="回本年限(P/FCF)", color_continuous_scale="RdYlGn_r",
            title="越短越便宜"
        )
        fig2.update_layout(xaxis_title="", yaxis_title="", yaxis={'categoryorder':'total descending'}, height=550)
        fig2.update_traces(texttemplate='%{text:.1f}年', textposition='outside')
        st.plotly_chart(fig2, use_container_width=True)

    st.info("💡 **提示**: 气泡颜色越绿，代表回本越快（便宜）；位置越靠右上，代表生意越好且价格越低。")
