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

        display_name = info.get
