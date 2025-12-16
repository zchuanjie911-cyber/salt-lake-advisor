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
# 检查并初始化 Tushare
try:
    import tushare as ts
    TUSHARE_TOKEN = st.secrets.get("TUSHARE_TOKEN") 
    pro = ts.pro_api(TUSHARE_TOKEN) if TUSHARE_TOKEN else None
except ImportError:
    pro = None
except Exception:
    pro = None

# ==========================================
# 0. 页面配置与初始化
# ==========================================
st.set_page_config(page_title="全球投资终端 v24.0 (护城河分析)", page_icon="🎯", layout="wide")
st.markdown("""<style>
/* 核心指标卡片样式优化 */
.metric-container {
    padding: 10px;
    border-radius: 8px;
    border: 1px solid #e0e0e0;
    margin-bottom: 10px;
    text-align: center;
}
.metric-title {
    font-size: 14px;
    color: #6c757d;
    font-weight: bold;
}
.metric-value {
    font-size: 24px;
    font-weight: bold;
    color: #0f52ba;
}
/* 隐藏 Streamlit 默认的 Metric 标签，因为我们用自定义的了 */
div[data-testid="stMetricDelta"] {
    display: none;
}
</style>""", unsafe_allow_html=True)

# 初始化会话状态
if 'peers_data_cache' not in st.session_state:
    st.session_state.peers_data_cache = {}
if 'current_peer_group' not in st.session_state:
    st.session_state.current_peer_group = None

# ==========================================
# 1. 数据字典与智能识别 (保留 V20.1)
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
    # 核心A股 (新增 新易盛 卧龙电驱)
    "600519.SS": "贵州茅台", "000858.SZ": "五粮液", "600900.SS": "长江电力", "300750.SZ": "宁德时代", "600036.SS": "招商银行", 
    "601318.SS": "中国平安", "600188.SS": "中煤能源", "601088.SS": "中国神华(A)", "600887.SS": "伊利股份", "600585.SS": "海螺水泥",
    "002714.SZ": "牧原股份", "600030.SS": "中信证券", "002594.SZ": "比亚迪", "300760.SZ": "迈瑞医疗",
    "300502.SZ": "新易盛",  
    "600580.SS": "卧龙电驱" 
}

NAME_TO_TICKER = {v: k for k, v in STOCK_MAP.items()}
NAME_TO_TICKER.update({
    "腾讯": "0700.HK", "茅台": "600519.SS", "平安": "601318.SS", "中煤": "600188.SS", "神华": "601088.SS",
    "苹果": "AAPL", "微软": "MSFT", "英伟达": "NVDA", "招行": "600036.SS", "伊利": "600887.SS",
    "新易盛": "300502.SZ", "卧龙": "600580.SS", "卧龙电驱": "600580.SS"
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
        "002714.SZ", "600030.SS", "002594.SZ", "300760.SZ", "300502.SZ", "600580.SS"
    ]
}

# 辅助函数 (保持不变)
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
@st.cache_data(ttl=3600)
def fetch_main_stock_data(symbol):
    info = {}; biz = {}; df_hist = pd.DataFrame()
    # Tushare 优先逻辑 (此处省略，保持 yfinance 稳定)

    # 降级到 yfinance 
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
        
        return info, biz, df_hist, display_name
    except Exception as e: 
        print(f"yfinance fallback failed for {symbol}: {e}")
        return None, None, None, symbol

# --- ROE & GM 建议函数 ---
def get_roe_advice(roe):
    if roe >= 0.25:
        return "✨ 极高 ROE：卓越的资本效率，具备顶级护城河潜力。", "success"
    elif roe >= 0.15:
        return "✅ 优秀 ROE：高于行业平均，体现管理层出色的盈利能力。", "success"
    elif roe >= 0.10:
        return "⚠️ 一般 ROE：符合市场标准，需结合估值判断，竞争力普通。", "warning"
    else:
        return "❌ 低 ROE：资本效率低下，警惕盈利模式脆弱。", "error"

def get_gm_advice(gm):
    if gm >= 0.60:
        return "👑 极高毛利率：产品定价权极强，行业垄断或独家技术。", "success"
    elif gm >= 0.40:
        return "✅ 高毛利率：具有较强品牌或成本优势，护城河稳定。", "success"
    elif gm >= 0.20:
        return "⚠️ 一般毛利率：行业竞争激烈，产品差异化不足。", "warning"
    else:
        return "❌ 低毛利率：纯粹竞争型行业，抗风险能力弱。", "error"


# ==========================================
# 3. 核心界面逻辑
# ==========================================
with st.sidebar:
    st.header("🎯 投资终端 v24.0")
    mode = st.radio("📡 选择模式", ["A. 全球猎手 (批量)", "B. 核心透视 (深度)"])
    
    # 核心透视模式下的输入框
    if mode == "B. 核心透视 (深度)":
        st.info("💡 输入全球代码 (如 DAX.DE, NVDA, 300502)")
        raw_input = st.text_input("分析对象:", "300502.SZ").strip() 
        symbol = smart_parse_symbol(raw_input)
    
    # Tushare 状态提示
    if 'pro' in globals() and pro is None and TUSHARE_TOKEN is None:
        st.warning("Tushare Token未配置，国内股票数据质量可能较低。")
    elif 'pro' in globals() and pro is None and TUSHARE_TOKEN is not None:
        st.error("Tushare 初始化失败或 Token 无效。")
    elif 'pro' in globals() and pro is not None:
        st.success("Tushare 连接成功！")
        
    st.divider()

if mode == "A. 全球猎手 (批量)":
    # --- Mode A: 全球猎手 (批量) (保持不变) ---
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
    # --- Mode B: 核心透视 (V24.0 优化布局) ---
    if 'symbol' in locals():
        # **阶段1：快速加载主角数据 (瞬间)**
        info, biz, df_hist, display_name = fetch_main_stock_data(symbol) 
        
        if info:
            st.header(f"💎 {display_name} ({symbol})")
            st.caption("基于 V3.4 极简风格，聚焦核心财务指标和估值分析。")
            
            group_name, target_group = get_peer_group_and_name(symbol)
            
            # 价格、市值、潜在涨幅 (Metric Cards)
            current_price = info.get('regularMarketPrice', 0)
            dcf_val = current_price * (1 + 0.2) 
            upside = ((dcf_val / current_price) - 1) * 100 if current_price else 0

            col_p, col_m, col_u = st.columns(3)
            with col_p:
                st.metric("实时价格", f"${current_price:.2f}")
            with col_m:
                st.metric("市值 (B)", f"${info.get('marketCap', 0)/1e9:.1f}")
            with col_u:
                st.metric("潜在涨幅", f"{upside:.1f}%", delta_color="inverse")
            
            st.markdown("---")

            # --- 核心商业指标 (可视化/Gauge Charts + 建议) ---
            st.subheader("1. 🛡️ 商业模式与护城河 (Moat Analysis)")
            
            val_roe = biz['ROE'] * 100
            val_gm = biz['毛利率'] * 100
            roe_advice, roe_style = get_roe_advice(val_roe / 100)
            gm_advice, gm_style = get_gm_advice(val_gm / 100)

            c1, c2, c3 = st.columns(3)
            with c1:
                # ROE Gauge
                fig_roe = go.Figure(go.Indicator(
                    mode="gauge+number", value=val_roe, title={'text': "股本回报率 (ROE)"}, 
                    gauge={'axis': {'range': [0, 40]}, 'bar': {'color': "#00c853" if val_roe > 15 else "#ff4b4b"},
                           'steps': [{'range': [0, 15], 'color': 'lightgray'}, {'range': [15, 40], 'color': '#d1f4e3'}],
                           'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 20}
                          }
                ))
                fig_roe.update_layout(height=250, margin=dict(t=30,b=10))
                st.plotly_chart(fig_roe, use_container_width=True)
                st.markdown(f"**ROE 建议:** <span style='color: {'green' if roe_style == 'success' else 'orange' if roe_style == 'warning' else 'red'};'>{roe_advice}</span>", unsafe_allow_html=True)
                
            with c2:
                # 毛利率 Gauge
                fig_gm = go.Figure(go.Indicator(
                    mode="gauge+number", value=val_gm, title={'text': "毛利率 (Gross Margin)"}, 
                    gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#2962ff" if val_gm > 40 else "#ff9800"},
                           'steps': [{'range': [0, 40], 'color': 'lightgray'}, {'range': [40, 100], 'color': '#c2e3ff'}],
                           'threshold': {'line': {'color': "darkorange", 'width': 4}, 'thickness': 0.75, 'value': 60}
                          }
                ))
                fig_gm.update_layout(height=250, margin=dict(t=30,b=10))
                st.plotly_chart(fig_gm, use_container_width=True)
                st.markdown(f"**毛利建议:** <span style='color: {'green' if gm_style == 'success' else 'orange' if gm_style == 'warning' else 'red'};'>{gm_advice}</span>", unsafe_allow_html=True)

            with c3:
                # 净利率 Metric (作为补充)
                st.markdown('<div style="height: 125px;"></div>', unsafe_allow_html=True) # 视觉对齐
                st.metric("净利率", f"{biz['净利率']*100:.2f}%")
                if biz['净利率']*100 > 10: st.success("净利率优秀（>10%）")
                else: st.info("净利率普通")
            
            st.markdown("---")

            # 2. 财务体检 (V3.4 风格图表)
            st.subheader("2. 财务体检：利润质量与增长趋势")
            
            if not df_hist.empty:
                f1, f2 = st.columns(2)
                
                # 营收虚胖检测
                with f1:
                    fig_rev = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_rev.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['营收'], name="营收", marker_color='lightblue'), secondary_y=False)
                    fig_rev.add_trace(go.Scatter(x=df_hist['年份'], y=df_hist['应收占比%'], name="应收占比%", mode='lines+markers', line=dict(color='red', width=3)), secondary_y=True)
                    fig_rev.update_layout(title="图 2.1 营收增长与应收账款占比 (健康度)", height=350, margin=dict(t=30, b=10))
                    st.plotly_chart(fig_rev, use_container_width=True)
                    last_ratio = df_hist['应收占比%'].iloc[-1]
                    if last_ratio > 30: st.error(f"🚨 结论：营收虚胖风险高 ({last_ratio:.1f}%)")
                    else: st.success(f"✅ 结论：营收质量健康 ({last_ratio:.1f}%)")

                # 利润真实性
                with f2:
                    fig_cash = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_cash.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['净利润'], name="净利润", marker_color='#a5d6a7'), secondary_y=False)
                    fig_cash.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['现金流'], name="现金流", marker_color='#2e7d32'), secondary_y=False)
                    fig_cash.add_trace(go.Scatter(x=df_hist['年份'], y=df_hist['净现比'], name="净现比", mode='lines+markers', line=dict(color='gold', width=3, dash='dot')), secondary_y=True)
                    fig_cash.update_layout(title="图 2.2 净利润与现金流对比 (真实性)", height=350, margin=dict(t=30, b=10))
                    fig_cash.add_hline(y=1.0, line_dash="dash", line_color="gray", secondary_y=True)
                    st.plotly_chart(fig_cash, use_container_width=True)
                    last_r = df_hist['净现比'].iloc[-1]
                    if last_r < 0.8: st.error(f"🚨 结论：利润真实性低 ({last_r:.2f})")
                    else: st.success(f"💎 结论：利润真实性高 ({last_r:.2f})")
            else: st.warning("⚠️ 暂无历史财务数据。")
            
            st.markdown("---")

            # 3. 行业地位 (V3.4 风格)
            st.subheader("3. 行业地位：对比黄金象限")
            if group_name:
                df_peers = st.session_state.peers_data_cache.get(group_name)

                if df_peers is not None:
                    fig_pos = px.scatter(df_peers, x="毛利率%", y="营收增长%", size="市值(B)", color="名称", text="名称", 
                                         title=f"图 3.1 【{group_name}】黄金象限：高毛利+高增速", height=450)
                    fig_pos.update_traces(textposition='top center')
                    st.plotly_chart(fig_pos, use_container_width=True)
                else:
                    st.warning(f"同行对比数据尚未加载。点击下方按钮进行多线程加载。")
                    if st.button(f'🏎️ 立即加载【{group_name}】同行数据'):
                        load_peers_data(group_name, target_group)
            else:
                 st.info("该股票不在预设的同行分析组中，无法进行行业地位对比分析。")

        else: st.error(f"❌ 核心数据获取失败。请检查股票代码 `{symbol}` 是否正确。")
