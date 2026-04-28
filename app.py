import streamlit as st
import pandas as pd
import io
import requests
import plotly.graph_objects as go

# 1. ページ設定
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# 2. デザイン修正
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stHeader"] { background-color: rgba(255, 255, 255, 0) !important; color: #131921 !important; }
    #MainMenu, footer { visibility: hidden !important; }
    [data-testid="stSidebar"] { background-color: #131921 !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }
    div[data-baseweb="select"] > div { background-color: #FFFFFF !important; color: #131921 !important; border: 1px solid #D5D9D9 !important; }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div { color: #131921 !important; font-weight: 700 !important; }
    div[data-testid="stMetricValue"] { color: #131921 !important; font-weight: 800 !important; letter-spacing: -0.03em !important; }
    .stDataFrame { font-family: 'Inter', sans-serif !important; }
    h1, h2, h3 { color: #131921 !important; font-weight: 800 !important; letter-spacing: -0.02em !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_data(url):
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return io.BytesIO(res.content)

try:
    df_m = pd.read_excel(load_data("http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"))
    df_s = pd.read_excel(load_data("http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"))

    df_s.columns = df_s.columns.str.strip()
    df_m.columns = df_m.columns.str.strip()
    for c in ['売上', '数量']:
        if c in df_s.columns:
            df_s[c] = pd.to_numeric(df_s[c].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    df_s['日付_dt'] = pd.to_datetime(df_s['日付'], format='%Y年%m月', errors='coerce')
    df_s['年月'] = df_s['日付_dt'].dt.strftime('%Y-%m')
    df_s['月'] = df_s['日付_dt'].dt.month
    
    # 年度計算 (4月開始)
    df_s['年度'] = df_s['日付_dt'].apply(lambda x: f"{str(x.year - 1)[2:]}年度" if x.month <= 3 else f"{str(x.year)[2:]}年度")

    all_months = sorted(df_s['年月'].dropna().unique(), reverse=True)
    all_years = sorted(df_s['年度'].dropna().unique(), reverse=True)
    all_options = all_years + all_months

    # --- サイドバー ---
    st.sidebar.title("Amazon Analytics")
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"], key="mode")
    st.sidebar.markdown("---")

    if mode == "通常モード":
        target_p = st.sidebar.selectbox("表示する期間を選択", all_options, index=0, key="m1")
        comp_p = None
    else:
        target_p = st.sidebar.selectbox("現在の期間（現在）", all_options, index=0, key="m2")
        comp_p = st.sidebar.selectbox("比較する期間（比較）", all_options, index=min(1, len(all_options)-1), key="m3")

    df_f = pd.merge(df_s, df_m, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})

    def filter_data(df, period):
        return df[df['年度'] == period] if "年度" in period else df[df['年月'] == period]

    main_res_raw = filter_data(df_f, target_p)
    main_sum = main_res_raw.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    # --- メインエリア ---
    st.title("Sales Performance Dashboard")
    m1, m2, m3 = st.columns(3)
    val_now = main_sum['売上'].sum()

    if mode == "比較モード":
        prev_res_raw = filter_data(df_f, comp_p)
        prev_sum = prev_res_raw.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()
        val_prev = prev_sum['売上'].sum()
        pct = ((val_now / val_prev) - 1) * 100 if val_prev > 0 else 0
        m1.metric(f"売上 ({target_p})", f"¥{int(val_now):,}", f"{pct:+.1f}%")
        m2.metric(f"売上 ({comp_p})", f"¥{int(val_prev):,}")
    else:
        m1.metric(f"売上 ({target_p})", f"¥{int(val_now):,}")
        m2.metric("合計数量", f"{int(main_sum['数量'].sum()):,}")
    m3.metric("商品数", f"{len(main_sum):,}")

    # --- グラフセクション (年度選択時のみ表示) ---
    if "年度" in target_p:
        st.subheader(f"月別売上実績 推移")
        
        # 4月から翌3月までの並び順を定義
        month_order = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
        
        fig = go.Figure()
        
        # 現在の年度データ
        now_trend = main_res_raw.groupby('月')['売上'].sum().reindex(month_order).fillna(0)
        fig.add_trace(go.Bar(
            x=[f"{m}月" for m in month_order], y=now_trend,
            name=target_p, marker_color='#FF9900',
            hovertemplate='売上: ¥%{y:,.0f}<extra></extra>'
        ))
        
        # 比較対象の年度データ
        if mode == "比較モード" and comp_p and "年度" in comp_p:
            prev_trend = prev_res_raw.groupby('月')['売上'].sum().reindex(month_order).fillna(0)
            fig.add_trace(go.Bar(
                x=[f"{m}月" for m in month_order], y=prev_trend,
                name=comp_p, marker_color='#A9A9A9',
                hovertemplate='売上: ¥%{y:,.0f}<extra></extra>'
            ))

        fig.update_layout(
            barmode='group', plot_bgcolor='white', paper_bgcolor='white',
            margin=dict(l=0, r=0, t=20, b=0), height=400,
            xaxis=dict(showline=True, linecolor='#D5D9D9'),
            yaxis=dict(showgrid=True, gridcolor='#F3F3F3', tickformat=',', title="売上(¥)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- 詳細テーブル ---
    st.markdown("---")
    st.subheader("売上詳細")
    if mode == "比較モード":
        disp = pd.merge(main_sum, prev_sum[['ASIN', '売上', '数量']], on='ASIN', how='outer', suffixes=('', '_比較')).fillna(0)
        disp['売上 MoM/YoY (%)'] = ((disp['売上'] / disp['売上_比較']) - 1) * 100
        disp.loc[disp['売上_比較'] == 0, '売上 MoM/YoY (%)'] = 0
        disp['数量 MoM/YoY (%)'] = ((disp['数量'] / disp['数量_比較']) - 1) * 100
        disp.loc[disp['数量_比較'] == 0, '数量 MoM/YoY (%)'] = 0
        
        c1, c2 = f"売上({target_p})", f"売上({comp_p})"
        c3, c4 = f"数量({target_p})", f"数量({comp_m if 'comp_m' in locals() else comp_p})"
        disp = disp[['ASIN', 'コード', '正式品名', '規格', '売上', '売上_比較', '売上 MoM/YoY (%)', '数量', '数量_比較', '数量 MoM/YoY (%)']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', c1, c2, '売上 MoM/YoY (%)', c3, c4, '数量 MoM/YoY (%)']
        fmt = {c1: '¥{:,.0f}', c2: '¥{:,.0f}', '売上 MoM/YoY (%)': '{:+.1f}%', c3: '{:,.0f}', c4: '{:,.0f}', '数量 MoM/YoY (%)': '{:+.1f}%'}
    else:
        disp = main_sum[['ASIN', 'コード', '正式品名', '規格', '売上', '数量']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', f"売上({target_p})", '数量']
        fmt = {f"売上({target_m if 'target_m' in locals() else target_p})": '¥{:,.0f}', '数量': '{:,.0f}'}

    search = st.text_input("クイック検索 (正式品名, コード, ASIN)", "").lower()
    if search:
        disp = disp[disp['正式品名'].str.lower().str.contains(search, na=False) | 
                    disp['コード'].astype(str).str.contains(search, na=False) | 
                    disp['ASIN'].str.lower().str.contains(search, na=False)]
    st.dataframe(disp.style.format(fmt), use_container_width=True, height=600)

except Exception as e:
    st.error(f"エラーが発生しました: {e}")