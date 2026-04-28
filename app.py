import streamlit as st
import pandas as pd
import io
import requests
import plotly.graph_objects as go

# 1. ページ設定
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# 2. デザイン修正（Amazonトンマナ & 選択行ハイライト）
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    input { color: #131921 !important; }
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', sans-serif !important;
    }
    #MainMenu, footer { visibility: hidden !important; }
    [data-testid="stSidebar"] { background-color: #131921 !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important; color: #131921 !important; border: 1px solid #D5D9D9 !important;
    }
    div[data-testid="stMetricValue"] {
        color: #131921 !important; font-weight: 800 !important; letter-spacing: -0.03em !important;
    }
    h1, h2, h3 { color: #131921 !important; font-weight: 800 !important; }
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
    df_s['年度'] = df_s['日付_dt'].apply(lambda x: f"{str(x.year - 1)[2:]}年度" if x.month <= 3 else f"{str(x.year)[2:]}年度")

    all_m = sorted(df_s['年月'].dropna().unique(), reverse=True)
    all_y = sorted(df_s['年度'].dropna().unique(), reverse=True)

    st.sidebar.title("Amazon Analytics")
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"], key="mode")
    st.sidebar.markdown("---")
    unit = st.sidebar.radio("表示単位を選択", ["月単位", "年度単位"], horizontal=True)

    if mode == "通常モード":
        opts = all_m if unit == "月単位" else all_y
        target_p = st.sidebar.selectbox("表示する期間を選択", opts, index=0, key="m1")
        comp_p = None
    else:
        opts = all_m if unit == "月単位" else all_y
        target_p = st.sidebar.selectbox("現在の期間（現在）", opts, index=0, key="m2")
        st.sidebar.markdown("---")
        c_unit = st.sidebar.radio("比較先の単位を選択", ["月単位", "年度単位"], horizontal=True, key="cu")
        c_opts = all_m if c_unit == "月単位" else all_y
        comp_p = st.sidebar.selectbox("比較する期間（比較）", c_opts, index=min(1, len(c_opts)-1), key="m3")

    df_f = pd.merge(df_s, df_m, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})

    def get_ana(df_b, df_t):
        df_t = df_t.sort_values('売上', ascending=False).reset_index(drop=True)
        tot = df_t['売上'].sum()
        df_t['比率'] = df_t['売上'].cumsum() / tot if tot > 0 else 0
        df_t['ABC'] = df_t['比率'].apply(lambda x: 'A' if x <= 0.7 else ('B' if x <= 0.9 else 'C'))
        avg = df_b.groupby('ASIN')['売上'].mean().reset_index()
        avg.columns = ['ASIN', 'avg']
        df_t = pd.merge(df_t, avg, on='ASIN', how='left')
        df_t['季節性'] = (df_t['売上'] / df_t['avg']).fillna(0)
        return df_t

    def filt(df, p):
        return df[df['年度'] == p] if "年度" in p else df[df['年月'] == p]

    raw_now = filt(df_f, target_p)
    sum_now = raw_now.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()
    sum_now = get_ana(df_f, sum_now)

    st.title("Sales Performance Dashboard")
    m1, m2, m3 = st.columns(3)
    v_now = sum_now['売上'].sum()

    if mode == "比較モード" and comp_p:
        raw_prev = filt(df_f, comp_p)
        sum_prev = raw_prev.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()
        v_prev = sum_prev['売上'].sum()
        pct = ((v_now / v_prev) - 1) * 100 if v_prev > 0 else 0
        m1.metric(f"売上 ({target_p})", f"¥{int(v_now):,}", f"{pct:+.1f}%")
        m2.metric(f"売上 ({comp_p})", f"¥{int(v_prev):,}")
    else:
        m1.metric(f"売上 ({target_p})", f"¥{int(v_now):,}")
        m2.metric("合計数量", f"{int(sum_now['数量'].sum()):,}")
    m3.metric("商品数", f"{len(sum_now):,}")

    # --- 商品詳細ドリルダウン機能 ---
    st.markdown("---")
    st.subheader("商品詳細ドリルダウン")
    
    # 選択用のリスト作成
    selected_asin = st.selectbox(
        "分析する商品を選択してください（商品名またはASINで検索可能）",
        options=sum_now['ASIN'].tolist(),
        format_func=lambda x: f"{sum_now[sum_now['ASIN']==x]['正式品名'].values[0]} ({x})",
        key="asin_selector"
    )

    if selected_asin:
        col_d1, col_d2 = st.columns([2, 1])
        
        # 選択商品の時系列データ抽出（直近12ヶ月分）
        prod_trend = df_f[df_f['ASIN'] == selected_asin].sort_values('日付_dt').tail(12)
        prod_info = sum_now[sum_now['ASIN'] == selected_asin].iloc[0]

        with col_d1:
            fig_prod = go.Figure()
            fig_prod.add_trace(go.Scatter(
                x=prod_trend['年月'], y=prod_trend['売上'],
                mode='lines+markers', name='売上推移',
                line=dict(color='#FF9900', width=4),
                marker=dict(size=10)
            ))
            fig_prod.update_layout(
                title=f"直近12ヶ月の売上推移: {prod_info['正式品名'][:30]}...",
                plot_bgcolor='white', height=350, margin=dict(l=0,r=0,t=40,b=0),
                yaxis=dict(showgrid=True, gridcolor='#F3F3F3', tickformat=',')
            )
            st.plotly_chart(fig_prod, use_container_width=True)

        with col_d2:
            st.write(f"**商品分析スコア**")
            st.info(f"""
            - **ランク**: {prod_info['ABC']}ランク
            - **季節性スコア**: {prod_info['季節性']:.2f}
            - **現在の数量**: {int(prod_info['数量']):,}
            """)
            if prod_info['季節性'] > 1.2:
                st.success("🔥 現在ハイシーズンです。在庫切れに注意してください。")
            elif prod_info['季節性'] < 0.8:
                st.warning("❄️ 現在ローシーズンです。販促を検討してください。")

    # --- 売上詳細分析テーブル ---
    st.markdown("---")
    st.subheader("売上詳細分析")
    
    def style_table(v):
        if v == 'A': return 'color: #FF9900; font-weight: 800;'
        if v == 'B': return 'color: #232F3E; font-weight: 700;'
        return 'color: #D5D9D9;'

    if mode == "比較モード" and comp_p:
        disp = pd.merge(sum_now, sum_prev[['ASIN', '売上', '数量']], on='ASIN', how='left', suffixes=('', '_c')).fillna(0)
        disp['売上MoM(%)'] = ((disp['売上'] / disp['売上_c']) - 1) * 100
        disp.loc[disp['売上_c'] == 0, '売上MoM(%)'] = 0
        disp['数量MoM(%)'] = ((disp['数量'] / disp['数量_c']) - 1) * 100
        disp.loc[disp['数量_c'] == 0, '数量MoM(%)'] = 0

        c_s_n, c_s_p = f"売上({target_p})", f"売上({comp_p})"
        c_q_n, c_q_p = f"数量({target_p})", f"数量({comp_p})"
        disp = disp[['ABC', 'ASIN', '正式品名', '規格', '売上', '売上_c', '売上MoM(%)', '数量', '数量_c', '数量MoM(%)', '季節性']].copy()
        disp.columns = ['ABC', 'ASIN', '正式品名', '規格', c_s_n, c_s_p, '売上MoM(%)', c_q_n, c_q_p, '数量MoM(%)', '季節性']
        fmt = {c_s_n: '¥{:,.0f}', c_s_p: '¥{:,.0f}', '売上MoM(%)': '{:+.1f}%', c_q_n: '{:,.0f}', c_q_p: '{:,.0f}', '数量MoM(%)': '{:+.1f}%', '季節性': '{:.2f}'}
    else:
        disp = sum_now[['ABC', 'ASIN', '正式品名', '規格', '売上', '数量', '季節性']].copy()
        disp.columns = ['ABC', 'ASIN', '正式品名', '規格', '売上', '数量', '季節性']
        fmt = {'売上': '¥{:,.0f}', '数量': '{:,.0f}', '季節性': '{:.2f}'}

    search = st.text_input("検索 (正式品名, ASIN)", "").lower()
    if search:
        disp = disp[disp['正式品名'].str.lower().str.contains(search, na=False) | disp['ASIN'].str.lower().str.contains(search, na=False)]

    st.dataframe(disp.style.format(fmt).map(style_table, subset=['ABC']), use_container_width=True, height=500, hide_index=True)

except Exception as e:
    st.error(f"システムエラー: {e}")