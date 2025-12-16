import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值猎手 v3.0 (机构版)", page_icon="🦁", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    div[data-testid="stDataFrame"] {font-size: 14px;}
    .big-font {font-size:20px !important; font-weight: bold;}
    .metric-card {background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 2px 2px 10px rgba(0,0,0,0.05);}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 核心股票池 (保持不变)
# ==========================================
STOCK_MAP = {
    # --- 🇺🇸 美股科技 ---
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊",
    "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威",
    "INTC": "英特尔", "BABA": "阿里(美)", "PDD": "拼多多",
    # --- 🇺🇸 美股价值 ---
    "BRK-B": "伯克希尔", "JPM": "摩根大通", "KO": "可口可乐", "JNJ": "强生",
    "PG": "宝洁", "XOM": "埃克森", "MCD": "麦当劳", "DIS": "迪士尼",
    "NKE": "耐克", "O": "Realty Income", "PFE": "辉瑞",
    # --- 🇭🇰 港股核心 ---
    "0700.HK": "腾讯", "9988.HK": "阿里(港)", "3690.HK": "美团",
    "0941.HK": "中移动", "0883.HK": "中海油", "1299.HK": "友邦",
    "0005.HK": "汇丰", "1088.HK": "神华",
    # --- 🇨🇳 A股核心 ---
    "600519.SS": "茅台", "000858.SZ": "五粮液", "600036.SS": "招行",
    "002594.SZ": "比亚迪", "000792.SZ": "盐湖", "601318.SS": "平安",
    "601857.SS": "中石油", "600900.SS": "长电", "600030.SS": "中信"
}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (MAG 7)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "INTC", "BABA", "PDD"],
    "🇺🇸 美股价值 (Buffett)": ["BRK-B", "JPM", "KO", "JNJ", "PG", "XOM", "MCD", "DIS", "NKE", "O", "PFE"],
    "🇭🇰 港股核心 (高股息)": ["0700.HK", "9988.HK", "3690.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK"],
    "🇨🇳 A股核心 (核心资产)": ["600519.SS", "000858.SZ", "600036.SS", "002594.SZ", "000792.SZ", "601318.SS", "601857.SS", "600900.SS", "600030.SS"]
}

# ==========================================
# 2. 深度数据获取 (引入 valuation 逻辑)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_financials(group_name):
    tickers = MARKET_GROUPS[group_name]
    data_list = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(tickers):
        cn_name = STOCK_MAP.get(symbol, symbol)
        status_text.text(f"🔍 深度审计: {cn_name} ({symbol}) ...")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # --- 1. 基础数据 ---
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            mkt_cap = info.get('marketCap', 0)
            
            # --- 2. 商业模式 (Business Model) ---
            # ROE: 资本效率
            roe = info.get('returnOnEquity', 0) or 0
            # 净利率: 最终落袋的能力
            net_margin = info.get('profitMargins', 0) or 0
            
            # --- 3. 护城河 (Moat) ---
            # 毛利率: 议价权
            gross_margin = info.get('grossMargins', 0) or 0
            
            # --- 4. 现金流与估值 (DCF Logic) ---
            # 获取自由现金流 (FCF)
            fcf = info.get('freeCashflow', 0)
            if fcf is None: # 降级策略
                fcf = info.get('operatingCashflow', 0) - (info.get('capitalExpenditures', 0) or 0)
            
            # 计算 FCF Yield (FCF收益率) = FCF / 市值
            # 含义：假设买下全公司，每年的现金回报率。类似债券收益率。
            # 这是 DCF 估值的快速代理指标。
            fcf_yield = (fcf / mkt_cap) if mkt_cap > 0 else 0
            
            # 市现率 P/FCF
            p_fcf = (mkt_cap / fcf) if fcf > 0 else 999
            
            # --- 5. 股息 (Dividend) ---
            div_yield = info.get('dividendYield', 0) or 0
            
            # 综合评分 (简单加权算法，仅供参考)
            # 满分100，侧重现金流和ROE
            score = (roe * 100 * 0.3) + (gross_margin * 100 * 0.2) + (fcf_yield * 100 * 2 * 0.4) + (div_yield * 100 * 0.1)

            data_list.append({
                "代码": symbol,
                "名称": cn_name,
                "现价": price,
                "ROE%": round(roe * 100, 2),
                "净利率%": round(net_margin * 100, 2), # Business Model
                "毛利率%": round(gross_margin * 100, 2), # Moat
                "FCF收益率%": round(fcf_yield * 100, 2), # DCF/Valuation
                "市现率(P/FCF)": round(p_fcf, 1),
                "股息率%": round(div_yield * 100, 2),
                "综合评分": round(score, 1),
                # 原始数据用于计算
                "raw_mkt_cap": mkt_cap,
                "raw_fcf": fcf
            })
        except Exception:
            continue
            
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(data_list)

# ==========================================
# 3. 侧边栏：四大支柱筛选
# ==========================================
with st.sidebar:
    st.header("🦁 猎手参数设置 (Pro)")
    group_choice = st.selectbox("战场", list(MARKET_GROUPS.keys()))
    st.divider()
    
    st.subheader("1️⃣ 商业模式 (赚钱能力)")
    min_roe = st.slider("最低 ROE (%)", 0, 40, 15, help="低于15%通常不是好生意")
    min_net_margin = st.slider("最低 净利率 (%)", 0, 50, 10, help="排除只赚吆喝不赚钱的企业")
    
    st.subheader("2️⃣ 护城河 (竞争壁垒)")
    min_gm = st.slider("最低 毛利率 (%)", 0, 90, 30, help="高毛利通常代表定价权")
    
    st.subheader("3️⃣ 估值 (现金流折现)")
    min_fcf_yield = st.slider("最低 FCF收益率 (%)", -5.0, 15.0, 3.0, step=0.5, 
                              help="核心指标！类似债券收益率。大于4%通常被认为有吸引力(对比美债)。")
    
    st.subheader("4️⃣ 股东回报")
    min_div = st.slider("最低 股息率 (%)", 0.0, 10.0, 0.0, step=0.5)

# ==========================================
# 4. 主逻辑与展示
# ==========================================
st.title(f"🌍 全球价值猎手: {group_choice}")
st.markdown("### 核心逻辑：商业模式 + 护城河 + 现金流折现(FCF Yield) + 股息")

raw_df = fetch_financials(group_choice)

if raw_df.empty:
    st.error("数据获取失败，请重试")
    st.stop()

# 筛选
df = raw_df[
    (raw_df["ROE%"] >= min_roe) &
    (raw_df["净利率%"] >= min_net_margin) &
    (raw_df["毛利率%"] >= min_gm) &
    (raw_df["FCF收益率%"] >= min_fcf_yield) &
    (raw_df["股息率%"] >= min_div)
].copy()

# 排序逻辑：默认按“综合评分”降序
df = df.sort_values(by="综合评分", ascending=False)

# --- 概览指标卡片 ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("狩猎目标数", f"{len(df)} / {len(raw_df)}")
with col2:
    if not df.empty:
        top_stock = df.iloc[0]["名称"]
        st.metric("评分最高", top_stock)
    else:
        st.metric("评分最高", "无")
with col3:
    if not df.empty:
        cash_king = df.sort_values("FCF收益率%", ascending=False).iloc[0]["名称"]
        st.metric("现金流之王", cash_king)
    else:
        st.metric("现金流之王", "无")
with col4:
    st.metric("筛选标准", "4大支柱")

# --- 主数据表 ---
st.subheader("🏆 幸存者名单")

if not df.empty:
    # 样式配置
    format_dict = {"现价": "{:.2f}"}
    
    # 动态高亮
    st.dataframe(
        df.drop(columns=["raw_mkt_cap", "raw_fcf"]).style
        .background_gradient(subset=["FCF收益率%"], cmap="Greens") # 现金流越好越绿
        .background_gradient(subset=["毛利率%"], cmap="Blues")   # 护城河越深越蓝
        .bar(subset=["综合评分"], color='#ffaa00')
        .format(format_dict),
        use_container_width=True,
        height=500,
        hide_index=True
    )
else:
    st.warning("🧹 没有股票符合如此严格的【巴菲特级】标准。请尝试降低【FCF收益率】或【毛利率】要求。")

# --- 高级可视化 ---
st.divider()

if not df.empty:
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("💎 价值象限：估值 vs 质量")
        # X轴：ROE (质量)，Y轴：FCF Yield (估值性价比)
        fig = px.scatter(
            df,
            x="ROE%",
            y="FCF收益率%",
            size="毛利率%", # 气泡大小代表护城河
            color="综合评分",
            hover_name="名称",
            text="名称",
            title="右上角为【高回报+便宜】的黄金机会",
            labels={"ROE%": "商业模式 (ROE)", "FCF收益率%": "估值吸引力 (FCF Yield)"}
        )
        # 添加辅助线：FCF Yield = 4% (美债参考线)
        fig.add_hline(y=4, line_dash="dash", line_color="red", annotation_text="无风险收益基准 (4%)")
        fig.update_traces(textposition='top center')
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("🏰 护城河深度分析")
        # 堆叠图或分组柱状图：展示毛利和净利的关系
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            y=df["名称"], x=df["毛利率%"], name="毛利率 (壁垒)", orientation='h', marker_color='#636EFA'
        ))
        fig2.add_trace(go.Bar(
            y=df["名称"], x=df["净利率%"], name="净利率 (真钱)", orientation='h', marker_color='#00CC96'
        ))
        
        fig2.update_layout(
            barmode='overlay', 
            title="毛利率 vs 净利率 (差距越小管理越优)",
            xaxis_title="百分比 %"
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.info("""
    **💡 指标深度解读：**
    1. **FCF收益率 (FCF Yield)**: 
       - 计算公式：自由现金流 / 市值。
       - 它是**未来现金流折现 (DCF)** 的简化实战版。
       - 如果 FCF Yield > 5%，说明在当前价格买入，仅靠现金流回报就已超过大多数理财产品，估值较低。
    2. **毛利率 vs 净利率**: 
       - 只有高毛利没有高净利？说明管理费用太高，商业模式可能有漏洞。
    """)
