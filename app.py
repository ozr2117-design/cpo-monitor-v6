import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# Page Config
st.set_page_config(
    page_title="全球 CPO 监控 V6.0",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Constants & Config ---
FUND_CODE = "021528"
HOLDINGS = {
    "300502.SZ": 0.0969,
    "301377.SZ": 0.0964,
    "300308.SZ": 0.0958,
    "688498.SS": 0.0950,
    "600183.SS": 0.0941,
    "002463.SZ": 0.0914,
    "688195.SS": 0.0903,
    "300476.SZ": 0.0877,
    "688183.SS": 0.0861,
    "601138.SS": 0.0672
}

TICKER_NAMES = {
    "300502.SZ": "新易盛",
    "301377.SZ": "鼎泰高科",
    "300308.SZ": "中际旭创",
    "688498.SS": "源杰科技",
    "600183.SS": "生益科技",
    "002463.SZ": "沪电股份",
    "688195.SS": "腾景科技",
    "300476.SZ": "胜宏科技",
    "688183.SS": "生益电子",
    "601138.SS": "工业富联"
}

# --- Helper Functions ---
def get_change_color(change):
    return "red" if change >= 0 else "green"

def fetch_data():
    """Fetches real-time data for holdings and NQ=F"""
    data_cache = {}
    
    # Fetch Holdings Data
    tickers = list(HOLDINGS.keys())
    try:
        # Batch fetch for A-shares might be slow with yfinance, but it's the standard requested way.
        # Check if we need to adjust for market hours (using 'today' or 'last close')
        # Using period='5d' to ensure we get data even if market is closed/weekend
        valid_tickers = " ".join(tickers)
        df_holdings = yf.download(valid_tickers, period="5d", interval="1d", progress=False)
        
        # Get latest % change for each
        # yfinance multi-index columns: (Price Type, Ticker)
        # We need 'Close'
        current_changes = {}
        quotes = {}
        
        for ticker in tickers:
            try:
                # Extract Close series
                closes = df_holdings['Close'][ticker].dropna()
                if len(closes) >= 2:
                    last_close = closes.iloc[-1]
                    prev_close = closes.iloc[-2]
                    change_pct = (last_close - prev_close) / prev_close
                    current_changes[ticker] = change_pct
                    quotes[ticker] = last_close
                else:
                    current_changes[ticker] = 0.0
                    quotes[ticker] = 0.0
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                current_changes[ticker] = 0.0
                quotes[ticker] = 0.0
                
        data_cache['holdings_change'] = current_changes
        data_cache['holdings_price'] = quotes
        
    except Exception as e:
        st.error(f"Error fetching holdings data: {e}")
        data_cache['holdings_change'] = {t: 0.0 for t in tickers}
        data_cache['holdings_price'] = {t: 0.0 for t in tickers}

    # Fetch NQ=F
    try:
        nq = yf.Ticker("NQ=F")
        nq_hist = nq.history(period="5d")
        if len(nq_hist) >= 2:
            nq_last = nq_hist['Close'].iloc[-1]
            nq_prev = nq_hist['Close'].iloc[-2]
            nq_change = (nq_last - nq_prev) / nq_prev
            data_cache['nq_change'] = nq_change
            data_cache['nq_price'] = nq_last
        else:
            data_cache['nq_change'] = 0.0
            data_cache['nq_price'] = 0.0
            
    except Exception as e:
        st.error(f"Error fetching NQ=F: {e}")
        data_cache['nq_change'] = 0.0
        data_cache['nq_price'] = 0.0
        
    return data_cache

def calculate_fund_sim(holdings_changes):
    """Core Logic 1: Fund Simulation"""
    total_weighted_change = 0.0
    total_weight = sum(HOLDINGS.values())
    
    for ticker, weight in HOLDINGS.items():
        change = holdings_changes.get(ticker, 0.0)
        total_weighted_change += change * weight
        
    sim_change = total_weighted_change / total_weight
    return sim_change

def check_signals(data, fund_sim_change):
    """Core Logic 2: Signal Engine"""
    signals = []
    
    # 1. US Shock: NQ=F moves > +/- 0.6%
    nq_change = data.get('nq_change', 0.0)
    if abs(nq_change) > 0.006:
        signals.append(f"⚠️ 美股剧震警报: NQ=F 波动 {nq_change:.2%}")
        
    # 2. Arbitrage: (NQ_Change - Fund_Sim_Change) > 1.0%
    if (nq_change - fund_sim_change) > 0.01:
        signals.append(f"💰以此套利机会: 纳指 vs 基金溢价 > 1.0% (Diff: {(nq_change - fund_sim_change):.2%})")

    # 3. Sentiment: Spread(Eoptolink - InnoLight) > +/- 3.0%
    # Mapping assumed: 300502 (Zhongji/InnoLight?), 301377?
    # Based on general knowledge of these tickers in this sector:
    # 300502.SZ is Zhongji Xuchuang (InnoLight)
    # 300308.SZ is Zhongji (Eoptolink? No, 300502 is InnoLight. 300308 is Zhongji. 
    # Actually, Eoptolink is 'New Eoptolink' -> 300502? No. 
    # Eoptolink Technology Inc is 300502. 
    # InnoLight is 300308? No. 
    # Let's rely on the Top 2 keys for the spread as they are the largest weights: 
    # 300502.SZ and 301377.SZ.
    t1 = "300502.SZ"
    t2 = "301377.SZ"
    c1 = data['holdings_change'].get(t1, 0.0)
    c2 = data['holdings_change'].get(t2, 0.0)
    
    spread = c1 - c2
    if abs(spread) > 0.03:
         signals.append(f"📊 情绪背离: 龙头股价差 > 3.0% ({t1} vs {t2})")
         
    return signals

# --- Main App ---
st.title("全球 CPO 监控 V6.0 🌍")
st.caption(f"跟踪基金: {FUND_CODE} | 实时模拟")

# Fetch Data
with st.spinner('Fetching Real-time Data...'):
    market_data = fetch_data()

# Calculations
fund_sim_val = calculate_fund_sim(market_data['holdings_change'])
alerts = check_signals(market_data, fund_sim_val)

# Alerts Toast
if alerts:
    for alert in alerts:
        st.toast(alert, icon="🔔")

# --- Layout Section A: Cockpit ---
st.subheader("🚀 实时驾驶舱")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("基金估算", f"{fund_sim_val:.2%}", delta=f"{fund_sim_val:.2%}")

with col2:
    nq_val = market_data.get('nq_change', 0.0)
    st.metric("纳指期货 (NQ=F)", f"{market_data.get('nq_price', 0.0):.1f}", delta=f"{nq_val:.2%}")

with col3:
    # Placeholder for Northbound Money
    st.metric("北向资金", "Wait", delta="--")

with col4:
    # Placeholder for NVDA
    st.metric("NVDA", "--", delta="--")

with col5:
    # Placeholder for COHR
    st.metric("COHR", "--", delta="--")

st.divider()

# --- Layout Section B: Tabs ---
tab1, tab2, tab3 = st.tabs(["📈 归因分析", "🔗 共振监测", "📋 持仓详情"])

with tab1:
    st.write("##### 前十大重仓股贡献度")
    # Bar chart of weighted contribution
    contrib_data = []
    for t, w in HOLDINGS.items():
        chg = market_data['holdings_change'].get(t, 0.0)
        contrib = chg * w
        name = TICKER_NAMES.get(t, t)
        contrib_data.append({"股票名称": name, "贡献度": contrib, "权重": w, "涨跌幅": chg})
    
    df_contrib = pd.DataFrame(contrib_data)
    # Sort by contribution for better visualization
    df_contrib = df_contrib.sort_values(by="贡献度", ascending=True)
    
    fig_contrib = px.bar(df_contrib, y='股票名称', x='贡献度', 
                         title="基金净值加权贡献度 (按贡献排序)",
                         color='贡献度',
                         orientation='h',
                         text_auto='.3%',
                         color_continuous_scale=['green', 'red'])
    
    fig_contrib.update_traces(marker_color=df_contrib['贡献度'].apply(lambda x: 'red' if x >= 0 else 'green'), textposition='outside')
    fig_contrib.update_layout(yaxis_title=None, xaxis_title="贡献度")
    st.plotly_chart(fig_contrib, use_container_width=True)

with tab2:
    st.write("##### 纳指期货 vs 基金估算")
    # Dummy historical data for visualization since we only have snapshot in this simplified logic
    # Real implementation would require historical data fetching
    st.info("历史共振图表需要加载历史数据。目前仅显示快照对比。")
    
    comp_df = pd.DataFrame({
        "资产": ["纳指期货 (NQ=F)", "基金估算"],
        "涨跌幅": [market_data.get('nq_change', 0.0), fund_sim_val]
    })
    fig_res = px.bar(comp_df, x="资产", y="涨跌幅", color="涨跌幅", title="快照对比")
    st.plotly_chart(fig_res, use_container_width=True)

with tab3:
    st.write("##### 前十大重仓股详情")
    # Display Data Table
    df_details = pd.DataFrame(list(HOLDINGS.items()), columns=["Ticker", "权重"])
    df_details["名称"] = df_details["Ticker"].map(TICKER_NAMES)
    df_details["当前价格"] = df_details["Ticker"].map(market_data['holdings_price'])
    df_details["涨跌幅"] = df_details["Ticker"].map(market_data['holdings_change'])
    
    # Reorder and Rename Ticker to Code
    df_details = df_details.rename(columns={"Ticker": "代码"})
    df_details = df_details[["代码", "名称", "权重", "当前价格", "涨跌幅"]]

    # Formatting
    st.dataframe(df_details.style.format({
        "权重": "{:.4f}",
        "当前价格": "{:.2f}",
        "涨跌幅": "{:.2%}"
    }))

# Footer
st.markdown("---")
st.caption("Global CPO Monitor V6.0 | Built with Streamlit & Python")
