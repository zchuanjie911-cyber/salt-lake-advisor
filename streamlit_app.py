import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="全球价值猎手 v3.3", page_icon="🦁", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    div[data-testid="stDataFrame"] {font-size: 14px;}
    .big-font {font-size:20px !important; font-weight: bold;}
    div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 核心股票池
# ==========================================
STOCK_MAP = {
    # --- 🇺🇸 美股 ---
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊",
    "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威",
    "TSM": "台积电", "ASML": "阿斯麦", "CRM": "赛富时", "ORCL": "甲骨文",
    "INTC": "英特尔", "BABA": "阿里(美)", "PDD": "拼多多",
    "BRK-B": "伯克希尔", "V": "Visa", "MA": "万事达", "COST": "开市客",
    "MCD": "麦当劳", "KO": "可口可乐", "PEP": "百事", "LLY": "礼来",
    "NVO": "诺和诺德", "UNH": "联合健康", "JPM": "摩根大通", "JNJ": "强生",
    "PG": "宝洁", "XOM": "埃克森", "CVX": "雪佛龙", "DIS": "迪士尼",
    "NKE": "耐克", "O": "Realty Income", "WMT": "沃尔玛",
    
    # --- 🇭🇰 港股 ---
    "0700.HK": "腾讯", "9988.HK": "阿里(港)", "3690.HK": "美团",
    "0388.HK": "港交所", "0941.HK": "中移动", "0883.HK": "中海油",
    "1299.HK": "友邦", "0005.HK": "汇丰", "1088.HK": "神华",
    "1810.HK": "小米", "2015.HK": "理想",

    # --- 🇨🇳 A股 ---
    "600519.SS": "茅台", "000858.SZ": "五粮液", "600900.SS": "长电",
    "300750.SZ": "宁德时代", "002594.SZ": "比亚迪", "600660.SS": "福耀",
    "300760.SZ": "迈瑞", "600036.SS": "招行", "601318.SS": "平安",
    "601857.SS": "中石油", "601225.SS": "陕煤", "000792.SZ": "盐湖",
    "600030.SS": "中信", "600276.SS": "恒瑞"
}

MARKET_GROUPS = {
    "🇺🇸 美股科技 (AI & Chips)": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "AMD", "TSM", "ASML", "INTC", "CRM", "ORCL", "BABA", "PDD"],
    "🇺🇸 美股护城河 (Moat & Value)": ["BRK-B", "V", "MA", "COST", "MCD", "KO", "PEP", "LLY", "NVO", "UNH", "JPM", "JNJ", "PG", "XOM", "CVX", "DIS", "NKE", "O", "WMT"],
    "🇭🇰 港股核心 (High Div & Tech)": ["0700.HK", "9988.HK", "3690.HK", "0388.HK", "0941.HK", "0883.HK", "1299.HK", "0005.HK", "1088.HK", "1810.HK", "2015.HK"],
    "🇨🇳 A股核心 (Core Assets)": ["600519.SS", "000858.SZ", "600900.SS", "300750.SZ", "002594.SZ", "600660.SS", "300760.SZ", "600036.SS", "601318.SS", "601857.SS", "601225.SS", "000792.SZ", "600030.SS", "600276.SS"]
}

# ==========================================
# 2. 数据获取 (含汇率修正)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_financials(group_name):
    tickers = MARKET_GROUPS[group_name]
    data_list = []
    
    # 汇率修正补丁
    ADR_FIX = {
        "PDD": 7.25, 
        "BABA": 7.25, 
        "BIDU": 7.25, 
        "JD": 7.25, 
        "TSM": 32.5
    }

    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(tickers):
        cn_name = STOCK_MAP.get(symbol, symbol)
        status_text.text(f"🔍 正在估值: {cn_name} ({symbol})...")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            # --- 基础数据 ---
            mkt_cap = info.get('marketCap', 0)
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            
            # --- 商业模式 ---
            roe = info.get('returnOnEquity', 0) or 0
            net_margin = info.get('profitMargins', 0) or 0
            
            # --- 现金流修正 ---
            fcf = info.get('freeCashflow', 0)
            # 如果没有直接的FCF数据，尝试手动计算
            if fcf is None: 
                op_cash = info.get('operatingCashflow', 0) or 0
                capex = info.get('capitalExpenditures', 0) or 0 
                # FCF = 经营现金流 + 资本开支 (注意: capex通常是负数)
                fcf = op_cash + capex if capex < 0 else op_cash - capex

            # --- 应用汇率修正 ---
            fix_rate = ADR_FIX.get(symbol, 1.0) 
            
            # --- 核心估值计算 ---
            # FCF Yield = (FCF / 市值) / 汇率
            fcf_yield = ((fcf / mkt_cap) / fix_rate) if mkt_cap > 0 else 0
            
            # P/FCF 回本年限 = (市值 / FCF) * 汇率
            p_fcf = ((mkt_cap / fcf) * fix_rate) if fcf > 0 else 0
            
            div_yield = info.get('dividendYield', 0) or 0

            # 综合评分
            score = (fcf_yield * 100 * 5) + (roe * 100 * 3) + (div_yield * 100
