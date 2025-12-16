import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值投资超级终端 v7.0 (图表增强版)", page_icon="🦁", layout="wide")
st.markdown("""<style>.stApp {background-color: #f8f9fa;} .big-font {font-size:20px !important; font-weight: bold;} div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}</style>""", unsafe_allow_html=True)

# ==========================================
# 1. 智能解析与数据字典
# ==========================================
STOCK_MAP = {
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊", "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威",
    "TSM": "台积电", "ASML": "阿斯麦", "BABA": "阿里(美)", "PDD": "拼多多", "JD": "京东", "BIDU": "百度", "NTES": "网易",
    "BRK-B": "伯克希尔", "V": "Visa", "MA": "万事达", "COST": "开市客", "MCD": "麦当劳", "KO": "可口可乐", "PEP": "百事", "LLY": "礼来",
    "NVO": "诺和诺德", "UNH": "联合健康", "JPM": "摩根大通", "JNJ": "强生", "PG": "宝洁", "XOM": "埃克森", "CVX": "雪佛龙", "DIS": "迪士尼",
    "0700.HK": "腾讯", "9988.HK": "阿里(港)", "3690.HK": "美团", "0388.HK": "港交所", "0941.HK": "中移动", "0883.HK": "中海油",
    "1299.HK": "友邦", "0005.HK": "汇丰", "1088.HK": "神华", "1810.HK": "小米", "2015.HK": "理想", "0981.HK": "中芯国际",
    "600519.SS": "茅台", "000858.SZ": "五粮液", "600900.SS": "长电", "300750.SZ": "宁德时代", "002594.SZ": "比亚迪", "600660.SS": "福耀",
    "300760.SZ": "迈瑞", "600036.SS": "招行", "601318.SS": "平安", "601857.SS": "中石油", "601225.SS": "陕煤", "000792.SZ": "盐湖"
}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (AI & Chips)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "TSM", "ASML", "BABA", "PDD"],
    "🇺🇸 美股护城河 (Moat & Value)": ["BRK-B", "V", "MA", "COST", "MCD", "KO", "PEP", "LLY", "NVO", "UNH", "JPM", "JNJ", "PG", "XOM", "CVX", "DIS", "NKE", "O", "WMT"],
    "🇭🇰 港股核心 (High Div & Tech)": ["0700.HK", "9988.HK", "3690.HK", "0388.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK", "1810.HK", "2015.HK"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ", "600036.SS", "601318.SS", "601857.SS", "601225.SS"]
}

def smart_parse_symbol(user_input):
    """智能代码识别"""
    code = user_input.strip().upper()
    if code.isdigit():
        if len(code) == 6 and code.startswith('6'): return f"{code}.SS"
        if len(code) == 6 and (code.startswith('0') or code.startswith('3')): return f"{code}.SZ"
        if len(code) == 4: return f"{code}.HK"
        if len(code) == 5 and code.startswith('0'): return f"{code[1:]}.HK"
    return code

def calculate_dcf(fcf, growth_rate, discount_rate, terminal_rate=0.03, years=10):
    if fcf <= 0: return 0
    future_flows = []
    for i in range(1, years + 1):
        flow = fcf * ((1 + growth_rate) ** i)
        discounted = flow / ((1 + discount_rate) ** i)
        future_flows.append(discounted)
    terminal_val = (fcf * ((1 + growth_rate) ** years) * (1 + terminal_rate)) / (discount_rate - terminal_rate)
    discounted_terminal = terminal_val / ((1 + discount_rate) ** years)
    return sum(future_flows) + discounted_terminal

# ==========================================
# 2. 数据获取 (统一接口)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_data(tickers, discount_rate):
    """拉取数据"""
    financials_history = []
    valuation_snapshot = []
    ADR_FIX = {"PDD": 7.25, "BABA": 7.25, "TSM": 32.5}
    
    progress = st.progress(0)
    
    for i, raw_sym in enumerate(tickers):
        progress.progress((i + 1) / len(tickers))
        symbol = smart_parse_symbol(raw_sym)
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            inc = stock.income_stmt
            
            # 基础信息
            cn_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
            mkt_cap = info.get('marketCap', 0)
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            roe = info.get('returnOnEquity', 0) or 0
            gm = info.get('grossMargins', 0) or 0
            
            # FCF
            fcf = info.get('freeCashflow', 0)
            if fcf is None:
                op = info.get('operatingCashflow', 0) or 0
                cap = info.get('capitalExpenditures', 0) or 0
                fcf = op + cap if cap < 0 else op - cap
            
            # DCF
            fix_rate = ADR_FIX.get(symbol, 1.0)
            fcf_usd = fcf / fix_rate
            growth = min(max(info.get('earningsGrowth', 0.05) or 0.05, 0.02), 0.25)
            intrinsic = calculate_dcf(fcf_usd, growth, discount_rate/100)
            upside = (intrinsic - mkt_cap) / mkt_cap if mkt_cap > 0 else 0
            
            valuation_snapshot.append({
                "代码": symbol, "名称": cn_name, "现价": price, 
                "潜在涨幅%": round(upside*100, 2), "DCF估值": round(price*(1+upside), 2),
                "ROE%": round(roe*100, 2), "毛利率%": round(gm*100, 2),
                "FCF收益率%": round((fcf_usd/mkt_cap)*100, 2) if mkt_cap>0 else 0,
                "市值(B)": round(mkt_cap/1e9, 2)
            })
            
            # 历史趋势 (仅前4年)
            if not inc.empty:
                years = inc.columns[:4]
                for d in years:
                    financials_history.append({
                        "代码": symbol, "名称": cn_name, "年份": d.strftime("%Y"),
                        "营收": inc.loc['Total Revenue', d] if 'Total Revenue' in inc.index else 0,
                        "净利润": inc.loc['Net Income', d] if 'Net Income' in inc.index else 0,
                        "毛利率": (inc.loc['Gross Profit', d] / inc.loc['Total Revenue', d]) if 'Gross Profit' in inc.index and 'Total Revenue' in inc.index else 0
                    })
        except: continue
        
    progress.empty()
    return pd.DataFrame(financials_history).iloc[::-1], pd.DataFrame(valuation_snapshot)

# ==========================================
# 3. 侧边栏与主逻辑
# ==========================================
with st.sidebar:
    st.header("🦁 超级终端 v7.0")
    app_mode = st.radio("📡 选择模式", ["A. 猎手筛选 (批量)", "B. 巅峰对决 (手动PK)"])
    st.divider()

if app_mode == "A. 猎手筛选 (批量)":
    with st.sidebar:
        options = list(MARKET_GROUPS.keys()) + ["🔍 自选输入"]
        choice = st.selectbox("选择战场", options)
        if choice == "🔍 自选输入":
            user_txt = st.text_area("输入代码 (逗号隔开)", "NVDA, TSLA, 600519")
            tickers = [x.strip() for x in user_txt.split(',') if x.strip()]
        else:
            tickers = MARKET_GROUPS[choice]
        dr = st.slider("折现率 (%)", 6, 15, 9)

    st.title("🌍 全球价值猎手")
    if tickers:
        df_hist, df_val = fetch_data(tickers, dr)
        
        if not df_val.empty:
            df_val = df_val.sort_values("潜在涨幅%", ascending=False)
            
            # --- 1. 估值哑铃图 ---
            st.subheader("⚖️ 1. 价格 vs 价值 (哑铃图)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_val["现价"], y=df_val["名称"], mode='markers', name='现价', marker=dict(color='red', size=10)))
            fig.add_trace(go.Scatter(x=df_val["DCF估值"], y=df_val["名称"], mode='markers', name='估值', marker=dict(color='green', size=10, symbol='diamond')))
            for i in range(len(df_val)):
                r = df_val.iloc[i]
                c = 'green' if r['DCF估值'] > r['现价'] else 'red'
                fig.add_shape(type="line", x0=r['现价'], y0=r['名称'], x1=r['DCF估值'], y1=r['名称'], line=dict(color=c, width=2))
            fig.update_layout(height=400, xaxis_title="价格", yaxis=dict(autorange="reversed"), margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

            # --- 2. 猎手看板 (新增) ---
            st.subheader("📊 2. 猎手可视化看板")
            col1, col2 = st.columns(2)
            
            with col1:
                # 潜能排行榜
                fig_upside = px.bar(
                    df_val, x="名称", y="潜在涨幅%", color="潜在涨幅%",
                    title="🚀 潜能排行榜 (谁被低估最多?)",
                    color_continuous_scale="RdYlGn",
                    text="潜在涨幅%"
                )
                fig_upside.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                st.plotly_chart(fig_upside, use_container_width=True)
                
            with col2:
                # 黄金象限：ROE vs FCF Yield
                fig_scatter = px.scatter(
                    df_val, x="FCF收益率%", y="ROE%", size="市值(B)", color="潜在涨幅%",
                    hover_name="名称", text="名称",
                    title="💎 黄金象限 (寻找右上角的优质股)",
                    labels={"FCF收益率%": "便宜程度 (FCF Yield)", "ROE%": "赚钱能力 (ROE)"},
                    color_continuous_scale="RdYlGn"
                )
                # 加辅助线
                fig_scatter.add_hline(y=15, line_dash="dot", line_color="gray", annotation_text="优质线(ROE>15%)")
                fig_scatter.add_vline(x=4, line_dash="dot", line_color="gray", annotation_text="低估线(Yield>4%)")
                st.plotly_chart(fig_scatter, use_container_width=True)

            # --- 3. 护城河对比 ---
            st.subheader("🏰 3. 护城河对比 (毛利率)")
            df_margin = df_val.sort_values("毛利率%", ascending=False)
            fig_margin = px.bar(
                df_margin, x="名称", y="毛利率%", color="毛利率%",
                title="谁的生意最暴利? (毛利率越高越好)",
                color_continuous_scale="Blues"
            )
            st.plotly_chart(fig_margin, use_container_width=True)

            # 数据表
            st.subheader("📋 详细数据表")
            st.dataframe(df_val.style.background_gradient(subset=["潜在涨幅%"], cmap="RdYlGn", vmin=-50, vmax=50), use_container_width=True)
        else:
            st.warning("暂无数据")

else:
    # --- Mode B: 巅峰对决 ---
    with st.sidebar:
        st.info("💡 输入代码用逗号隔开")
        user_input = st.text_area("输入PK名单:", "NVDA, AMD, INTC", height=100)
        target_list = [x.strip() for x in user_input.split(',') if x.strip()]
        dr_pk = st.slider("折现率 (%)", 6, 15, 9)

    st.title("⚔️ 巅峰对决")
    if target_list:
        df_hist, df_val = fetch_data(target_list, dr_pk)
        if not df_val.empty:
            st.subheader("1. 核心指标 PK")
            st.dataframe(
                df_val.set_index("名称").style
                .highlight_max(subset=["潜在涨幅%", "ROE%", "毛利率%", "FCF收益率%"], color='lightgreen')
                .highlight_min(subset=["潜在涨幅%", "ROE%", "毛利率%"], color='pink')
                .format({"市值(B)": "{:.2f}", "潜在涨幅%": "{:.2f}"}),
                use_container_width=True
            )
            
            st.subheader("2. 趋势厮杀")
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(px.line(df_hist, x="年份", y="营收", color="名称", markers=True, title="营收成长性"), use_container_width=True)
            with c2:
                st.plotly_chart(px.line(df_hist, x="年份", y="净利润", color="名称", markers=True, title="利润含金量"), use_container_width=True)
        else:
            st.error("数据获取失败")
