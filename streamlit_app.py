import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值投资超级终端 v5.1", page_icon="🦁", layout="wide")
st.markdown("""<style>.stApp {background-color: #f8f9fa;} .big-font {font-size:20px !important; font-weight: bold;} div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}</style>""", unsafe_allow_html=True)

# ==========================================
# 1. 全局数据字典
# ==========================================
STOCK_MAP = {
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊", "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威",
    "TSM": "台积电", "ASML": "阿斯麦", "CRM": "赛富时", "ORCL": "甲骨文", "INTC": "英特尔", "BABA": "阿里(美)", "PDD": "拼多多",
    "BRK-B": "伯克希尔", "V": "Visa", "MA": "万事达", "COST": "开市客", "MCD": "麦当劳", "KO": "可口可乐", "PEP": "百事", "LLY": "礼来",
    "NVO": "诺和诺德", "UNH": "联合健康", "JPM": "摩根大通", "JNJ": "强生", "PG": "宝洁", "XOM": "埃克森", "CVX": "雪佛龙", "DIS": "迪士尼",
    "NKE": "耐克", "O": "Realty Income", "WMT": "沃尔玛",
    "0700.HK": "腾讯", "9988.HK": "阿里(港)", "3690.HK": "美团", "0388.HK": "港交所", "0941.HK": "中移动", "0883.HK": "中海油",
    "1299.HK": "友邦", "0005.HK": "汇丰", "1088.HK": "神华", "1810.HK": "小米", "2015.HK": "理想",
    "600519.SS": "茅台", "000858.SZ": "五粮液", "600900.SS": "长电", "300750.SZ": "宁德时代", "002594.SZ": "比亚迪", "600660.SS": "福耀",
    "300760.SZ": "迈瑞", "600036.SS": "招行", "601318.SS": "平安", "601857.SS": "中石油", "601225.SS": "陕煤", "000792.SZ": "盐湖",
    "600030.SS": "中信", "600276.SS": "恒瑞"
}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (AI & Chips)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "TSM", "ASML", "INTC", "CRM", "ORCL", "BABA", "PDD"],
    "🇺🇸 美股护城河 (Moat & Value)": ["BRK-B", "V", "MA", "COST", "MCD", "KO", "PEP", "LLY", "NVO", "UNH", "JPM", "JNJ", "PG", "XOM", "CVX", "DIS", "NKE", "O", "WMT"],
    "🇭🇰 港股核心 (High Div & Tech)": ["0700.HK", "9988.HK", "3690.HK", "0388.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK", "1810.HK", "2015.HK"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ", "600036.SS", "601318.SS", "601857.SS", "601225.SS", "000792.SZ", "600030.SS", "600276.SS"]
}

# ==========================================
# 2. 通用计算函数
# ==========================================
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

@st.cache_data(ttl=3600)
def fetch_batch_data(ticker_list, discount_rate):
    """批量获取数据 (安全赋值版)"""
    data = []
    ADR_FIX = {"PDD": 7.25, "BABA": 7.25, "TSM": 32.5}
    progress = st.progress(0)
    
    for i, symbol in enumerate(ticker_list):
        progress.progress((i + 1) / len(ticker_list))
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            cn_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
            
            mkt_cap = info.get('marketCap', 0)
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            roe = info.get('returnOnEquity', 0) or 0
            
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
            
            # --- 安全赋值区 (防止括号不匹配) ---
            item = {}
            item["代码"] = symbol
            item["名称"] = cn_name
            item["现价"] = price
            item["潜在涨幅%"] = round(upside * 100, 2)
            item["ROE%"] = round(roe * 100, 2)
            item["FCF收益率%"] = round((fcf_usd / mkt_cap) * 100, 2) if mkt_cap > 0 else 0
            item["DCF估值"] = round(price * (1 + upside), 2)
            
            data.append(item)
            # --------------------------------
            
        except: continue
    progress.empty()
    return pd.DataFrame(data)

@st.cache_data(ttl=3600)
def fetch_deep_data(ticker):
    """深度数据获取"""
    try:
        stock = yf.Ticker(ticker)
        inc = stock.income_stmt
        bal = stock.balance_sheet
        cf = stock.cashflow
        info = stock.info
        
        years = inc.columns[:4]
        res = []
        for d in years:
            # --- 安全赋值区 ---
            record = {}
            record["年份"] = d.strftime("%Y")
            record["营收"] = inc.loc['Total Revenue', d] if 'Total Revenue' in inc.index else 0
            record["净利润"] = inc.loc['Net Income', d] if 'Net Income' in inc.index else 0
            record["应收"] = bal.loc['Receivables', d] if 'Receivables' in bal.index else 0
            record["存货"] = bal.loc['Inventory', d] if 'Inventory' in bal.index else 0
            record["经营现金流"] = cf.loc['Operating Cash Flow', d] if 'Operating Cash Flow' in cf.index else 0
            res.append(record)
            # ----------------
            
        return pd.DataFrame(res).iloc[::-1], info
    except: return pd.DataFrame(), {}

# ==========================================
# 3. 侧边栏与主逻辑
# ==========================================
with st.sidebar:
    st.header("🦁 超级终端 v5.1")
    app_mode = st.radio("📡 选择模式", ["A. 全球猎手 (批量筛选)", "B. 深度审计 (个股排雷)"])
    st.divider()

if app_mode == "A. 全球猎手 (批量筛选)":
    # --- 模式 A 逻辑 ---
    with st.sidebar:
        options = list(MARKET_GROUPS.keys()) + ["🔍 自选输入"]
        choice = st.selectbox("选择战场", options)
        if choice == "🔍 自选输入":
            user_txt = st.text_area("输入代码 (逗号隔开)", "NVDA, TSLA, 600519.SS")
            tickers = [x.strip() for x in user_txt.split(',') if x.strip()]
        else:
            tickers = MARKET_GROUPS[choice]
        dr = st.slider("折现率 (%)", 6, 15, 9)

    st.title("🌍 全球价值猎手")
    if tickers:
        df = fetch_batch_data(tickers, dr)
        if not df.empty:
            df = df.sort_values("潜在涨幅%", ascending=False)
            
            st.subheader("⚖️ 价格 vs 价值 (哑铃图)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["现价"], y=df["名称"], mode='markers', name='现价', marker=dict(color='red', size=10)))
            fig.add_trace(go.Scatter(x=df["DCF估值"], y=df["名称"], mode='markers', name='估值', marker=dict(color='green', size=10)))
            for i in range(len(df)):
                r = df.iloc[i]
                c = 'green' if r['DCF估值'] > r['现价'] else 'red'
                fig.add_shape(type="line", x0=r['现价'], y0=r['名称'], x1=r['DCF估值'], y1=r['名称'], line=dict(color=c, width=2))
            fig.update_layout(height=500, xaxis_title="价格", yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(df.style.background_gradient(subset=["潜在涨幅%"], cmap="RdYlGn", vmin=-50, vmax=50), use_container_width=True)

else:
    # --- 模式 B 逻辑 ---
    with st.sidebar:
        symbol = st.text_input("输入单个代码", "NVDA").upper().strip()
        dr_deep = st.slider("折现率 (%)", 6, 15, 9)
        g_deep = st.slider("增长率假设 (%)", 0, 30, 15)

    st.title(f"🔬 深度审计: {symbol}")
    if symbol:
        df_fin, info = fetch_deep_data(symbol)
        if not df_fin.empty:
            roe = info.get('returnOnEquity', 0)
            gm = info.get('grossMargins', 0)
            c1, c2, c3 = st.columns(3)
            c1.metric("ROE", f"{roe*100:.2f}%")
            c2.metric("毛利率", f"{gm*100:.2f}%")
            
            st.subheader("📊 财务雷达 (4年趋势)")
            col_a, col_b = st.columns(2)
            with col_a:
                fig1 = go.Figure()
                fig1.add_trace(go.Bar(x=df_fin['年份'], y=df_fin['营收'], name='营收', marker_color='lightblue'))
                fig1.add_trace(go.Bar(x=df_fin['年份'], y=df_fin['应收'], name='应收', marker_color='orange'))
                fig1.update_layout(title="营收 vs 应收 (橙柱过高需警惕)")
                st.plotly_chart(fig1, use_container_width=True)
            with col_b:
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(x=df_fin['年份'], y=df_fin['净利润'], name='净利润', marker_color='lightgreen'))
                fig2.add_trace(go.Bar(x=df_fin['年份'], y=df_fin['经营现金流'], name='现金流', marker_color='darkgreen'))
                fig2.update_layout(barmode='overlay', title="利润 vs 现金流 (深绿覆盖浅绿为优)")
                st.plotly_chart(fig2, use_container_width=True)

            st.subheader("💰 DCF 估值")
            last_fcf = df_fin['经营现金流'].iloc[-1]
            val = calculate_dcf(last_fcf, g_deep/100, dr_deep/100)
            mkt = info.get('marketCap', 1)
            up = (val - mkt) / mkt
            k1, k2 = st.columns(2)
            k1.metric("理论估值", f"{val/1e9:.2f} B")
            k2.metric("潜在涨幅", f"{up*100:.2f}%", delta_color="normal" if up>0 else "inverse")
        else:
            st.error("无法获取数据，请检查代码。")
