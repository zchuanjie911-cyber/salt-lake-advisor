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
        years = income.columns[:4] 
        
        data = []
        for date in years:
            year_str = date.strftime("%Y")
            
            # 1. 营收与利润
            if 'Total Revenue' in income.index:
                rev = income.loc['Total Revenue', date]
            else:
                rev = 0
                
            if 'Net Income' in income.index:
                net_income = income.loc['Net Income', date]
            else:
                net_income = 0
            
            # 2. 资产负债 (应收 & 库存)
            if 'Receivables' in balance.index:
                receivables = balance.loc['Receivables', date]
            elif 'Net Receivables' in balance.index:
                receivables = balance.loc['Net Receivables', date]
            else:
                receivables = 0
            
            if 'Inventory' in balance.index:
                inventory = balance.loc['Inventory', date]
            else:
                inventory = 0
            
            # 3. 现金流 (FCF = 经营现金流 + 资本开支)
            # 注意：CAPEX通常为负数，所以是用加号
            if 'Operating Cash Flow' in cashflow.index:
                op_cash = cashflow.loc['Operating Cash Flow', date]
            else:
                op_cash = 0
                
            if 'Capital Expenditure' in cashflow.index:
                capex = cashflow.loc['Capital Expenditure', date]
            else:
                capex = 0
            
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
        
        # 翻转顺序，让时间从左到右 (2020 -> 2023)
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
    st.error("⚠️ 无法获取详细财务数据。请检查代码或该股票数据源缺失。")
    st.stop()

# 基础信息栏
price = info.get('currentPrice', info.get('regularMarketPrice', 0))
mkt_cap = info.get('marketCap', 0)
currency = info.get('currency', 'USD')
st.markdown(f"**当前价格**: {price} {currency} | **市值**: {mkt_cap/1e9:.2f} B")

# === 创建四个深度分析板块 ===
tab1, tab2, tab3, tab4 = st.tabs(["🛡️ 1. 商业模式", "💣 2. 财务雷达", "💰 3. 现金流估值", "⚔️ 4. 同业对比"])

# --- Tab 1: 商业模式 ---
with tab1:
    st.markdown("### 核心指标：这是一门好生意吗？")
    col1, col2, col3 = st.columns(3)
    
    roe = info.get('returnOnEquity', 0)
    gross_margin = info.get('grossMargins', 0)
    net_margin = info.get('profitMargins', 0)
    
    with col1:
        st.metric("ROE (净资产收益率)", f"{roe*100:.2f}%")
        fig_roe = go.Figure(go.Indicator(
            mode = "gauge+number", value = roe*100, title = {'text': "ROE 强度"},
            gauge = {'axis': {'range': [0, 50]}, 'bar': {'color': "#0f52ba"},
                     'steps': [{'range': [0, 15], 'color': "lightgray"}, {'range': [15, 50], 'color': "#e6f2ff"}]}
        ))
        fig_roe.update_layout(height=250, margin=dict(l=20,r=20,t=30,b=20))
        st.plotly_chart(fig_roe, use_container_width=True)
        
    with col2:
        st.metric("毛利率 (Gross Margin)", f"{gross_margin*100:.2f}%")
        fig_gm = go.Figure(go.Indicator(
            mode = "gauge+number", value = gross_margin*100, title = {'text': "毛利率壁垒"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#2E8B57"},
                     'steps': [{'range': [0, 40], 'color': "lightgray"}]}
        ))
        fig_gm.update_layout(height=250, margin=dict(l=20,r=20,t=30,b=20))
        st.plotly_chart(fig_gm, use_container_width=True)

    with col3:
        st.metric("净利率 (Net Margin)", f"{net_margin*100:.2f}%")
        st.info(f"""
        **分析师点评**:
        * **ROE**: {roe*100:.1f}% -> {"🌟 顶级生意" if roe > 0.2 else "✅ 良好生意" if roe > 0.15 else "⚠️ 普通生意"}
        * **毛利率**: {gross_margin*100:.1f}% -> {"🏰 强护城河" if gross_margin > 0.5 else "🛡️ 有一定壁垒" if gross_margin > 0.3 else "⚔️ 竞争激烈"}
        """)

# --- Tab 2: 财务排雷 (重点) ---
with tab2:
    st.markdown("### 🕵️‍♂️ 财务排雷：识破虚假繁荣")
    
    # 1. 营收质量分析：应收 vs 营收
    st.subheader("1. 卖货收得到钱吗？(应收账款 vs 营收)")
    c1, c2 = st.columns([3, 1])
    with c1:
        fig_rec = go.Figure()
        fig_rec.add_trace(go.Bar(
            x=df_fin['年份'], y=df_fin['营收'], 
            name='总营收', marker_color='lightblue'
        ))
        fig_rec.add_trace(go.Bar(
            x=df_fin['年份'], y=df_fin['应收账款'], 
            name='应收账款', marker_color='orange'
        ))
        fig_rec.update_layout(barmode='group', title="营收 vs 应收 (橙色不应增长过快)")
        st.plotly_chart(fig_rec, use_container_width=True)
    with c2:
        st.warning("**警惕**: 若【应收账款】增速 > 【营收】增速，说明可能在压货赊销。")

    st.divider()

    # 2. 库存风险分析：库存 vs 营收
    st.subheader("2. 货卖得出去吗？(存货 vs 营收)")
    c1, c2 = st.columns([3, 1])
    with c1:
        fig_inv = go.Figure()
        fig_inv.add_trace(go.Scatter(
            x=df_fin['年份'], y=df_fin['营收'], 
            name='总营收', line=dict(color='blue', width=3)
        ))
        fig_inv.add_trace(go.Scatter(
            x=df_fin['年份'], y=df_fin['存货'], 
            name='存货', line=dict(color='red', width=3, dash='dot')
        ))
        fig_inv.update_layout(title="营收(蓝) vs 存货(红)")
        st.plotly_chart(fig_inv, use_container_width=True)
    with c2:
        st.warning("**警惕**: 若【红线】飙升而【蓝线】走平，说明产品滞销。")

    st.divider()

    # 3. 盈利含金量：净利润 vs 现金流
    st.subheader("3. 赚的是真钱吗？(净利润 vs 经营现金流)")
    c1, c2 = st.columns([3, 1])
    with c1:
        fig_cash = go.Figure()
        fig_cash.add_trace(go.Bar(
            x=df_fin['年份'], y=df_fin['净利润'], 
            name='净利润', marker_color='#90EE90'
        ))
        fig_cash.add_trace(go.Bar(
            x=df_fin['年份'], y=df_fin['经营现金流'], 
            name='经营现金流', marker_color='#006400'
        ))
        fig_cash.update_layout(barmode='overlay', title="浅绿=纸面富贵 | 深绿=真金白银")
        st.plotly_chart(fig_cash, use_container_width=True)
    with c2:
        st.success("**优质**: 深绿柱子(现金流) 高于 浅绿柱子(利润) 为最佳。")

# --- Tab 3: 估值 ---
with tab3:
    st.markdown("### 💰 DCF 绝对估值模型")
    
    last_fcf = df_fin['自由现金流'].iloc[-1]
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("最新年度 FCF", f"{last_fcf/1e9:.2f} B")
        st.metric("设定增长率", f"{growth_rate_manual}%")
        st.metric("设定折现率", f"{discount_rate}%")
        
    with col_b:
        intrinsic
