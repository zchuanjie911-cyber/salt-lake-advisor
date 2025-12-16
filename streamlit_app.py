import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots # 引入双轴图表支持
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值投资超级终端 v11.2 (审计加强版)", page_icon="🕵️", layout="wide")
st.markdown("""<style>.stApp {background-color: #f8f9fa;} .big-font {font-size:20px !important; font-weight: bold;} div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}</style>""", unsafe_allow_html=True)

# ==========================================
# 1. 数据字典与智能识别
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
# 2. 极速数据获取
# ==========================================
def get_stock_basic_info(symbol):
    try:
        t = yf.Ticker(symbol)
        i = t.info
        return {
            "名称": STOCK_MAP.get(symbol, symbol),
            "市值(B)": (i.get('marketCap', 0) or 0)/1e9,
            "毛利率%": (i.get('grossMargins', 0) or 0)*100,
            "营收增长%": (i.get('revenueGrowth', 0) or 0)*100
        }
    except: return None

@st.cache_data(ttl=3600)
def fetch_deep_data_concurrent(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        inc = stock.income_stmt
        bal = stock.balance_sheet
        cf = stock.cashflow
        
        biz = {
            "ROE": info.get('returnOnEquity', 0),
            "毛利率": info.get('grossMargins', 0),
            "净利率": info.get('profitMargins', 0)
        }
        
        history = []
        if not inc.empty:
            years = inc.columns[:5]
            for d in years:
                rev = inc.loc['Total Revenue', d] if 'Total Revenue' in inc.index else 1
                rec = bal.loc['Receivables', d] if 'Receivables' in bal.index else 0
                ni = inc.loc['Net Income', d] if 'Net Income' in inc.index else 1
                ocf = cf.loc['Operating Cash Flow', d] if 'Operating Cash Flow' in cf.index else 0
                
                history.append({
                    "年份": d.strftime("%Y"),
                    "营收": rev,
                    "应收": rec,
                    "净利润": ni,
                    "现金流": ocf,
                    "应收占比%": (rec / rev) * 100 if rev > 0 else 0,
                    "净现比": (ocf / ni) if ni > 0 else 0
                })
                
        # 同行并发获取
        target_group = MARKET_GROUPS["🇺🇸 美股科技 (AI & Chips)"]
        for k, v in MARKET_GROUPS.items():
            if symbol in v: target_group = v; break
        safe_group = target_group[:10]
        peers_data = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(get_stock_basic_info, safe_group)
        for res in results:
            if res: peers_data.append(res)
            
        return info, biz, pd.DataFrame(history).iloc[::-1], pd.DataFrame(peers_data)
    except: return None, None, pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_hunter_data_concurrent(tickers, discount_rate):
    ADR_FIX = {"PDD": 7.25, "BABA": 7.25, "TSM": 32.5}
    def fetch_one(raw_sym):
        symbol = smart_parse_symbol(raw_sym)
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
            return {
                "代码": symbol, "名称": cn_name, "现价": price, 
                "潜在涨幅%": round(upside*100, 2), "DCF估值": round(price*(1+upside), 2),
                "ROE%": round(roe*100, 2), "FCF收益率%": round((fcf_usd/mkt_cap)*100, 2) if mkt_cap > 0 else 0,
                "市值(B)": round(mkt_cap/1e9, 2)
            }
        except: return None

    snapshot = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_one, tickers)
    for res in results:
        if res: snapshot.append(res)
    return pd.DataFrame(snapshot)

# ==========================================
# 3. 核心界面逻辑
# ==========================================
with st.sidebar:
    st.header("⚡ 超级终端 v11.2")
    mode = st.radio("📡 选择模式", ["A. 全球猎手 (批量)", "B. 核心透视 (深度)"])
    st.divider()

if mode == "A. 全球猎手 (批量)":
    # --- 模式 A 保持不变 ---
    with st.sidebar:
        options = list(MARKET_GROUPS.keys()) + ["🔍 自选输入"]
        choice = st.selectbox("选择战场", options)
        if choice == "🔍 自选输入":
            user_txt = st.text_area("输入 (逗号隔开)", "NVDA, TSLA, 600519")
            tickers = [x.strip() for x in user_txt.split(',') if x.strip()]
        else: tickers = MARKET_GROUPS[choice]
        dr = st.slider("折现率 (%)", 6, 15, 9)
    
    st.title("🌍 全球价值猎手")
    if tickers:
        with st.spinner('⚡ 多线程扫描中...'):
            df_val = fetch_hunter_data_concurrent(tickers, dr)
        if not df_val.empty:
            df_val = df_val.sort_values("潜在涨幅%", ascending=False)
            st.subheader("1. 估值概览")
            fig_dumb = go.Figure()
            fig_dumb.add_trace(go.Scatter(x=df_val["现价"], y=df_val["名称"], mode='markers', name='现价', marker=dict(color='red', size=12)))
            fig_dumb.add_trace(go.Scatter(x=df_val["DCF估值"], y=df_val["名称"], mode='markers', name='估值', marker=dict(color='green', size=12, symbol='diamond')))
            for i in range(len(df_val)):
                r = df_val.iloc[i]
                c = 'green' if r['DCF估值'] > r['现价'] else 'red'
                fig_dumb.add_shape(type="line", x0=r['现价'], y0=r['名称'], x1=r['DCF估值'], y1=r['名称'], line=dict(color=c, width=3))
            st.plotly_chart(fig_dumb, use_container_width=True)
            c1, c2 = st.columns(2)
            with c1: st.plotly_chart(px.bar(df_val, x="名称", y="潜在涨幅%", color="潜在涨幅%", color_continuous_scale="RdYlGn", title="2. 潜能排行榜"), use_container_width=True)
            with c2: st.plotly_chart(px.scatter(df_val, x="FCF收益率%", y="ROE%", size="市值(B)", color="潜在涨幅%", text="名称", title="3. 黄金象限", color_continuous_scale="RdYlGn"), use_container_width=True)
            st.dataframe(df_val, use_container_width=True)

else:
    # --- 模式 B (核心透视) 升级版 ---
    with st.sidebar:
        raw_input = st.text_input("分析对象:", "NVDA").strip()
        symbol = smart_parse_symbol(raw_input)
    
    st.title(f"📊 核心透视: {symbol}")
    if symbol:
        with st.spinner('⚡ 正在进行财务体检...'):
            info, biz, df_hist, df_peers = fetch_deep_data_concurrent(symbol)
        
        if info:
            cn_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
            st.caption(f"分析对象: {cn_name}")

            # 1. 商业模式
            st.header("1. 🏢 商业模式")
            c1, c2, c3 = st.columns(3)
            with c1:
                val = biz['ROE'] * 100
                fig = go.Figure(go.Indicator(mode="gauge+number", value=val, title={'text': "ROE"}, gauge={'axis': {'range': [0, 40]}, 'bar': {'color': "#00c853" if val>15 else "#ff4b4b"}}))
                fig.update_layout(height=250, margin=dict(t=30,b=10))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                val = biz['毛利率'] * 100
                fig = go.Figure(go.Indicator(mode="gauge+number", value=val, title={'text': "毛利率"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#2962ff" if val>40 else "#ff9800"}}))
                fig.update_layout(height=250, margin=dict(t=30,b=10))
                st.plotly_chart(fig, use_container_width=True)
            with c3:
                st.metric("净利率", f"{biz['净利率']*100:.2f}%")
                st.info("ROE>15% (优) | 毛利>40% (强)")

            # 2. 行业地位
            st.header("2. 🏔️ 行业地位")
            if not df_peers.empty:
                fig_pos = px.scatter(df_peers, x="毛利率%", y="营收增长%", size="市值(B)", color="名称", text="名称", 
                                     title="行业格局 (右上角为王者)", height=450)
                fig_pos.update_traces(textposition='top center')
                st.plotly_chart(fig_pos, use_container_width=True)
            else: st.warning("暂无同行数据")

            # 3. 财务体检 (升级双轴图表)
            st.header("3. 🔎 深度财务审计")
            if not df_hist.empty:
                f1, f2 = st.columns(2)
                
                # --- 图1: 营收含金量 (双轴) ---
                with f1:
                    fig_rev = make_subplots(specs=[[{"secondary_y": True}]])
                    # 柱状图：营收
                    fig_rev.add_trace(
                        go.Bar(x=df_hist['年份'], y=df_hist['营收'], name="营收", marker_color='lightblue'),
                        secondary_y=False
                    )
                    # 折线图：应收占比 (警惕线)
                    fig_rev.add_trace(
                        go.Scatter(x=df_hist['年份'], y=df_hist['应收占比%'], name="应收占比%", mode='lines+markers', line=dict(color='red', width=3)),
                        secondary_y=True
                    )
                    fig_rev.update_layout(title="⚠️ 营收虚胖检测 (红线向上=危险)")
                    fig_rev.update_yaxes(title_text="营收规模", secondary_y=False)
                    fig_rev.update_yaxes(title_text="应收占比 (%)", secondary_y=True)
                    st.plotly_chart(fig_rev, use_container_width=True)
                    
                    # 智能结论
                    last_ratio = df_hist['应收占比%'].iloc[-1]
                    if last_ratio > 30: st.error(f"🚨 **高风险**: 应收账款占营收 {last_ratio:.1f}%，赊销严重！")
                    else: st.success(f"✅ **健康**: 应收占比 {last_ratio:.1f}%，回款正常。")

                # --- 图2: 利润含金量 (双轴) ---
                with f2:
                    fig_cash = make_subplots(specs=[[{"secondary_y": True}]])
                    # 柱状图：净利润
                    fig_cash.add_trace(
                        go.Bar(x=df_hist['年份'], y=df_hist['净利润'], name="净利润", marker_color='#a5d6a7'),
                        secondary_y=False
                    )
                    # 柱状图：现金流
                    fig_cash.add_trace(
                        go.Bar(x=df_hist['年份'], y=df_hist['现金流'], name="现金流", marker_color='#2e7d32'),
                        secondary_y=False
                    )
                    # 折线图：净现比 (安全线)
                    fig_cash.add_trace(
                        go.Scatter(x=df_hist['年份'], y=df_hist['净现比'], name="净现比 (现金/利润)", mode='lines+markers', line=dict(color='gold', width=3, dash='dot')),
                        secondary_y=True
                    )
                    fig_cash.update_layout(title="💰 利润真实性检测 (黄线>1=优秀)")
                    fig_cash.update_yaxes(title_text="金额", secondary_y=False)
                    fig_cash.update_yaxes(title_text="净现比 (倍)", secondary_y=True)
                    # 画一条基准线
                    fig_cash.add_hline(y=1.0, line_dash="dash", line_color="gray", secondary_y=True)
                    st.plotly_chart(fig_cash, use_container_width=True)
                    
                    # 智能结论
                    last_r = df_hist['净现比'].iloc[-1]
                    if last_r < 0.8: st.error(f"🚨 **低质量**: 净现比仅 {last_r:.2f}，利润没收到钱！")
                    elif last_r > 1.0: st.success(f"💎 **真金白银**: 净现比 {last_r:.2f}，现金流充沛。")
                    else: st.warning(f"⚠️ **一般**: 净现比 {last_r:.2f}，处于及格线附近。")

            else: st.warning("暂无历史数据")
        else: st.error("无法获取数据")
