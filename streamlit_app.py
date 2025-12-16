import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="核心三维分析 v10.0", page_icon="🎯", layout="wide")
st.markdown("""<style>.stApp {background-color: #f8f9fa;} .big-font {font-size:20px !important; font-weight: bold;} div[data-testid="stMetricValue"] {font-size: 24px; color: #0f52ba;}</style>""", unsafe_allow_html=True)

# ==========================================
# 1. 基础数据与映射
# ==========================================
STOCK_MAP = {
    "AAPL": "苹果", "MSFT": "微软", "GOOG": "谷歌", "AMZN": "亚马逊", "META": "Meta", "TSLA": "特斯拉", "NVDA": "英伟达", "AMD": "超威",
    "TSM": "台积电", "ASML": "阿斯麦", "BABA": "阿里(美)", "PDD": "拼多多", "JD": "京东", "BIDU": "百度", "NTES": "网易",
    "0700.HK": "腾讯", "9988.HK": "阿里(港)", "3690.HK": "美团", "0388.HK": "港交所", "0941.HK": "中移动", "0883.HK": "中海油",
    "1299.HK": "友邦", "0005.HK": "汇丰", "1088.HK": "神华", "1810.HK": "小米", "2015.HK": "理想", "0981.HK": "中芯国际",
    "600519.SS": "茅台", "000858.SZ": "五粮液", "600900.SS": "长电", "300750.SZ": "宁德时代", "002594.SZ": "比亚迪", "600660.SS": "福耀",
    "300760.SZ": "迈瑞", "600036.SS": "招行", "601318.SS": "平安", "601857.SS": "中石油", "601225.SS": "陕煤", "000792.SZ": "盐湖"
}
NAME_TO_TICKER = {v: k for k, v in STOCK_MAP.items()}

# 用于“行业地位”对比的默认参照组
MARKET_GROUPS = {
    "科技巨头": ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "TSM", "0700.HK", "BABA"],
    "中国核心资产": ["600519.SS", "000858.SZ", "300750.SZ", "002594.SZ", "601318.SS", "600036.SS", "000792.SZ"],
    "高股息/资源": ["0883.HK", "1088.HK", "601857.SS", "601225.SS", "600900.SS", "0941.HK"]
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

@st.cache_data(ttl=3600)
def fetch_analysis_data(symbol):
    """获取单只股票的详细财务数据"""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        inc = stock.income_stmt
        bal = stock.balance_sheet
        cf = stock.cashflow
        
        # 1. 商业模式数据
        biz_model = {
            "ROE": info.get('returnOnEquity', 0),
            "毛利率": info.get('grossMargins', 0),
            "净利率": info.get('profitMargins', 0)
        }
        
        # 2. 财务历史数据 (用于图表)
        history = []
        if not inc.empty:
            years = inc.columns[:5] # 取最近5年
            for d in years:
                item = {}
                item["年份"] = d.strftime("%Y")
                item["营收"] = inc.loc['Total Revenue', d] if 'Total Revenue' in inc.index else 0
                item["应收"] = bal.loc['Receivables', d] if 'Receivables' in bal.index else 0
                item["净利润"] = inc.loc['Net Income', d] if 'Net Income' in inc.index else 0
                item["现金流"] = cf.loc['Operating Cash Flow', d] if 'Operating Cash Flow' in cf.index else 0
                history.append(item)
        
        return info, biz_model, pd.DataFrame(history).iloc[::-1]
    except: return None, None, pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_peers_data(current_symbol):
    """获取同行业对比数据 (用于行业地位)"""
    # 简单逻辑：找到当前股票所在的组，或者默认跟科技股比
    target_group = MARKET_GROUPS["科技巨头"]
    for group_name, tickers in MARKET_GROUPS.items():
        if current_symbol in tickers:
            target_group = tickers
            break
            
    peers_data = []
    for t in target_group:
        try:
            s = yf.Ticker(t)
            i = s.info
            peers_data.append({
                "代码": t,
                "名称": STOCK_MAP.get(t, t),
                "市值(B)": (i.get('marketCap', 0) or 0) / 1e9,
                "毛利率%": (i.get('grossMargins', 0) or 0) * 100,
                "营收增长%": (i.get('revenueGrowth', 0) or 0) * 100
            })
        except: continue
    return pd.DataFrame(peers_data)

# ==========================================
# 3. 主界面逻辑
# ==========================================
with st.sidebar:
    st.header("🎯 核心三维分析")
    st.info("请输入代码或中文，如 `600519` 或 `英伟达`")
    raw_input = st.text_input("分析对象:", "NVDA").strip()
    symbol = smart_parse_symbol(raw_input)

st.title(f"📊 个股核心报告: {symbol}")

if symbol:
    info, biz, df_hist = fetch_analysis_data(symbol)
    
    if info and not df_hist.empty:
        cn_name = STOCK_MAP.get(symbol, info.get('shortName', symbol))
        st.subheader(f"{cn_name}")

        # ==========================================
        # 第一维：商业模式 (好生意吗？)
        # ==========================================
        st.markdown("---")
        st.header("1. 🏢 商业模式判研")
        
        c1, c2, c3 = st.columns(3)
        
        # 1. ROE 仪表盘
        with c1:
            val = biz['ROE'] * 100
            fig = go.Figure(go.Indicator(
                mode = "gauge+number", value = val,
                title = {'text': "ROE (赚钱效率)"},
                gauge = {'axis': {'range': [0, 40]},
                         'bar': {'color': "#00c853" if val > 15 else "#ff4b4b"},
                         'steps': [{'range': [0, 15], 'color': "#f0f0f0"}, {'range': [15, 40], 'color': "#e8f5e9"}]}
            ))
            fig.update_layout(height=250, margin=dict(l=10,r=10,t=40,b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            check = "✅ 优秀" if val > 15 else "⚠️ 一般"
            st.caption(f"**结论**: {check}。ROE反映股东投入的每一块钱能生出多少利。>15%为门槛。")

        # 2. 毛利率 仪表盘
        with c2:
            val = biz['毛利率'] * 100
            fig = go.Figure(go.Indicator(
                mode = "gauge+number", value = val,
                title = {'text': "毛利率 (护城河)"},
                gauge = {'axis': {'range': [0, 100]},
                         'bar': {'color': "#2962ff" if val > 40 else "#ff9800"},
                         'steps': [{'range': [0, 40], 'color': "#f0f0f0"}]}
            ))
            fig.update_layout(height=250, margin=dict(l=10,r=10,t=40,b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            check = "🏰 极深" if val > 60 else ("🛡️ 稳固" if val > 40 else "⚔️ 激烈")
            st.caption(f"**结论**: {check}。毛利率越高，定价权越强，越不怕价格战。")

        # 3. 净利率 仪表盘
        with c3:
            val = biz['净利率'] * 100
            st.metric("净利率 (最终落袋)", f"{val:.2f}%")
            st.progress(min(int(val), 100))
            st.info("""
            **判研逻辑**: 
            * **ROE > 20%**: 顶级印钞机
            * **毛利 > 40%**: 具备竞争优势
            * **净利 > 20%**: 盈利质量极高
            """)

        # ==========================================
        # 第二维：行业地位与周期 (老大还是小弟？)
        # ==========================================
        st.markdown("---")
        st.header("2. 🏔️ 行业地位与周期")
        
        # 自动拉取同行
        df_peers = fetch_peers_data(symbol)
        
        col_p1, col_p2 = st.columns([2, 1])
        
        with col_p1:
            if not df_peers.empty:
                # 气泡图：横轴=毛利率，纵轴=营收增长，大小=市值
                fig_pos = px.scatter(
                    df_peers, x="毛利率%", y="营收增长%", size="市值(B)", color="名称",
                    text="名称", title="行业格局图 (右上角为 最强+最快)",
                    labels={"毛利率%": "竞争力 (毛利率)", "营收增长%": "成长性 (增速)"},
                    height=400
                )
                # 标记当前股票
                fig_pos.update_traces(textposition='top center')
                st.plotly_chart(fig_pos, use_container_width=True)
            else:
                st.warning("暂无同行数据对比")

        with col_p2:
            st.markdown("#### 📈 自身成长周期")
            # 简单的营收趋势线
            fig_cycle = px.line(df_hist, x="年份", y="营收", markers=True, title="营收历史走势")
            fig_cycle.update_traces(line_color='#6200ea', line_width=3)
            fig_cycle.update_layout(height=300)
            st.plotly_chart(fig_cycle, use_container_width=True)
            st.caption("看曲线斜率：向上陡峭=成长期；走平=成熟期；向下=衰退期。")

        # ==========================================
        # 第三维：财务分析 (真假与健康)
        # ==========================================
        st.markdown("---")
        st.header("3. 🔎 财务质量体检")
        
        f1, f2 = st.columns(2)
        
        # 1. 营收含金量 (营收 vs 应收)
        with f1:
            fig_rev = go.Figure()
            fig_rev.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['营收'], name='总营收', marker_color='lightblue'))
            fig_rev.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['应收'], name='应收账款', marker_color='orange'))
            fig_rev.update_layout(title="营收含金量 (橙柱越低越好)", barmode='group')
            st.plotly_chart(fig_rev, use_container_width=True)
            st.warning("**关键点**: 如果橙色柱子(应收)增长比蓝色(营收)快，说明在压货，业绩有水分。")
            
        # 2. 利润含金量 (利润 vs 现金流)
        with f2:
            fig_cash = go.Figure()
            fig_cash.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['净利润'], name='净利润 (纸面)', marker_color='#a5d6a7'))
            fig_cash.add_trace(go.Bar(x=df_hist['年份'], y=df_hist['现金流'], name='现金流 (真钱)', marker_color='#2e7d32'))
            fig_cash.update_layout(title="利润含金量 (深绿覆盖浅绿为优)", barmode='overlay')
            st.plotly_chart(fig_cash, use_container_width=True)
            st.success("**关键点**: 现金流(深绿)长期高于净利润(浅绿)，才是真正的赚钱机器(如茅台、腾讯)。")

    else:
        st.error("数据获取失败，请检查代码拼写。")
