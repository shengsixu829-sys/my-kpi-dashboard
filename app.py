# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
import requests
import os
import re
import base64
import math

# --- 1. ページ基本設定 ---
st.set_page_config(page_title="ストアカルテ", layout="wide")

# 画像保存用のフォルダを自動作成
IMG_DIR = "saved_captures"
if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

# --- タイトル用ロゴ画像の読み込み ---
def get_logo():
    logo_path = "logo.png" 
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
            return f"data:image/png;base64,{data}"
    return None

LOGO_DATA = get_logo()

# --- 2. Googleスプレッドシート接続設定 ---
@st.cache_resource
def get_gspread_auth():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return creds
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

auth_creds = get_gspread_auth()
gc = gspread.authorize(auth_creds)

# データソースID
SPREADSHEET_ID = "1KlZevjH2IbsV0kWQZxw1QjHy3EmsjG9vTKGtvVVTni8"
SAVE_SHEET_ID = "1_8XbvigwRRIR-HxT5OEDlrKdpW8J9AjYYtjEk33LPIk"
TENPO_DATA_SP_ID = "1jJcIVOFTICCPr3YnoqkO-NxRzwTcvr_HfwgZunS0vdY"
WEEKLY_DATA_SP_ID = "1_lEdGhSnGzEIgMFn2Q_qUbCVIL35MVHQBxW0M_2TcyI"

# --- 3. 動的シート名判定とデータ読込ロジック ---
@st.cache_data(ttl=5)
def load_raw_data_by_sheet_name(sel_year_str, sel_month_str):
    try:
        year_suffix = str(sel_year_str)[2:]
        month_num = str(sel_month_str).replace("月", "").zfill(2)
        target_sheet_name = f"{year_suffix}{month_num}"
        
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(target_sheet_name)
        
        import google.auth.transport.requests
        request = google.auth.transport.requests.Request()
        auth_creds.refresh(request)
        token = auth_creds.token
        
        export_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={ws.id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(export_url, headers=headers)
        if response.status_code == 200:
            return pd.read_csv(io.BytesIO(response.content), header=None)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 業態マスター（完全なOPEN店舗のみ）とWeekly Dataの読み込み
@st.cache_data(ttl=5)
def load_mall_mapping_and_weekly_data():
    try:
        sh_tenpo = gc.open_by_key(TENPO_DATA_SP_ID)
        ws_tenpo = sh_tenpo.worksheet("店舗データ")
        df_tenpo = pd.DataFrame(ws_tenpo.get_all_values())
        
        mapping = {}
        for _, row in df_tenpo.iterrows():
            if len(row) > 18:
                store_name = str(row[2]).strip()
                op_cl_status = str(row[7]).strip()
                gyotai = str(row[18]).strip()
                
                if store_name and "店舗名" not in store_name and op_cl_status == "OPEN":
                    mapping[store_name] = gyotai
                    
        sh_weekly = gc.open_by_key(WEEKLY_DATA_SP_ID)
        ws_weekly = sh_weekly.worksheet("Data")
        df_weekly = pd.DataFrame(ws_weekly.get_all_values())
        return mapping, df_weekly
    except:
        return {}, pd.DataFrame()

def get_score(df, row, col):
    try:
        val = df.iloc[row-1, col-1]
        if pd.isna(val): return 0
        s_val = str(val).replace(',','').replace('%','').replace('¥','').replace('円','').strip()
        return pd.to_numeric(s_val, errors='coerce') if s_val else 0
    except: return 0

# --- 4. テキストの読み書き ---
def fetch_sheet_text_live(search_key):
    try:
        sh = gc.open_by_key(SAVE_SHEET_ID)
        ws = sh.worksheet("シート1")
        all_data = ws.get_all_values()
        res = {"zasu": "", "tanka": "", "cvr": "", "kyaku": "", "summary": ""}
        search_key_clean = str(search_key).strip()
        for row in all_data:
            if row and str(row[0]).strip() == search_key_clean:
                padded = row + [""] * (6 - len(row))
                res["zasu"], res["tanka"], res["cvr"], res["kyaku"], res["summary"] = padded[1:6]
                return res
        return res
    except:
        return {"zasu": "", "tanka": "", "cvr": "", "kyaku": "", "summary": ""}

def save_to_sheet_live(search_key, data_list):
    try:
        sh = gc.open_by_key(SAVE_SHEET_ID)
        ws = sh.worksheet("シート1")
        all_values = ws.get_all_values()
        target_row, search_key_clean = -1, str(search_key).strip()
        for i, row in enumerate(all_values):
            if row and str(row[0]).strip() == search_key_clean:
                target_row = i + 1
                break
        final_row = [search_key_clean] + [str(d) for d in data_list]
        if target_row != -1:
            ws.update(range_name=f"A{target_row}:F{target_row}", values=[final_row])
        else:
            ws.append_row(final_row)
        return True
    except: return False

def save_local_image(key, suffix, uploaded_file):
    if uploaded_file is not None:
        file_path = os.path.join(IMG_DIR, f"{key}_{suffix}.png")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

def get_local_image_path(key, suffix):
    file_path = os.path.join(IMG_DIR, f"{key}_{suffix}.png")
    return file_path if os.path.exists(file_path) else None

def ceil_p(val):
    if val is None or pd.isna(val): return 0.0
    return math.ceil(val * 10) / 10.0

# --- 5. サイドバー UI ---
st.sidebar.header("📅 期間選択")

year_list = ["2026", "2027", "2028"]
sel_year = st.sidebar.selectbox("年", year_list, index=0)

month_list = ["3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
sel_month = st.sidebar.selectbox("月", month_list, index=2)

week_row_map = {"W1": 57, "W2": 58, "W3": 59, "W4": 60, "W5": 61, "W6": 62}
sel_week = st.sidebar.selectbox("週", list(week_row_map.keys()))

current_key = f"{sel_year}-{sel_month}-{sel_week}"
current_txt = fetch_sheet_text_live(current_key)

with st.sidebar.form("input_form"):
    st.info(f"📍 読込中キー: {current_key}" )
    r_zasu = st.text_area("座数の理由", value=current_txt["zasu"])
    r_tanka = st.text_area("客単価の理由", value=current_txt["tanka"])
    r_cvr = st.text_area("CVRの理由", value=current_txt["cvr"])
    r_kyaku = st.text_area("客数の理由", value=current_txt["kyaku"])
    st.markdown("<p style='font-size:0.85em; font-weight:bold; margin-bottom:-5px;'>📸 キャプチャ添付</p>", unsafe_allow_html=True)
    img_juchu = st.file_uploader("受注額", type=["png", "jpg", "jpeg"])
    img_zasu = st.file_uploader("座数", type=["png", "jpg", "jpeg"])
    img_tanka = st.file_uploader("客単価", type=["png", "jpg", "jpeg"])
    img_cvr = st.file_uploader("CVR", type=["png", "jpg", "jpeg"])
    img_kyaku = st.file_uploader("客数", type=["png", "jpg", "jpeg"])
    img_sonota = st.file_uploader("その他", type=["png", "jpg", "jpeg"])
    sum_text = st.text_area("■総評 / 今週のアクション", value=current_txt["summary"], height=150)
    if st.form_submit_button("全ユーザーに共有保存"):
        if save_to_sheet_live(current_key, [r_zasu, r_tanka, r_cvr, r_kyaku, sum_text]):
            for s, f in [("juchu", img_juchu), ("zasu", img_zasu), ("tanka", img_tanka), ("cvr", img_cvr), ("kyaku", img_kyaku), ("sonota", img_sonota)]:
                save_local_image(current_key, s, f)
            st.success("保存しました！")
            st.cache_data.clear()
            st.rerun()

# --- 6. メイン表示 ---
df_raw = load_raw_data_by_sheet_name(sel_year, sel_month)

if not df_raw.empty:
    header_logo = f'<img src="{LOGO_DATA}" class="carte-logo" style="height: 50px; width: auto; border-radius: 4px; object-fit: contain;">' if LOGO_DATA else ""
    st.markdown(f'''<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">{header_logo}<h1 style="margin: 0; padding: 0; color: #3b484e; font-family: 'Meiryo', sans-serif; font-size: 2.2rem;">ストアカルテ {sel_year}年{sel_month}</h1></div>''', unsafe_allow_html=True)
    
    # 🌟 デザインCSS（PDF化・印刷時の縮尺をブラウザ画面と完全に一致させるチューニング）
    st.markdown('''<style>
        html, body, [class*="css"] { font-family: "Meiryo", sans-serif; color: #3b484e; }
        .reach { color: #58b5ca; font-weight: bold; }
        .unmet { color: #f3a359; font-weight: bold; }
        .base-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.85em; background-color: white; }
        .base-table th { background-color: rgba(88, 181, 202, 0.9); color: white; padding: 8px; border: 1px solid #eeece1; text-align: center; }
        .base-table td { border: 1px solid #eeece1; padding: 8px; text-align: center; }
        .kpi-table th { background-color: #3F484F !important; color: #eeece1 !important; }
        .comment-cell { text-align: left !important; background-color: #fdfcf7 !important; white-space: pre-wrap; vertical-align: middle; color: #3b484e; font-size: 0.95em; }
        .summary-box { background-color: #e1f2f7; border: 1px solid #58b5ca; padding: 15px; border-radius: 4px; white-space: pre-wrap; color: #3b484e; min-height: 80px; }
        h4 { color: #3b484e; border-bottom: 2px solid #fcde9c; padding-bottom: 5px; margin-top: 25px; }
        .img-label { font-size: 0.9em; font-weight: bold; color: #3b484e; margin-bottom: 5px; border-left: 3px solid #58b5ca; padding-left: 6px; }
        .empty-box { border: 1px dashed #cccccc; padding: 20px; border-radius: 4px; text-align: center; color: #888888; font-size: 0.8em; background-color: #fafafa; }
        .mall-share-table { border: 1.5px solid rgba(88, 181, 202, 0.9); width: 100%; border-collapse: collapse; font-size: 0.82rem; }
        .mall-share-table th { background-color: rgba(88, 181, 202, 0.9); color: white; border: 1px solid #eeece1; padding: 6px 4px; font-weight: normal; }
        .mall-share-table td { border: 1px solid #eeece1; padding: 6px 4px; text-align: center; }
        .mall-share-table tr.total-row { background-color: #f0f2f6; font-weight: bold; }
        .mall-share-table tr.total-row td { border-bottom: 2px solid rgba(88, 181, 202, 0.9); }
        
        /* 🌟 PDF印刷時のロゴ・キャプチャ巨大化バグ完全対策CSS */
        @media print {
            body { width: 100% !important; margin: 0 !important; padding: 10mm !important; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
            [data-testid="stSidebar"] { display: none !important; }
            
            /* 一番上のロゴを小さく固定 */
            .carte-logo { max-width: 120px !important; height: auto !important; object-fit: contain !important; }
            
            /* PDF化する際も横並び3列の構造を崩さずキープする */
            div:has(> [data-testid="stHorizontalBlock"]) { display: block !important; }
            [data-testid="stHorizontalBlock"] { display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important; gap: 15px !important; width: 100% !important; }
            [data-testid="stColumn"] { flex: 1 !important; width: 31% !important; min-width: 31% !important; max-width: 33% !important; display: block !important; }
            
            /* キャプチャが横幅いっぱいに引き伸ばされて潰れるのを防ぎ、画面と同じフォントバランスに固定 */
            .capture-img-wrapper { width: 100% !important; max-width: 280px !important; margin: 0 auto !important; }
            .capture-img-wrapper img { width: 100% !important; max-width: 100% !important; height: auto !important; object-fit: contain !important; image-rendering: -webkit-optimize-contrast !important; }
            
            table, .mall-share-table, .base-table { page-break-inside: avoid !important; font-size: 0.75rem !important; }
            h1 { font-size: 1.6rem !important; }
            h4 { font-size: 1.1rem !important; page-break-after: avoid !important; margin-top: 15px !important; }
            .summary-box { font-size: 0.8rem !important; }
        }
    </style>''', unsafe_allow_html=True)

    def fmt_v(val, cond, unit=""):
        cls = "reach" if cond else "unmet"
        t = f"{unit}{abs(val):,.0f}" if abs(val) >= 100 else f"{unit}{abs(val):.2f}"
        return f'<span class="{cls}">{t}</span>'

    def fmt_p(val, cond):
        cls = "reach" if cond else "unmet"
        return f'<span class="{cls}">{val:.1f}%</span>'

    # All Stores 予実
    act = sum([get_score(df_raw, i, 6) for i in range(12, 54)])
    tgt, bgt, ly = get_score(df_raw, 3, 7), get_score(df_raw, 3, 9), get_score(df_raw, 3, 11)
    mt, mb, ml = get_score(df_raw, 6, 7), get_score(df_raw, 6, 9), get_score(df_raw, 6, 11)
    st.markdown("<h4>All Stores ※FC excluded</h4>", unsafe_allow_html=True)
    st.markdown(f'''<table class="base-table"><tr><th style="background-color:#606970;">月次受注額</th><td colspan="5" style="font-size:1.2em;font-weight:bold;">{act:,.0f}</td></tr><tr><th>月次目標</th><td>{tgt:,.0f}</td><th>月次予算</th><td>{bgt:,.0f}</td><th>前年受注額</th><td>{ly:,.0f}</td></tr><tr><th>目標比</th><td>{fmt_p(act/tgt*100 if tgt else 0, act>=tgt)}</td><th>予算比</th><td>{fmt_p(act/bgt*100 if bgt else 0, act>=bgt)}</td><th>前年比</th><td>{fmt_p(act/ly*100 if ly else 0, act>=ly)}</td></tr><tr><th>差額</th><td>{fmt_v(act-tgt, act>=tgt)}</td><th>差額</th><td>{fmt_v(act-bgt, act>=bgt)}</td><th>差額</th><td>{fmt_v(act-ly, act>=ly)}</td></tr><tr><th>MTD目標</th><td>{mt:,.0f}</td><th>MTD予算</th><td>{mb:,.0f}</td><th>MTD前年</th><td>{ml:,.0f}</td></tr><tr><th>MTD目標%</th><td>{fmt_p(act/mt*100 if mt else 0, act>=mt)}</td><th>MTD予算%</th><td>{fmt_p(act/mb*100 if mb else 0, act>=mb)}</td><th>MTD前年%</th><td>{fmt_p(act/ml*100 if ml else 0, act>=ml)}</td></tr><tr><th>MTD目標 差額</th><td>{fmt_v(act-mt, act>=mt)}</td><th>MTD予算 差額</th><td>{fmt_v(act-mb, act>=mb)}</td><th>MTD前年 差額</th><td>{fmt_v(act-ml, act>=ml)}</td></tr></table>''', unsafe_allow_html=True)

    # WEEKサマリー
    st.markdown("<h4>WEEKサマリー</h4>", unsafe_allow_html=True)
    w_rows = ""
    for w_n, r_i in week_row_map.items():
        wa, wt, wb, wl = get_score(df_raw, r_i, 6), get_score(df_raw, r_i, 7), get_score(df_raw, r_i, 10), get_score(df_raw, r_i, 13)
        w_rows += f'<tr><td>{w_n}</td><td>{wa:,.0f}</td><td>{wt:,.0f}</td><td>{fmt_v(wa-wt, wa>=wt)}</td><td>{fmt_p(wa/wt*100 if wt else 0, wa>=wt)}</td><td>{wb:,.0f}</td><td>{fmt_v(wa-wb, wa>=wb)}</td><td>{fmt_p(wa/wb*100 if wb else 0, wa>=wb)}</td><td>{wl:,.0f}</td><td>{fmt_p(wa/wl*100 if wl else 0, wa>=wl)}</td></tr>'
    st.markdown(f'<table class="base-table"><tr><th>WEEK</th><th>受注額</th><th>目標</th><th>差額</th><th>達成率</th><th>予算</th><th>差額</th><th>達成率</th><th>前年実績</th><th>前年比</th></tr>{w_rows}</table>', unsafe_allow_html=True)

    # KPI別サマリー
    current_week_row_idx = week_row_map[sel_week]
    st.markdown(f"<h4>KPI別 ({sel_week})</h4>", unsafe_allow_html=True)
    k_data = [("座数", 44, 48, 52, "zasu"), ("客単価", 47, 51, 55, "tanka"), ("CVR", 45, 49, 53, "cvr"), ("客数", 46, 50, 54, "kyaku")]
    k_rows = ""
    for k_n, ac, tc, lc, t_k in k_data:
        av, tv, lv = get_score(df_raw, current_week_row_idx, ac), get_score(df_raw, current_week_row_idx, tc), get_score(df_raw, current_week_row_idx, lc)
        u, m = ("¥" if k_n == "客単価" else ""), ("◯" if (av/tv if tv else 0) >= 1 else "△" if (av/tv if tv else 0) >= 0.9 else "✕")
        reason = str(current_txt[t_k]).replace("\n", "<br>")
        k_rows += f'<tr><td>{m}</td><td>{k_n}</td><td>{u}{tv:,.0f}</td><td>{fmt_v(av, av>=tv, u)}</td><td>{fmt_p(av/tv*100 if tv else 0, av>=tv)}</td><td>{fmt_p(av/lv*100 if lv else 0, av>=lv)}</td><td class="comment-cell">{reason}</td></tr>'
    st.markdown(f'<div style="page-break-inside:avoid;"><table class="base-table kpi-table"><tr><th>評</th><th>KPI</th><th>目標</th><th>実績</th><th>目標比</th><th>LY比</th><th>理由</th></tr>{k_rows}</table></div>', unsafe_allow_html=True)

    # --- KPIグラフ（画面サイズ再現型・高精度レイアウト） ---
    st.markdown("<h4>📋 KPIグラフ(１ストア平均)</h4>", unsafe_allow_html=True)
    row1_cols = st.columns(3)
    row2_cols = st.columns(3)
    suffixes = [("juchu", "受注"), ("zasu", "座数"), ("tanka", "客単価"), ("cvr", "CVR"), ("kyaku", "客数"), ("sonota", "その他")]
    
    for i, (s, label) in enumerate(suffixes):
        col = row1_cols[i] if i < 3 else row2_cols[i-3]
        with col:
            st.markdown(f'<div class="img-label">{label}</div>', unsafe_allow_html=True)
            p = get_local_image_path(current_key, s)
            if p: 
                # 🌟 ラッパーを噛ませ、PDF出力時も横3列・最大280pxのコンパクトな縮尺を維持する
                st.markdown(f'<div class="capture-img-wrapper"><img src="data:image/png;base64,{base64.b64encode(open(p, "rb").read()).decode()}" style="width:100%; max-width:100%; height:auto; object-fit:contain; border-radius:4px; border:1px solid #eeece1;"></div>', unsafe_allow_html=True)
            else: 
                st.markdown('<div class="empty-box" style="max-width:280px; margin:0 auto;">未アップロード</div>', unsafe_allow_html=True)

    # --- モール別シェア ---
    st.markdown("<h4>📊 モール別シェア(過去10週推移)</h4>", unsafe_allow_html=True)
    mall_mapping, df_weekly = load_mall_mapping_and_weekly_data()
    if not df_weekly.empty and mall_mapping:
        header_row = [str(x).strip() for x in df_weekly.iloc[0].tolist()]
        
        year_suffix = str(sel_year)[2:]
        month_digit_z = str(sel_month).replace("月", "").zfill(2)
        
        matched_cols = []
        for i, h in enumerate(header_row):
            if f"{year_suffix}/{month_digit_z}/" in h or f"{sel_year}-{month_digit_z}-" in h or h.startswith(f"{year_suffix}/{month_digit_z}/"):
                matched_cols.append(i)
                
        week_idx = ["W1","W2","W3","W4","W5","W6"].index(sel_week) if sel_week in ["W1","W2","W3","W4","W5","W6"] else 0
        if matched_cols:
            base_col_idx = matched_cols[min(week_idx, len(matched_cols)-1)]
        else:
            base_col_idx = len(header_row)-1
        
        ten_weeks_indices = [base_col_idx - step for step in range(10) if base_col_idx - step >= 5]
        target_gyotais = ["全体", "路面店", "イオンモール", "ららぽーと", "アウトレット", "MARK IS", "アミュプラザ", "駅ビル", "ショッピングモール"]
        report_data = {g: {"count": 0, "weeks": {idx: 0 for idx in ten_weeks_indices}} for g in target_gyotais}
        unique_stores = {g: set() for g in target_gyotais}
        
        for r_idx in range(1, len(df_weekly)):
            st_name, kpi = str(df_weekly.iloc[r_idx, 1]).strip(), str(df_weekly.iloc[r_idx, 4]).strip()
            
            if st_name in mall_mapping and "受注金額(税抜)" in kpi:
                g = mall_mapping[st_name]
                if g in report_data:
                    unique_stores[g].add(st_name); unique_stores["全体"].add(st_name)
                    for c in ten_weeks_indices:
                        v = str(df_weekly.iloc[r_idx, c]).replace(',','').replace('¥','').strip()
                        val = pd.to_numeric(v, errors='coerce') if v else 0
                        if not pd.isna(val):
                            report_data[g]["weeks"][c] += val; report_data["全体"]["weeks"][c] += val
        
        for g in target_gyotais: report_data[g]["count"] = len(unique_stores[g])
        
        base_date = header_row[base_col_idx]
        header_html = f'<tr><th colspan="4" style="background-color:rgba(88, 181, 202, 0.9); font-weight:bold;">{base_date}</th>'
        for c in ten_weeks_indices[1:]: header_html += f'<th style="background-color:rgba(88, 181, 202, 0.9); font-weight:bold;">{header_row[c]}</th>'
        header_html += '</tr><tr><th>業態</th><th>ストア数</th><th>受注実績</th><th>売上シェア</th>'
        for _ in ten_weeks_indices[1:]: header_html += '<th>売上シェア</th>'
        header_html += '</tr>'
        
        rows_html, total_base = "", report_data["全体"]["weeks"].get(base_col_idx, 0)
        for g in target_gyotais:
            cls = ' class="total-row"' if g == "全体" else ""
            g_cnt, g_act = report_data[g]["count"], report_data[g]["weeks"].get(base_col_idx, 0)
            share = ceil_p(g_act / total_base * 100 if total_base else 0) if g != "全体" else 100.0
            row = f'<tr{cls}><td>{g}</td><td>{g_cnt}</td><td>{g_act:,.0f}</td><td>{share:.1f}%</td>'
            for c in ten_weeks_indices[1:]:
                w_tot, w_act = report_data["全体"]["weeks"].get(c, 0), report_data[g]["weeks"].get(c, 0)
                w_share = ceil_p(w_act / w_tot * 100 if w_tot else 0) if g != "全体" else 100.0
                row += f'<td>{w_share:.1f}%</td>'
            rows_html += row + '</tr>'
        st.markdown(f'<div style="page-break-inside:avoid;"><table class="mall-share-table">{header_html}{rows_html}</table></div>', unsafe_allow_html=True)
    else:
        st.info("データ取得中...")

    st.markdown("<h4>■総評 / 今週のアクション</h4>", unsafe_allow_html=True)
    st.markdown(f'<div class="summary-box" style="page-break-inside:avoid;">{str(current_txt["summary"])}</div>', unsafe_allow_html=True)
else:
    st.warning("指定された月のデータシート（例：2605）を読み込めませんでした。シート名を確認してください。")
