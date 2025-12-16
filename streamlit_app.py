import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 0. Tushare 初始化与数据源配置
# ==========================================
# 安全地导入 Tushare 并获取 Token
try:
    import tushare as ts
    TUSHARE_TOKEN = st.secrets.get("TUSHARE_TOKEN") 
    pro = ts.pro_api(TUSHARE_TOKEN) if TUSHARE_TOKEN else None
except ImportError:
    pro = None
except Exception as e:
    pro = None
    st.sidebar.error(f"Tushare 初始化失败: {e}")

# 初始化时在侧边栏提示 Tushare 状态
if pro is None and TUSHARE_TOKEN is None:
    st.sidebar.warning("Tushare Token未配置，国内股票数据质量可能较低。请在Secrets中设置TUSHARE_TOKEN。")
elif pro is not None:
    st.sidebar.success("Tushare 连接成功！")


# ==========================================
# 1. 数据字典与智能识别
# ==========================================
STOCK_MAP = {
    # 核心美股 - Tech & Mega Cap
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊", "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威半导体",
    "TSM": "台积电", "ASML": "阿斯麦", "BABA": "阿里巴巴(美)", "PDD": "拼多多",
    # 核心美股 - Moat & Value
    "BRK-B": "伯克希尔哈撒韦", "V": "威士", "MA": "万事达", "COST": "开市客", "JPM": "摩根大通", "JNJ": "强生", "PG": "宝洁", "XOM": "埃克森美孚", 
    "KO": "可口可乐", "PEP": "百事", "MCD": "麦当劳", "LLY": "礼来", "UNH": "联合健康",
    # 核心港股
    "0700.HK": "腾讯控股", "9988.HK": "阿里巴巴(港)", "3690.HK": "美团", "0388.HK": "香港交易所", "0941.HK": "中国移动", "0883.HK": "中国海洋石油",
    "1810.HK": "小米集团", "1024.HK": "快手", "1299.HK": "友邦保险", "0005.HK": "汇丰控股",
    # 核心A股
    "600519.SS": "贵州茅台", "000858.SZ": "五粮液", "600900.SS": "长江电力", "300750.SZ": "宁德时代", "600036.SS": "招商银行", 
    "601318.SS": "中国平安", "600188.SS": "中煤能源", "601088.SS": "中国神华(A)", "600887.SS": "伊利股份", "600585.SS": "海螺水泥",
    "002714.SZ": "牧原股份", "600030.SS": "中信证券", "002594.SZ": "比亚迪", "300760.SZ": "迈瑞医疗"
}

NAME_TO_TICKER = {v: k for k, v in STOCK_MAP.items()}
NAME_TO_TICKER.update({
    "腾讯": "0700.HK", "茅台": "600519.SS", "平安": "601318.SS", "中煤": "600188.SS", "神华": "601088.SS",
    "苹果": "AAPL", "微软": "MSFT", "英伟达": "NVDA", "招行": "600036.SS", "伊利": "600887.SS"
})

MARKET_GROUPS = {
    "🇺🇸 美股科技 (Tech)": [
        "AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", 
        "TSM", "ASML", "BABA", "PDD"
    ],
    "🇺🇸 美股护城河 (Value)": [
        "BRK-B", "V", "MA", "COST", "JPM", "JNJ", "PG", "XOM", 
        "KO", "PEP", "MCD", "LLY", "UNH"
    ],
    "🇭🇰 港股核心 (Core)": [
        "0700.HK", "9988.HK", "3690.HK", "0388.HK", "0941.HK", "0883.HK", 
        "1810.HK", "1024.HK", "1299.HK", "0005.HK"
    ],
    "🇨🇳 A股核心 (Core)": [
        "600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "600036.SS", 
        "601318.SS", "600188.SS", "601088.SS", "600887.SS", "600585.SS", 
        "002714.SZ", "600030.SS", "002594.SZ", "300760.SZ"
    ]
}
# 辅助函数保持不变
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
def get_peer_group_and_name(symbol):
    for group_name, tickers in MARKET_GROUPS.items():
        if symbol in tickers: return group_name, tickers
    return None, None
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


# ==========================================
# 2. Tushare 专有数据拉取函数 (新增)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_tushare_data(ts_code):
    """
    通过 Tushare 获取 A股/港股核心财务数据。
    ts_code 格式：'600519.SH' 或 '00700.HK'
    返回: info, biz, df_hist
    """
    global pro
    if pro is None:
        raise ConnectionError("Tushare Pro API 未成功初始化。")

    # Tushare 交易日历：获取最新的一个交易日，确保数据是近期的
    end_date = pd.to_datetime('today').strftime('%Y%m%d')
    start_date = (pd.to_datetime('today') - pd.DateOffset(years=5)).strftime('%Y%m%d')
    
    # 1. 估值和基本信息 (获取最新 ROE 和市值)
    df_basic = pro.query('daily_basic', ts_code=ts_code, end_date=end_date, fields='trade_date,total_share,circ_share,total_mv,pe_ttm,roe')
    
    # 2. 利润表 (用于营收和净利润数据)
    df_inc = pro.query('income', ts_code=ts_code, start_date=start_date, end_date=end_date, fields='end_date,revenue,n_income,dt_ann')
    
    # 3. 现金流量表 (用于 OCF)
    df_cf = pro.query('cashflow', ts_code=ts_code, start_date=start_date, end_date=end_date, fields='end_date,n_cashflow_act')
    
    # 4. 资产负债表 (用于应收账款)
    df_bal = pro.query('balancesheet', ts_code=ts_code, start_date=start_date, end_date=end_date, fields='end_date,total_receiv')

    if df_basic.empty or df_inc.empty:
        raise ValueError("Tushare未返回足够的基本面或利润数据。")
        
    # --- 数据清洗与格式化 ---
    
    # 1. 商业模式 (Biz)
    latest_basic = df_basic.iloc[0]
    
    # Tushare没有直接的毛利率和净利率，需要用利润表计算
    latest_inc = df_inc.iloc[0]
    gross_profit = latest_inc.get('revenue', 0) - latest_inc.get('cost_oper', 0) if 'cost_oper' in latest_inc.index else 0 # Tushare默认字段可能需要查询
    
    biz = {
        "ROE": latest_basic.get('roe', 0) / 100, # Tushare的ROE通常是百分比值
        "毛利率": 0, # Tushare缺乏直接的毛利/成本数据，设为0或通过复杂的中间表计算
        "净利率": latest_inc.get('n_income', 0) / latest_inc.get('revenue', 1) if latest_inc.get('revenue') else 0
    }
    
    # 2. 历史趋势 (df_hist)
    # 合并INC, CF, BAL表，并按报告期（end_date）对齐
    df_hist_merged = pd.merge(df_inc, df_cf, on='end_date', how='inner')
    df_hist_merged = pd.merge(df_hist_merged, df_bal, on='end_date', how='inner')
    
    # 转换为 yfinance 兼容格式
    df_hist = df_hist_merged.rename(columns={
        'end_date': '年份',
        'revenue': '营收',
        'n_income': '净利润',
        'n_cashflow_act': '现金流',
        'total_receiv': '应收'
    })
    
    df_hist['年份'] = df_hist['年份'].apply(lambda x: pd.to_datetime(x).strftime('%Y'))
    df_hist = df_hist.sort_values(by='年份').drop_duplicates(subset=['年份'], keep='last').tail(5)
    
    # 计算衍生指标
    df_hist['应收占比%'] = (df_hist['应收'] / df_hist['营收']) * 100
    df_hist['净现比'] = (df_hist['现金流'] / df_hist['净利润']).clip(upper=5) # 限制异常值
    
    # 3. 构造 info 字典
    # 简单构造显示名称，Tushare拉不到 shortName
    display_name = STOCK_MAP.get(ts_code.replace('.SH', '.SS').replace('.SZ', '.SZ').replace('.HK', '.HK'), ts_code)
    
    info = {
        'regularMarketPrice': None, # Tushare实时价格需要另一个接口
        'shortName': display_name
    }

    return info, biz, df_hist, display_name


# ==========================================
# 3. 核心数据获取 (分流逻辑)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_main_stock_data(symbol):
    """
    主数据拉取函数: Tushare优先 (A/H股)，否则使用 yfinance。
    """
    is_domestic = symbol.endswith(('.SS', '.SZ', '.HK'))

    if is_domestic and pro is not None:
        # 尝试使用 Tushare
        ts_code = symbol.replace('.SS', '.SH').replace('.SZ', '.SZ').replace('.HK', '.HK') # 转换为 Tushare 代码格式
        try:
            info, biz, df_hist, display_name = fetch_tushare_data(ts_code)
            st.warning(f"✅ 【{display_name}】数据由 Tushare 提供 (仅财报)")
            
            # Tushare 缺乏价格信息，回退到 yfinance 补充价格
            try:
                yf_info = yf.Ticker(symbol).info
                info['regularMarketPrice'] = yf_info.get('regularMarketPrice')
            except: pass
            
            return info, biz, df_hist, display_name

        except Exception as e:
            st.warning(f"Tushare数据拉取失败 ({e.__class__.__name__})，回退到 yfinance...")


    # Tushare 失败 或 非国内股票，回退到 yfinance (v17.1 容错逻辑)
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
    st.header("🌎 超级终端 v20.0")
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
        raw_input = st.text_input("分析对象:", "600519.SS").strip() # 默认值改为茅台，方便测试 Tushare
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
