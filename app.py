import streamlit as st
import pandas as pd
import io
import requests
import plotly.graph_objects as go

# 1. ページ設定
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# 2. デザイン修正（Amazonトーン＆マナー）
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
    h1, h2, h3 { color: #131921 !important; font-weight: 800 !important; letter-spacing: -0.02em !important; }
    
    /* ABCランク用バッジスタイル */
    .badge-a { background-color: #FF9900; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
    .badge-b { background-color: #232F3E; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
    .badge-c { background-color: #D5D9D9; color: #131921; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
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

    all_months = sorted(df_s['年月'].dropna().unique(), reverse=True)
    all_years = sorted(df_s['年度'].dropna().unique(), reverse=True)

    # --- サイドバー ---
    st.sidebar.title("Amazon Analytics")
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"], key="mode")
    st.sidebar.markdown("---")
    unit = st.sidebar.radio("表示単位を選択", ["月単位", "年度単位"], horizontal=True)

    if mode == "通常モード":
        target_options = all_months if unit == "月単位" else all_years
        target_p = st.sidebar.selectbox("表示する期間を選択", target_options, index=0, key="m1")
        comp_p = None
    else:
        target_options = all_months if unit == "月単位" else all_years
        target_p = st.sidebar.selectbox("現在の期間（現在）", target_options, index=0, key="m2")
        st.sidebar.markdown("---")
        comp_unit = st.sidebar.radio("比較先の単位を選択", ["月単位", "年度単位"], horizontal=True, key="c_unit")
        comp_options = all_months if comp_unit == "月単位" else all_years
        comp_p = st.sidebar.selectbox("比較する期間（比較）", comp_options, index=min(1, len(comp_options)-1), key="m3")

    df_f = pd.merge(df_s, df_m, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})

    # --- 共通計算ロジック (ABC分析 & 季節性) ---
    def add_analytics(df_base, df_target):
        # ABC分析
        df_target = df_target.sort_values('売上', ascending=False)
        total_sales = df_target['売上'].sum()
        df_target['累計比率'] = df_target['売上'].cumsum() / total_sales if total_sales > 0 else 0
        df_target['ABC'] = df_target['累計比率'].apply(lambda x: 'A' if x <= 0.7 else ('B' if x <= 0.9 else 'C'))
        
        # 季節性スコア (選択月売上 / 商品別年間月平均売上)
        # 12ヶ月分程度の平均をとる
        avg_sales = df_base.groupby('ASIN')['売上'].mean().reset_index()
        avg_sales.columns = ['ASIN', '平均売上']
        df_target = pd.merge(df_target, avg_sales, on='ASIN', how='left')
        df_target['季節性'] = (df_target['売上'] / df_target['平均売上']).fillna(0)
        
        return df_target

    def filter_data(df, period):
        return df[df['年度'] == period] if "年度" in period else df[df['年月'] == period]

    main_res_raw = filter_data(df_f, target_p)
    main_sum = main_res_raw.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()
    main_sum = add_analytics(df_f, main_sum)

    # --- メインエリア ---
    st.title("Sales Performance Dashboard")
    m1, m2, m3 = st.columns(3)
    val_now = main_sum['売上'].sum()

    if mode == "比較モード" and comp_p:
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

    # --- グラフセクション ---
    if "年度" in target_p:
        st.subheader(f"月別売上実績 推移")
        month_order = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
        fig = go.Figure()
        now_trend = main_res_raw.groupby('月')['売上'].sum().reindex(month_order).fillna(0)
        fig.add_trace(go.Bar(x=[f"{m}月" for m in month_order], y=now_trend, name=target_p, marker_color='#FF9900'))
        if mode == "比較モード" and comp_p and "年度" in comp_p:
            prev_trend = prev_res_raw.groupby('月')['売上'].sum().reindex(month_order).fillna(0)
            fig.add_trace(go.Bar(x=[f"{m}月" for m in month_order], y=prev_trend, name=comp_p, marker_color='#A9A9A9'))
        fig.update_layout(barmode='group', plot_bgcolor='white', height=350, margin=dict(l=0,r=0,t=20,b=0))
        st.plotly_chart(fig, use_container_width=True)

    # --- 詳細テーブル ---
    st.markdown("---")
    st.subheader("売上詳細分析")

    # 比較モード用のデータ結合
    if mode == "比較モード" and comp_p:
        disp = pd.merge(main_sum, prev_sum[['ASIN', '売上', '数量']], on='ASIN', how='outer', suffixes=('', '_比較')).fillna(0)
        disp['売上 MoM/YoY (%)'] = ((disp['売上'] / disp['売上_比較']) - 1) * 100
        disp.loc[disp['売上_比較'] == 0, '売上 MoM/YoY (%)'] = 0
        disp['数量 MoM/YoY (%)'] = ((disp['数量'] / disp['数量_比較']) - 1) * 100
        disp.loc[disp['数量_比較'] == 0, '数量 MoM/YoY (%)'] = 0
        
        c1, c2 = f"売上({target_p})", f"売上({comp_p})"
        disp = disp[['ABC', 'ASIN', '正式品名', '規格', '売上', '売上_比較', '売上 MoM/YoY (%)', '季節性']]
        disp.columns = ['ABCランク', 'ASIN', '正式品名', '規格', c1, c2, 'MoM/YoY(%)', '季節性スコア']
        
        # 表示スタイルの設定
        st.dataframe(
            disp.style.format({c1: '¥{:,.0f}', c2: '¥{:,.0f}', 'MoM/YoY(%)': '{:+.1f}%', '季節性スコア': '{:.2f}'})
            .background_gradient(subset=['MoM/YoY(%)'], cmap='RdYlGn')
            .background_gradient(subset=['季節性スコア'], cmap='Oranges')
            .applymap(lambda x: 'font-weight: bold; color: #FF9900;' if x == 'A' else '', subset=['ABCランク']),
            use_container_width=True, height=600
        )
    else:
        disp = main_sum[['ABC', 'ASIN', '正式品名', '規格', '売上', '数量', '季節性']]
        disp.columns = ['ABCランク', 'ASIN', '正式品名', '規格', '売上', '数量', '季節性スコア']
        
        st.dataframe(
            disp.style.format({'売上': '¥{:,.0f}', '数量': '{:,.0f}', '季節性スコア': '{:.2f}'})
            .background_gradient(subset=['売上'], cmap='YlGnBu')
            .background_gradient(subset=['季節性スコア'], cmap='Oranges')
            .applymap(lambda x: 'font-weight: bold; color: #FF9900;' if x == 'A' else '', subset=['ABCランク']),
            use_container_width=True, height=600
        )

except Exception as e:
    st.error(f"エラーが発生しました: {e}")