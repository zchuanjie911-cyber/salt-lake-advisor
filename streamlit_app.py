import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 0. 页面配置与初始化
# ==========================================
st.set_page_config(page_title="全球价值投资超级终端 v16.0 (能源板块新增)", page_icon="💡", layout="wide")
st.markdown("""<style>.stApp {background-color: #f8f9fa;} .big-font {font-size:20px !important; font-weight: bold;} div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}</style>""", unsafe_allow_html=True)

# 初始化会话状态 (用于存储高延迟的同行数据)
if 'peers_data_cache' not in st.session_state:
    st.session_state.peers_data_cache = {}
if 'current_peer_group' not in st.session_state:
    st.session_state.current_peer_group = None

# ==========================================
# 1. 数据字典与智能识别 (新增能源股)
# ==========================================
STOCK_MAP = {
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊", "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威半导体",
    "TSM": "台积电", "ASML": "阿斯麦", "BABA": "阿里巴巴(美)", "PDD": "拼多多", "JD": "京东", "BIDU": "百度", "NTES": "网易",
    "BRK-B": "伯克希尔哈撒韦", "V": "威士", "MA": "万事达", "COST": "开市客", "MCD": "麦当劳", "KO": "可口可乐", "PEP": "百事", "LLY": "礼来",
    "NVO": "诺和诺德", "UNH": "联合健康", "JPM": "摩根大通", "JNJ": "强生", "PG": "宝洁", "XOM": "埃克森美孚", "CVX": "雪佛龙", "DIS": "迪士尼",
    "0700.HK": "腾讯控股", "9988.HK": "阿里巴巴(港)", "3690.HK": "美团", "0388.HK": "香港交易所", "0941.HK": "中国移动", "0883.HK": "中国海洋石油",
    "1299.HK": "友邦保险", "0005.HK": "汇丰控股", "1088.HK": "中国神华", "1810.HK": "小米集团", "2015.HK": "理想汽车", "0981.HK": "中芯国际",
    "600519.SS": "贵州茅台", "000858.SZ": "五粮液", "600900.SS": "长江电力", "300750.SZ": "宁德时代", "002594.SZ": "比亚迪", "600660.SS": "福耀玻璃",
    "300760.SZ": "迈瑞医疗", "600036.SS": "招商银行", "601318.SS": "中国平安", "601857.SS": "中国石油", "601225.SS": "陕西煤业", "000792.SZ": "盐湖股份",
    "600188.SS": "中煤能源",
    "601088.SS": "中国神华(A)",
    "600919.SS": "江苏银行"
}
# 建立全称 -> 代码的映射
NAME_TO_TICKER = {v: k for k, v in STOCK_MAP.items()}
# 增加热门简称映射
NAME_TO_TICKER.update({
    "腾讯": "0700.HK", "茅台": "600519.SS", "平安": "601318.SS", "招行": "600036.SS", "五粮液": "000858.SZ", 
    "阿里": "9988.HK", "英伟达": "NVDA", "中煤": "600188.SS", "神华": "1088.HK",
    "兖州煤业": "600188.SS", "中石化": "600028.SS", "中石油": "601857.SS"
})

MARKET_GROUPS = {
    "🇺🇸 美股科技 (AI & Chips)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "TSM", "ASML", "BABA", "PDD"],
    "🇨🇳 能源/煤炭 (Coal & Oil)": ["600188.SS", "601857.SS", "1088.HK", "0883.HK", "601088.SS", "600900.SS"], # 新增能源煤炭组
    "🇺🇸 美股护城河 (Moat & Value)": ["BRK-B", "V", "MA", "COST", "MCD", "KO", "PEP", "LLY", "NVO", "UNH", "JPM", "JNJ", "PG", "XOM", "CVX", "DIS"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600036.SS", "601318.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ"] 
}

def smart_parse_symbol(user_input):
    clean = user_input.strip()
    
    # 1. 精确匹配
    if clean in NAME_TO_TICKER: return NAME_TO_TICKER[clean]
    
    # 2. 模糊匹配 
    for name, ticker in NAME_TO_TICKER.items():
        if clean in name: 
            return ticker

    # 3. 数字匹配 
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
# 2. 极速数据获取 (并发与分段)
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

def get_peer_group_and_name(symbol):
    # 修正逻辑：先尝试在所有 MARKET_GROUPS 中找到匹配项
    for group_name, tickers in MARKET_GROUPS.items():
        if symbol in tickers: 
            return group_name, tickers
    # 如果找不到，默认使用美股科技组作为备选
    default_group = MARKET_GROUPS["🇺🇸 美股科技 (AI & Chips)"]
    return "🇺🇸 美股科技 (AI & Chips)", default_group

@st.cache_data(ttl=3600)
def fetch_main_stock_data(symbol):
    """只获取主角的财务和商业模式数据 (快速) - 增强容错"""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        inc = stock.income_stmt
        bal = stock.balance_sheet
        cf = stock.cashflow
        
        # 商业模式 (ROE/毛利率等，缺失则为0)
        biz = {
            "ROE": info.get('returnOnEquity', 0) or 0,
            "毛利率": info.get('grossMargins', 0) or 0,
            "净利率": info.get('profitMargins', 0) or 0
        }
        
        # 核心数据检查
        if not info or info.get('regularMarketPrice') is None:
             raise ValueError("Essential financial data missing.")

        # 历史趋势
        history = []
        if not inc.empty and len(inc.columns) >= 2: # 至少有2年数据
            years = inc.columns[:5]
            for d in years:
                # 强化容错：所有分母都设默认值
                rev = inc.loc['Total Revenue', d] if 'Total Revenue' in inc.index and inc.loc['Total Revenue', d] else 1.0
                rec = bal.loc['Receivables', d] if 'Receivables' in bal.index and bal.loc['Receivables', d] is not None else 0
                ni = inc.loc['Net Income', d] if 'Net Income' in inc.index and inc.loc['Net Income', d] else 1.0
                ocf = cf.loc['Operating Cash Flow', d] if 'Operating Cash Flow' in cf.index and cf.loc['Operating Cash Flow', d] is not None else 0
                
                history.append({
                    "年份": d.strftime("%Y"), "营收": rev, "应收": rec, "净利润": ni, "现金流": ocf,
                    "应收占比%": (rec / rev) * 100 if rev > 1 else 0, 
                    "净现比": (ocf / ni) if abs(ni) > 1 else 0 
                })
        
        return info, biz, pd.DataFrame(history).iloc[::-1]
    except Exception as e: 
        print(f"Error fetching data for {symbol}: {e}")
        return None, None, None

def load_peers_data(group_name, target_group):
    """加载同行数据，并存入缓存"""
    safe_group = target_group[:10]
    
    with st.spinner(f'🏎️ 正在多线程加载【{group_name}】同行数据...'):
        peers_data = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(get_stock_basic_info, safe_group)
        for res in results:
            if res: peers_data.append(res)
        
        st.session_state.peers_data_cache[group_name] = pd.DataFrame(peers_data)
        st.session_state.current_peer_group = group_name
    
    st.rerun() 

@st.cache_data(ttl=3600)
def fetch_hunter_data_concurrent(tickers, discount_rate):
    """猎手模式并发获取"""
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
    st.header("⚡ 超级终端 v15.1")
    mode = st.radio("📡 选择模式", ["A. 全球猎手 (批量)", "B. 核心透视 (深度)"])
    st.divider()

if mode == "A. 全球猎手 (批量)":
    # --- Mode A ---
    with st.sidebar:
        options = list(MARKET_GROUPS.keys()) + ["🔍 自选输入"]
        choice = st.selectbox("选择战场", options)
        if choice == "🔍 自选输入":
            user_txt = st.text_area("输入 (逗号隔开)", "NVDA, 腾讯, 贵州茅台")
            tickers = [x.strip() for x in user_txt.split(',') if x.strip()]
        else: tickers = MARKET_GROUPS[choice]
        dr = st.slider("折现率 (%)", 6, 15, 9)
    
    st.title("🌍 全球价值猎手")
    if tickers:
        with st.spinner('⚡ 多线程扫描中...'):
            df_val = fetch_hunter_data_concurrent(tickers, dr)
            
        if not df_val.empty:
            df_val = df_val.sort_values("潜在涨幅%", ascending=False).reset_index(drop=True)
            st.subheader("1. 估值概览 (优秀者置顶)")
            
            fig_dumb = go.Figure()
            fig_dumb.add_trace(go.Scatter(x=df_val["现价"], y=df_val["名称"], mode='markers', name='现价', marker=dict(color='red', size=12)))
            fig_dumb.add_trace(go.Scatter(x=df_val["DCF估值"], y=df_val["名称"], mode='markers', name='估值', marker=dict(color='green', size=12, symbol='diamond')))
            for i in range(len(df_val)):
                r = df_val.iloc[i]
                c = 'green' if r['DCF估值'] > r['现价'] else 'red'
                fig_dumb.add_shape(type="line", x0=r['现价'], y0=r['名称'], x1=r['DCF估值'], y1=r['名称'], line=dict(color=c, width=3))
            
            fig_dumb.update_layout(height=max(400, len(df_val)*30), xaxis_title="价格", yaxis=dict(autorange="reversed", type='category', categoryorder='array', categoryarray=df_val['名称']), title="🏆 哑铃榜：最上面的绿线越长，机会越大")
            st.plotly_chart(fig_dumb, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1: st.plotly_chart(px.bar(df_val, x="名称", y="潜在涨幅%", color="潜在涨幅%", color_continuous_scale="RdYlGn", title="2. 潜能排行榜 (按涨幅排序)"), use_container_width=True)
            with c2: st.plotly_chart(px.scatter(df_val, x="FCF收益率%", y="ROE%", size="市值(B)", color="潜在涨幅%", text="名称", title="3. 黄金象限 (质优价廉)", color_continuous_scale="RdYlGn"), use_container_width=True)
            
            st.dataframe(df_val.style.background_gradient(subset=["潜在涨幅%"], cmap="RdYlGn", vmin=-50, vmax=50), use_container_width=True)
        else: st.warning("未找到数据")

else:
    # --- Mode B (核心透视) - 阶段加载核心 ---
    with st.sidebar:
        st.info("💡 示例: NVDA, 贵州茅台, 中煤, 600188")
        raw_input = st.text_input("分析对象:", "NVDA").strip() # <-- 默认值改回 NVDA
        symbol = smart_parse_symbol(raw_input)
    
    st.title(f"📊 核心透视: {symbol}")
    if symbol:
        # **阶段1：快速加载主角数据 (瞬间)**
        info, biz, df_hist = fetch_main_stock_data(symbol) 
        
        if info:
            cn_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
            st.caption(f"分析对象: {cn_name}")
            
            group_name, target_group = get_peer_group_and_name(symbol)

            # 1. 商业模式 (即时加载)
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

            # 3. 财务体检 (即时加载)
            st.header("3. 🔎 深度财务审计")
            if df_hist is not None and not df_hist.empty:
                f1, f2 = st.columns(2)
                with f1:
                    fig_rev = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_rev.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['营收'], name="营收", marker_color='lightblue'), secondary_y=False)
                    fig_rev.add_trace(go.Scatter(x=df_hist['年份'], y=df_hist['应收占比%'], name="应收占比%", mode='lines+markers', line=dict(color='red', width=3)), secondary_y=True)
                    fig_rev.update_layout(title="⚠️ 营收虚胖检测")
                    st.plotly_chart(fig_rev, use_container_width=True)
                    last_ratio = df_hist['应收占比%'].iloc[-1]
                    if last_ratio > 30: st.error(f"🚨 应收占比 {last_ratio:.1f}%，虚胖！")
                    else: st.success(f"✅ 应收占比 {last_ratio:.1f}%，健康。")

                with f2:
                    fig_cash = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_cash.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['净利润'], name="净利润", marker_color='#a5d6a7'), secondary_y=False)
                    fig_cash.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['现金流'], name="现金流", marker_color='#2e7d32'), secondary_y=False)
                    fig_cash.add_trace(go.Scatter(x=df_hist['年份'], y=df_hist['净现比'], name="净现比", mode='lines+markers', line=dict(color='gold', width=3, dash='dot')), secondary_y=True)
                    fig_cash.update_layout(title="💰 利润真实性")
                    fig_cash.add_hline(y=1.0, line_dash="dash", line_color="gray", secondary_y=True)
                    st.plotly_chart(fig_cash, use_container_width=True)
                    last_r = df_hist['净现比'].iloc[-1]
                    if last_r < 0.8: st.error(f"🚨 净现比 {last_r:.2f}，利润质量低！")
                    else: st.success(f"💎 净现比 {last_r:.2f}，真金白银。")
            else: st.warning("⚠️ 暂无历史财务数据，请确认股票已上市并有公开年报。")


            # 2. 行业地位 (异步加载/缓存)
            st.header(f"2. 🏔️ 行业地位 ({group_name})")
            
            df_peers = st.session_state.peers_data_cache.get(group_name)

            if df_peers is not None:
                fig_pos = px.scatter(df_peers, x="毛利率%", y="营收增长%", size="市值(B)", color="名称", text="名称", 
                                     title="行业格局 (右上角为王者)", height=450)
                fig_pos.update_traces(textposition='top center')
                st.plotly_chart(fig_pos, use_container_width=True)
                st.success("✨ 数据已从缓存中加载 (秒开)")
            else:
                st.warning(f"同行对比数据尚未加载。点击下方按钮进行多线程加载。")
                if st.button(f'🏎️ 立即加载【{group_name}】同行数据'):
                    load_peers_data(group_name, target_group)
        
        else: st.error(f"❌ 核心数据获取失败。请检查股票代码 `{symbol}` 是否正确，或数据源暂不可用。")
