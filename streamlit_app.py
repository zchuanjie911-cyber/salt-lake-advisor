import streamlit as st
import pandas as pd
import yfinance as yf
# try:
#     import akshare as ak
# except ImportError:
#     st.error("请确保已安装 akshare 库: pip install akshare")
#     ak = None # 禁用 akshare
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 0. 页面配置与初始化
# ==========================================
st.set_page_config(page_title="全球投资终端 v19.0 (AkShare集成)", page_icon="🇨🇳", layout="wide")
st.markdown("""<style>.stApp {background-color: #f8f9fa;} .big-font {font-size:20px !important; font-weight: bold;} div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}</style>""", unsafe_allow_html=True)

# 初始化会话状态
if 'peers_data_cache' not in st.session_state:
    st.session_state.peers_data_cache = {}
if 'current_peer_group' not in st.session_state:
    st.session_state.current_peer_group = None

# ==========================================
# 1. 数据字典与智能识别 
# ==========================================
# 股票字典保持不变
STOCK_MAP = {
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "NVDA": "英伟达", "TSM": "台积电",
    "0700.HK": "腾讯控股", "600519.SS": "贵州茅台", "600188.SS": "中煤能源", "601318.SS": "中国平安",
    "601088.SS": "中国神华(A)", "0883.HK": "中国海洋石油", "0941.HK": "中国移动",
    "600036.SS": "招商银行", "600887.SS": "伊利股份", "600585.SS": "海螺水泥",
    "BRK-B": "伯克希尔哈撒韦", "COST": "开市客", "JPM": "摩根大通",
}

NAME_TO_TICKER = {v: k for k, v in STOCK_MAP.items()}
NAME_TO_TICKER.update({
    "腾讯": "0700.HK", "茅台": "600519.SS", "平安": "601318.SS", "中煤": "600188.SS", "神华": "601088.SS",
    "苹果": "AAPL", "微软": "MSFT", "英伟达": "NVDA", "招行": "600036.SS", "伊利": "600887.SS"
})

MARKET_GROUPS = {
    "🇺🇸 美股科技 (Tech)": ["AAPL", "MSFT", "GOOG", "NVDA", "TSM"],
    "🇺🇸 美股护城河 (Value)": ["BRK-B", "COST", "JPM"],
    "🇭🇰 港股核心 (Core)": ["0700.HK", "0941.HK", "0883.HK"],
    "🇨🇳 A股核心 (Core)": ["600519.SS", "600036.SS", "601318.SS", "600188.SS", "601088.SS", "600887.SS", "600585.SS"]
}

def smart_parse_symbol(user_input):
    clean = user_input.strip()
    if clean in NAME_TO_TICKER: return NAME_TO_TICKER[clean]
    for name, ticker in NAME_TO_TICKER.items():
        if clean in name: return ticker
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
# 2. AkShare 专属数据获取和清洗函数
# ==========================================

@st.cache_data(ttl=3600)
def fetch_akshare_data(code):
    """
    通过 AkShare 获取 A股/H股核心财务数据。
    返回: info, biz, df_hist (兼容 yfinance 格式)
    """
    if 'ak' not in globals():
        return None, None, None, "AkShare未安装或无法加载"

    try:
        # 1. 获取基本面数据 (用于ROE/毛利率)
        # 统一获取 A 股代码 (无后缀) 或 H 股代码 (无后缀)
        ticker = code.split('.')[0]
        
        if code.endswith('.HK'):
            # 港股财报数据源
            df_report = ak.stock_hk_financial_report_sina(symbol=ticker)
            # 港股没有现成的ROE/毛利率，需要手动计算
            if df_report.empty:
                 raise ValueError("AkShare港股财报缺失")
            
            latest_data = df_report.iloc[0]
            # 简化计算（需要更复杂的逻辑才能兼容 yfinance 的 info 字段）
            biz = {
                 "ROE": (latest_data['净利润'] / latest_data['股东权益'] if latest_data['股东权益'] else 0) or 0,
                 "毛利率": (latest_data['毛利率'] / 100) or 0,
                 "净利率": (latest_data['净利润率'] / 100) or 0
            }
            display_name = df_report.columns.name if df_report.columns.name else ticker

        else: # A 股 (SH/SZ)
            # A股业绩快报，用于获取最新ROE和利润率
            df_express = ak.stock_a_performance_express_sina()
            express_data = df_express[df_express['股票代码'] == ticker].iloc[0] if not df_express[df_express['股票代码'] == ticker].empty else {}
            
            # A股利润表 (income statement)
            df_profit = ak.stock_financial_report_sina(stock=ticker, symbol="利润表")
            
            if df_profit.empty:
                 raise ValueError("AkShare A股利润表缺失")
                 
            latest_profit = df_profit.iloc[0]
            
            biz = {
                "ROE": (latest_profit['净资产收益率(%)'] / 100) or 0,
                "毛利率": (latest_profit['销售毛利率(%)'] / 100) or 0,
                "净利率": (latest_profit['销售净利率(%)'] / 100) or 0
            }
            display_name = express_data.get('股票简称', ticker)

        # 2. 构造历史趋势 df_hist (财务体检图所需)
        # 仅为演示AkShare逻辑，这里用一个假数据或仅取主要指标
        # 实际项目中需要拉取利润表、资产负债表和现金流量表并对齐年份
        df_hist = pd.DataFrame()
        
        # 3. 构造 info 字典 (仅用于展示名称和价格)
        # 实时价格数据获取
        df_price = ak.stock_zh_a_spot_em() if not code.endswith('.HK') else ak.stock_hk_spot()
        price_data = df_price[df_price['代码'] == ticker].iloc[0] if not df_price[df_price['代码'] == ticker].empty else {}
        
        info = {
            'shortName': display_name,
            'regularMarketPrice': price_data.get('最新价') if price_data.get('最新价') else None,
            'marketCap': price_data.get('总市值') if price_data.get('总市值') else 0
        }
        
        return info, biz, df_hist, display_name

    except Exception as e:
        return None, None, None, f"AkShare数据拉取失败: {e}"


# ==========================================
# 3. 核心数据获取 (分流逻辑)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_main_stock_data(symbol):
    """
    主数据拉取函数: 优先使用 AkShare (A/H股)，否则使用 yfinance。
    """
    is_domestic = symbol.endswith(('.SS', '.SZ', '.HK'))

    if is_domestic and 'ak' in globals():
        # 尝试使用 AkShare
        info, biz, df_hist, display_name = fetch_akshare_data(symbol)
        if info:
            st.warning(f"✅ 【{display_name}】数据由 AkShare 提供")
            return info, biz, df_hist, display_name

    # AkShare 失败 或 非国内股票，回退到 yfinance (v17.1 容错逻辑)
    info = {}; biz = {}; df_hist = pd.DataFrame()
    try:
        stock = yf.Ticker(symbol)
        info = stock.info if stock.info else {}
        inc = stock.income_stmt if stock.income_stmt is not None else pd.DataFrame()
        bal = stock.balance_sheet if stock.balance_sheet is not None else pd.DataFrame()
        cf = stock.cashflow if stock.cashflow is not None else pd.DataFrame()
        
        if not info or info.get('regularMarketPrice') is None:
             raise ValueError("No basic price information available.")

        biz = {
            "ROE": info.get('returnOnEquity', 0) or 0,
            "毛利率": info.get('grossMargins', 0) or 0,
            "净利率": info.get('profitMargins', 0) or 0
        }
        
        history = []
        if not inc.empty and len(inc.columns) >= 1:
            years = inc.columns[:5]
            for d in years:
                rev = inc.loc['Total Revenue', d] if 'Total Revenue' in inc.index and inc.loc['Total Revenue', d] else 1.0
                rec = bal.loc['Receivables', d] if 'Receivables' in bal.index and bal.loc['Receivables', d] is not None else 0
                ni = inc.loc['Net Income', d] if 'Net Income' in inc.index and inc.loc['Net Income', d] else 1.0
                ocf = cf.loc['Operating Cash Flow', d] if 'Operating Cash Flow' in cf.index and cf.loc['Operating Cash Flow', d] is not None else 0
                
                history.append({
                    "年份": d.strftime("%Y"), "营收": rev, "应收": rec, "净利润": ni, "现金流": ocf,
                    "应收占比%": (rec / rev) * 100 if rev > 1 else 0, 
                    "净现比": (ocf / ni) if abs(ni) > 1 else 0 
                })
            df_hist = pd.DataFrame(history).iloc[::-1]

        display_name = info.get('shortName', info.get('longName', symbol))
        st.info(f"⚡ 【{display_name}】数据由 yfinance 提供")
        return info, biz, df_hist, display_name
    except Exception as e: 
        print(f"yfinance fallback failed for {symbol}: {e}")
        return None, None, None, symbol

# ==========================================
# 4. 辅助函数 (保持不变)
# ==========================================
def get_stock_basic_info(symbol):
    try:
        t = yf.Ticker(symbol)
        i = t.info
        name = STOCK_MAP.get(symbol, i.get('shortName', symbol)) 
        return {
            "名称": name,
            "市值(B)": (i.get('marketCap', 0) or 0)/1e9,
            "毛利率%": (i.get('grossMargins', 0) or 0)*100,
            "营收增长%": (i.get('revenueGrowth', 0) or 0)*100
        }
    except: return None

def get_peer_group_and_name(symbol):
    for group_name, tickers in MARKET_GROUPS.items():
        if symbol in tickers: 
            return group_name, tickers
    return None, None

def load_peers_data(group_name, target_group):
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
    ADR_FIX = {"PDD": 7.25, "BABA": 7.25, "TSM": 32.5}
    def fetch_one(raw_sym):
        symbol = smart_parse_symbol(raw_sym)
        if symbol not in STOCK_MAP and not symbol.endswith(('.SS', '.SZ', '.HK')):
            return None
            
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
# 5. 主界面逻辑
# ==========================================
with st.sidebar:
    st.header("🌎 超级终端 v19.0")
    mode = st.radio("📡 选择模式", ["A. 全球猎手 (批量)", "B. 核心透视 (深度)"])
    st.divider()

if mode == "A. 全球猎手 (批量)":
    # --- Mode A: 全球猎手 (批量) ---
    with st.sidebar:
        options = list(MARKET_GROUPS.keys()) + ["🔍 自选输入"]
        choice = st.selectbox("选择战场", options)
        if choice == "🔍 自选输入":
            st.info("💡 批量分析仅支持预设的股票池，保证数据准确性。")
            user_txt = st.text_area("输入 (逗号隔开)", "NVDA, 腾讯控股, 贵州茅台")
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
            with c1: st.plotly_chart(px.bar(df_val, x="名称", y="潜在涨幅%", color="潜在涨幅%", color_continuous_scale="RdYlGn", title="2. 潜能排行榜"), use_container_width=True)
            with c2: st.plotly_chart(px.scatter(df_val, x="FCF收益率%", y="ROE%", size="市值(B)", color="潜在涨幅%", text="名称", title="3. 黄金象限 (质优价廉)", color_continuous_scale="RdYlGn"), use_container_width=True)
            
            st.dataframe(df_val.style.background_gradient(subset=["潜在涨幅%"], cmap="RdYlGn", vmin=-50, vmax=50), use_container_width=True)
        else: st.warning("未找到数据")

else:
    # --- Mode B: 核心透视 (全球查询) ---
    with st.sidebar:
        st.info("💡 输入全球代码 (如 DAX.DE, NVDA, 600519)")
        raw_input = st.text_input("分析对象:", "NVDA").strip()
        symbol = smart_parse_symbol(raw_input)
    
    st.title(f"🌎 核心透视: {symbol}")
    if symbol:
        # **阶段1：快速加载主角数据 (瞬间)**
        info, biz, df_hist, display_name = fetch_main_stock_data(symbol) 
        
        if info:
            st.caption(f"分析对象名称: {display_name}")
            
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
            if not df_hist.empty:
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
            else: st.warning("⚠️ 暂无历史财务数据。")


            # 2. 行业地位 (异步加载/缓存或跳过)
            if group_name:
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
            else:
                 st.header("2. 🏔️ 行业地位")
                 st.info("该股票不在预设的同行分析组中，无法进行行业地位对比分析。")

        else: st.error(f"❌ 核心数据获取失败。请检查股票代码 `{symbol}` 是否正确。")
