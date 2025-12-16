import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值投资超级终端 v8.2", page_icon="🦁", layout="wide")
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
NAME_TO_TICKER = {v: k for k, v in STOCK_MAP.items()}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (AI & Chips)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "TSM", "ASML", "BABA", "PDD"],
    "🇺🇸 美股护城河 (Moat & Value)": ["BRK-B", "V", "MA", "COST", "MCD", "KO", "PEP", "LLY", "NVO", "UNH", "JPM", "JNJ", "PG", "XOM", "CVX", "DIS", "NKE", "O", "WMT"],
    "🇭🇰 港股核心 (High Div & Tech)": ["0700.HK", "9988.HK", "3690.HK", "0388.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK", "1810.HK", "2015.HK"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ", "600036.SS", "601318.SS", "601857.SS", "601225.SS"]
}

def smart_parse_symbol(user_input):
    clean = user_input.strip()
    if clean in NAME_TO_TICKER: return NAME_TO_TICKER[clean]
    code = clean.upper()
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
# 2. 数据获取 (安全赋值模式)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_data(tickers, discount_rate):
    history = []
    snapshot = []
    ADR_FIX = {"PDD": 7.25, "BABA": 7.25, "TSM": 32.5}
    
    progress = st.progress(0)
    for i, raw_sym in enumerate(tickers):
        progress.progress((i + 1) / len(tickers))
        symbol = smart_parse_symbol(raw_sym)
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            inc = stock.income_stmt
            
            cn_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
            mkt_cap = info.get('marketCap', 0)
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            roe = info.get('returnOnEquity', 0) or 0
            gm = info.get('grossMargins', 0) or 0
            
            fcf = info.get('freeCashflow', 0)
            if fcf is None:
                op = info.get('operatingCashflow', 0) or 0
                cap = info.get('capitalExpenditures', 0) or 0
                fcf = op + cap if cap < 0 else op - cap
            
            fix_rate = ADR_FIX.get(symbol, 1.0)
            fcf_usd = fcf / fix_rate
            growth = min(max(info.get('earningsGrowth', 0.05) or 0.05, 0.02), 0.25)
            intrinsic = calculate_dcf(fcf_usd, growth, discount_rate/100)
            upside = (intrinsic - mkt_cap) / mkt_cap if mkt_cap > 0 else 0
            
            # --- 🛠️ 修复核心：分开写，防报错 ---
            item = {}
            item["代码"] = symbol
            item["名称"] = cn_name
            item["现价"] = price
            item["潜在涨幅%"] = round(upside*100, 2)
            item["DCF估值"] = round(price*(1+upside), 2)
            item["ROE%"] = round(roe*100, 2)
            item["毛利率%"] = round(gm*100, 2)
            item["FCF收益率%"] = round((fcf_usd/mkt_cap)*100, 2) if mkt_cap > 0 else 0
            item["市值(B)"] = round(mkt_cap/1e9, 2)
            snapshot.append(item)
            # --------------------------------
            
            if not inc.empty:
                years = inc.columns[:4]
                for d in years:
                    # --- 🛠️ 历史数据也分开写 ---
                    hist_item = {}
                    hist_item["代码"] = symbol
                    hist_item["名称"] = cn_name
                    hist_item["年份"] = d.strftime("%Y")
                    hist_item["营收"] = inc.loc['Total Revenue', d] if 'Total Revenue' in inc.index else 0
                    hist_item["净利润"] = inc.loc['Net Income', d] if 'Net Income' in inc.index else 0
                    
                    if 'Gross Profit' in inc.index and 'Total Revenue' in inc.index:
                        hist_item["毛利率"] = inc.loc['Gross Profit', d] / inc.loc['Total Revenue', d]
                    else:
                        hist_item["毛利率"] = 0
                        
                    history.append(hist_item)
                    # -------------------------
        except: continue
        
    progress.empty()
    return pd.DataFrame(history).iloc[::-1], pd.DataFrame(snapshot)

# ==========================================
# 3. 侧边栏与主逻辑
# ==========================================
with st.sidebar:
    st.header("🦁 超级终端 v8.2")
    app_mode = st.radio("📡 选择模式", ["A. 猎手筛选 (批量)", "B. 巅峰对决 (手动PK)"])
    st.divider()

if app_mode == "A. 猎手筛选 (批量)":
    with st.sidebar:
        options = list(MARKET_GROUPS.keys()) + ["🔍 自选输入"]
        choice = st.selectbox("选择战场", options)
        if choice == "🔍 自选输入":
            st.info("💡 示例: `苹果, 600519`")
            user_txt = st.text_area("输入 (逗号隔开)", "NVDA, TSLA, 600519")
            tickers = [x.strip() for x in user_txt.split(',') if x.strip()]
        else:
            tickers = MARKET_GROUPS[choice]
        dr = st.slider("折现率 (%)", 6, 15, 9)
    st.title("🌍 全球价值猎手")
else:
    with st.sidebar:
        st.info("💡 混输模式: `苹果, 茅台, NVDA`")
        default_txt = "苹果, 微软, 谷歌"
        user_input = st.text_area("输入PK名单:", default_txt, height=100)
        tickers = [x.strip() for x in user_input.split(',') if x.strip()]
        dr = st.slider("折现率 (%)", 6, 15, 9)
    st.title("⚔️ 巅峰对决")

if tickers:
    df_hist, df_val = fetch_data(tickers, dr)
    
    if not df_val.empty:
        df_val = df_val.sort_values("潜在涨幅%", ascending=False)
        
        st.subheader("📸 估值与质量快照")
        fig_dumb = go.Figure()
        fig_dumb.add_trace(go.Scatter(x=df_val["现价"], y=df_val["名称"], mode='markers', name='现价', marker=dict(color='red', size=12)))
        fig_dumb.add_trace(go.Scatter(x=df_val["DCF估值"], y=df_val["名称"], mode='markers', name='估值', marker=dict(color='green', size=12, symbol='diamond')))
        for i in range(len(df_val)):
            r = df_val.iloc[i]
            c = 'green' if r['DCF估值'] > r['现价'] else 'red'
            fig_dumb.add_shape(type="line", x0=r['现价'], y0=r['名称'], x1=r['DCF估值'], y1=r['名称'], line=dict(color=c, width=3))
        fig_dumb.update_layout(title="1. 哑铃图: 价格 vs 价值", height=400, xaxis_title="价格", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_dumb, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            fig_upside = px.bar(df_val, x="名称", y="潜在涨幅%", color="潜在涨幅%", title="2. 潜能排行榜", color_continuous_scale="RdYlGn", text="潜在涨幅%")
            fig_upside.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            st.plotly_chart(fig_upside, use_container_width=True)
        with col2:
            fig_scatter = px.scatter(
                df_val, x="FCF收益率%", y="ROE%", size="市值(B)", color="潜在涨幅%",
                hover_name="名称", text="名称", title="3. 黄金象限 (寻找右上角)",
                labels={"FCF收益率%": "便宜度 (FCF Yield)", "ROE%": "赚钱能力 (ROE)"}, color_continuous_scale="RdYlGn"
            )
            fig_scatter.add_hline(y=15, line_dash="dot", line_color="gray")
            fig_scatter.add_vline(x=4, line_dash="dot", line_color="gray")
            st.plotly_chart(fig_scatter, use_container_width=True)

        st.subheader("📋 详细核心数据")
        st.dataframe(df_val.set_index("名称").style.background_gradient(subset=["潜在涨幅%"], cmap="RdYlGn", vmin=-50, vmax=50), use_container_width=True)

        if app_mode == "B. 巅峰对决 (手动PK)" or "🔍" in str(st.session_state.get('choice', '')):
            st.divider()
            st.subheader("📈 历史趋势厮杀 (最近4年)")
            c1, c2 = st.columns(2)
            with c1: st.plotly_chart(px.line(df_hist, x="年份", y="营收", color="名称", markers=True, title="营收规模"), use_container_width=True)
            with c2: st.plotly_chart(px.line(df_hist, x="年份", y="净利润", color="名称", markers=True, title="利润含金量"), use_container_width=True)
            st.plotly_chart(px.bar(df_hist, x="年份", y="毛利率", color="名称", barmode="group", title="护城河对比 (毛利率)"), use_container_width=True)
    else:
        st.warning("暂无数据，请检查输入。")
