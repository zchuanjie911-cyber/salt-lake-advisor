import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值投资超级终端 v6.0 (PK版)", page_icon="⚔️", layout="wide")
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
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ", "600036.SS", "601318.SS", "601857.SS", "601225.SS"]
}

def smart_parse_symbol(user_input):
    """智能代码识别: 数字转代码"""
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
def fetch_pk_data(tickers, discount_rate):
    """拉取多只股票的深度数据进行PK"""
    financials_history = []  # 用于画图 (DataFrame)
    valuation_snapshot = []  # 用于估值表 (List)
    ADR_FIX = {"PDD": 7.25, "BABA": 7.25, "TSM": 32.5}
    
    progress = st.progress(0)
    
    for i, raw_sym in enumerate(tickers):
        progress.progress((i + 1) / len(tickers))
        symbol = smart_parse_symbol(raw_sym)
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            inc = stock.income_stmt
            bal = stock.balance_sheet
            cf = stock.cashflow
            
            # --- 1. 基础信息与估值 ---
            cn_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
            mkt_cap = info.get('marketCap', 0)
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            roe = info.get('returnOnEquity', 0) or 0
            gm = info.get('grossMargins', 0) or 0
            
            # FCF 计算
            fcf = info.get('freeCashflow', 0)
            if fcf is None:
                op = info.get('operatingCashflow', 0) or 0
                cap = info.get('capitalExpenditures', 0) or 0
                fcf = op + cap if cap < 0 else op - cap # CAPEX is usually negative
            
            # DCF 计算
            fix_rate = ADR_FIX.get(symbol, 1.0)
            fcf_usd = fcf / fix_rate
            growth = min(max(info.get('earningsGrowth', 0.05) or 0.05, 0.02), 0.25)
            intrinsic = calculate_dcf(fcf_usd, growth, discount_rate/100)
            upside = (intrinsic - mkt_cap) / mkt_cap if mkt_cap > 0 else 0
            
            # 存入估值表
            valuation_snapshot.append({
                "代码": symbol, "名称": cn_name, "现价": price, 
                "潜在涨幅%": round(upside*100, 2), "DCF估值": round(price*(1+upside), 2),
                "ROE%": round(roe*100, 2), "毛利率%": round(gm*100, 2),
                "FCF收益率%": round((fcf_usd/mkt_cap)*100, 2) if mkt_cap>0 else 0,
                "市值(B)": round(mkt_cap/1e9, 2)
            })
            
            # --- 2. 历史趋势数据 (取最近4年) ---
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
    # 返回: 历史趋势DataFrame, 估值快照DataFrame
    return pd.DataFrame(financials_history).iloc[::-1], pd.DataFrame(valuation_snapshot)

# ==========================================
# 3. 侧边栏与主逻辑
# ==========================================
with st.sidebar:
    st.header("🦁 超级终端 v6.0")
    app_mode = st.radio("📡 选择模式", ["A. 猎手筛选 (批量)", "B. 巅峰对决 (手动PK)"])
    st.divider()

if app_mode == "A. 猎手筛选 (批量)":
    # --- 原有筛选逻辑 (简化显示) ---
    with st.sidebar:
        group = st.selectbox("选择板块", list(MARKET_GROUPS.keys()))
        tickers = MARKET_GROUPS[group]
        dr = st.slider("折现率 (%)", 6, 15, 9)
    
    st.title("🌍 板块批量筛选")
    df_hist, df_val = fetch_pk_data(tickers, dr)
    if not df_val.empty:
        df_val = df_val.sort_values("潜在涨幅%", ascending=False)
        st.subheader("🏆 性价比排行榜")
        st.dataframe(df_val.style.background_gradient(subset=["潜在涨幅%"], cmap="RdYlGn", vmin=-50, vmax=50), use_container_width=True)

else:
    # --- B. 巅峰对决 (PK Mode) ---
    with st.sidebar:
        st.info("💡 输入代码用逗号隔开，支持混输")
        default_txt = "NVDA, AMD, INTC"
        user_input = st.text_area("输入PK名单:", default_txt, height=100)
        target_list = [x.strip() for x in user_input.split(',') if x.strip()]
        
        dr_pk = st.slider("折现率 (%)", 6, 15, 9)

    st.title("⚔️ 巅峰对决 (Stock Battle)")
    
    if target_list:
        df_hist, df_val = fetch_pk_data(target_list, dr_pk)
        
        if not df_val.empty:
            # 1. 估值与基本面 PK 表
            st.subheader("1. 基本面与估值 PK")
            # 高亮最大值
            st.dataframe(
                df_val.set_index("名称").style
                .highlight_max(subset=["潜在涨幅%", "ROE%", "毛利率%", "FCF收益率%"], color='lightgreen')
                .highlight_min(subset=["潜在涨幅%", "ROE%", "毛利率%"], color='pink')
                .format({"市值(B)": "{:.2f}", "潜在涨幅%": "{:.2f}"}),
                use_container_width=True
            )
            
            # 2. 趋势对比图
            st.subheader("2. 历史趋势厮杀 (4年)")
            
            col1, col2 = st.columns(2)
            with col1:
                # 营收对比 (Line)
                fig_rev = px.line(df_hist, x="年份", y="营收", color="名称", markers=True, title="营收规模对比 (Revenue)")
                st.plotly_chart(fig_rev, use_container_width=True)
            
            with col2:
                # 利润对比 (Line)
                fig_inc = px.line(df_hist, x="年份", y="净利润", color="名称", markers=True, title="净利润对比 (Net Income)")
                st.plotly_chart(fig_inc, use_container_width=True)
                
            # 毛利率对比 (Bar Grouped)
            st.subheader("3. 护城河对比 (毛利率趋势)")
            fig_margin = px.bar(df_hist, x="年份", y="毛利率", color="名称", barmode="group", title="毛利率趋势 (越高护城河越深)")
            fig_margin.update_layout(yaxis_tickformat=".1%")
            st.plotly_chart(fig_margin, use_container_width=True)
            
            # 4. 哑铃图
            st.subheader("4. 价格 vs 价值")
            fig_dumb = go.Figure()
            fig_dumb.add_trace(go.Scatter(x=df_val["现价"], y=df_val["名称"], mode='markers', name='现价', marker=dict(color='red', size=12)))
            fig_dumb.add_trace(go.Scatter(x=df_val["DCF估值"], y=df_val["名称"], mode='markers', name='DCF价值', marker=dict(color='green', size=12, symbol='diamond')))
            
            for i in range(len(df_val)):
                r = df_val.iloc[i]
                color = 'green' if r['DCF估值'] > r['现价'] else 'red'
                fig_dumb.add_shape(type="line", x0=r['现价'], y0=r['名称'], x1=r['DCF估值'], y1=r['名称'], line=dict(color=color, width=3))
            
            fig_dumb.update_layout(xaxis_title="价格", yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_dumb, use_container_width=True)
            
        else:
            st.error("未获取到数据，请检查代码拼写。")
