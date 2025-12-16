import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 0. 页面配置
# ==========================================
st.set_page_config(page_title="个股深度审计 v4.0", page_icon="🔬", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    .big-font {font-size:24px !important; font-weight: bold; color: #0f52ba;}
    .sub-font {font-size:18px !important; font-weight: bold; color: #333;}
    .metric-card {background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 工具函数：获取历史财报数据
# ==========================================
@st.cache_data(ttl=3600)
def get_deep_financials(ticker):
    stock = yf.Ticker(ticker)
    
    try:
        # 获取年度报表
        income = stock.income_stmt
        balance = stock.balance_sheet
        cashflow = stock.cashflow
        info = stock.info
        
        # 提取关键字段 (最近4年)
        years = income.columns[:4] # 取最近4列
        
        data = []
        for date in years:
            year_str = date.strftime("%Y")
            
            # 1. 营收与利润
            rev = income.loc['Total Revenue', date] if 'Total Revenue' in income.index else 0
            net_income = income.loc['Net Income', date] if 'Net Income' in income.index else 0
            
            # 2. 资产负债 (应收 & 库存)
            # 注意：不同行业科目名称可能不同，这里做简单容错
            receivables = balance.loc['Receivables', date] if 'Receivables' in balance.index else \
                          (balance.loc['Net Receivables', date] if 'Net Receivables' in balance.index else 0)
            
            inventory = balance.loc['Inventory', date] if 'Inventory' in balance.index else 0
            
            # 3. 现金流
            # FCF = 经营现金流 - 资本开支 (CAPEX通常为负，所以是 + )
            op_cash = cashflow.loc['Operating Cash Flow', date] if 'Operating Cash Flow' in cashflow.index else 0
            capex = cashflow.loc['Capital Expenditure', date] if 'Capital Expenditure' in cashflow.index else 0
            fcf = op_cash + capex 

            data.append({
                "年份": year_str,
                "营收": rev,
                "净利润": net_income,
                "应收账款": receivables,
                "存货": inventory,
                "经营现金流": op_cash,
                "自由现金流": fcf
            })
        
        # 翻转顺序，让时间从左到右
        df_fin = pd.DataFrame(data).iloc[::-1]
        return df_fin, info
        
    except Exception as e:
        return pd.DataFrame(), {}

# ==========================================
# 2. 工具函数：DCF计算器
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

# ==========================================
# 3. 侧边栏：输入区
# ==========================================
with st.sidebar:
    st.header("🔬 审计控制台")
    ticker_input = st.text_input("输入股票代码", value="NVDA", help="美股直接输代码，A股加.SS/.SZ，港股加.HK").upper().strip()
    
    st.divider()
    st.subheader("⚙️ 估值参数")
    discount_rate = st.slider("折现率 (%)", 6, 15, 9)
    growth_rate_manual = st.slider("预期增长率 (%)", 0, 30, 15)
    
    st.divider()
    st.subheader("🆚 同行对比 (逗号隔开)")
    peers_input = st.text_area("输入对手代码", value="AMD, INTC, TSM")

# ==========================================
# 4. 主逻辑
# ==========================================
if not ticker_input:
    st.stop()

st.title(f"📊 深度审计报告: {ticker_input}")

# 获取数据
df_fin, info = get_deep_financials(ticker_input)

if df_fin.empty:
    st.error("⚠️ 无法获取详细财务数据。请检查代码或该股票数据源缺失（如银行股可能没有存货数据）。")
    st.stop()

# 基础信息栏
price = info.get('currentPrice', info.get('regularMarketPrice', 0))
mkt_cap = info.get('marketCap', 0)
currency = info.get('currency', 'USD')
st.markdown(f"**当前价格**: {price} {currency} | **市值**: {mkt_cap/1e9:.2f} B")

# === 创建四个深度分析板块 ===
tab1, tab2, tab3, tab4 = st.tabs(["🛡️ 1. 商业模式与护城河", "💣 2. 财务雷达 (核心)", "💰 3. 现金流估值", "⚔️ 4. 同业对比"])

# --- Tab 1: 商业模式 ---
with tab1:
    st.markdown("### 核心指标：这是一门好生意吗？")
    col1, col2, col3 = st.columns(3)
    
    roe = info.get('returnOnEquity', 0)
    gross_margin = info.get('grossMargins', 0)
    net_margin = info.get('profitMargins', 0)
    
    with col1:
        st.metric("ROE (净资产收益率)", f"{roe*100:.2f}%", help="巴菲特最看重的指标，>15%为优秀")
        fig_roe = go.Figure(go.Indicator(
            mode = "gauge+number", value = roe*100,
            title = {'text': "ROE 强度"},
            gauge = {'axis': {'range': [0, 50]}, 'bar': {'color': "#0f52ba"},
                     'steps': [{'range': [0, 15], 'color': "lightgray"}, {'range': [15, 50], 'color': "#e6f2ff"}]}
        ))
        fig_roe.update_layout(height=250, margin=dict(l=20,r=20,t=30,b=20))
        st.plotly_chart(fig_roe, use_container_width=True)
        
    with col2:
        st.metric("毛利率 (Gross Margin)", f"{gross_margin*100:.2f}%", help="体现产品定价权和竞争壁垒")
        fig_gm = go.Figure(go.Indicator(
            mode = "gauge+number", value = gross_margin*100,
            title = {'text': "毛利率壁垒"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#2E8B57"},
                     'steps': [{'range': [0, 40], 'color': "lightgray"}]}
        ))
        fig_gm.update_layout(height=250, margin=dict(l=20,r=20,t=30,b=20))
        st.plotly_chart(fig_gm, use_container_width=True)

    with col3:
        st.metric("净利率 (Net Margin)", f"{net_margin*100:.2f}%", help="最终落袋的利润率")
        st.info(f"""
        **分析师点评**:
        * **ROE**: {roe*100:.1f}% -> {"🌟 顶级生意" if roe > 0.2 else "✅ 良好生意" if roe > 0.15 else "⚠️ 普通生意"}
        * **毛利率**: {gross_margin*100:.1f}% -> {"🏰 强护城河" if gross_margin > 0.5 else "🛡️ 有一定壁垒" if gross_margin > 0.3 else "⚔️ 竞争激烈"}
        """)

# --- Tab 2: 财务排雷 (重点) ---
with tab2:
    st.markdown("### 🕵️‍♂️ 财务排雷：识破虚假繁荣")
    
    # 数据归一化处理（为了画图好看，变成增长率或相对值）
    
    # 1. 营收质量分析：应收 vs 营收
    st.subheader("1. 卖货收得到钱吗？(应收账款 vs 营收)")
    c1, c2 = st.columns([3, 1])
    with c1:
        fig_rec = go.Figure()
        fig_rec.add_trace(go.Bar(x=df_fin['年份'], y=
