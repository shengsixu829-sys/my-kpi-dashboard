# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
import requests
import os
import re

st.set_page_config(page_title="ストアカルテ", layout="wide")
LOGO_URL = "https://raw.githubusercontent.com/yone-lab/cart_log/main/j_logo.png"

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
SPREADSHEET_ID = "1KlZevjH2IbsV0kWQZxw1QjHy3EmsjG9vTKGtvVVTni8"
SAVE_SHEET_ID = "1_8XbvigwRRIR-HxT5OEDlrKdpW8J9AjYYtjEk33LPIk"

@st.cache_data(ttl=0) # 強制読み込み設定
def get_dynamic_month_config():
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheets = sh.worksheets()
        config = {}
        for ws in worksheets:
            title = ws.title.strip()
            if title.startswith("26"):
                nums = re.findall(r'\d+', title)
                if nums and len(nums[0]) >= 4:
                    month_num = int(nums[0][2:])
                    month_name = f"{month_num}月"
                    config[month_name] = str(ws.id)
        sorted_keys = sorted(config.keys(), key=lambda x: int(x.replace("月","")))
        return {k: config[k] for k in sorted_keys}
    except Exception as e:
        st.error(f"シート構成の取得に失敗しました: {e}")
        return {"3月": "1502960872", "4月": "166364340"}

DYNAMIC_MONTH_CONFIG = get_dynamic_month_config()

STORE_GROUPS = {
    "イオンモール": ["mozoワンダーシティ","THE OUTLETS HIROSHIMA","イオンモールKYOTO","イオンモール旭川西","イオンモール綾川","イオンモール伊丹昆陽","イオンモール羽生","イオンモール岡崎","イオンモール岡山","イオンモール各務原インター","イオンモール橿原","イオンモール宮崎","イオンモール京都桂川","イオンモール熊本","イオンモール広島府中","イオンモール高崎","イオンモール札幌発寒","イオンモール鹿児島","イオンモール春日部","イオンモール新潟亀田インター","イオンモール須坂","イオンモール水戸内原","イオンモール川口","イオンモール倉敷","イオンモール草津","イオンモール大高","イオンモール筑紫野","イオンモール長久手","イオンモール天童","イオンモール徳島","イオンモール苫小牧","イオンモール白山","イオンモール八幡東","イオンモール姫路大津","イオンモール浜松市野","イオンモール浜松志都呂","イオンモール福岡","イオンモール豊川","イオンモール幕張新都心","イオンモール名古屋茶屋","イオンモール名取","イオンモール鈴鹿","イオンモール和歌山","イオンレイクタウンmori"],
    "ららぽーと": ["ららぽーとEXPOCITY","ららぽーとTOKYO-BAY","ららぽーと愛知東郷","ららぽーと横浜","ららぽーと海老名","ららぽーと堺","ららぽーと沼津","ららぽーと湘南平塚","ららぽーと新三郷","ららぽーと富士見","ららぽーと福岡","ららぽーと名古屋みなとアクルス","ららぽーと門真","ららぽーと立川立飛","ららぽーと和泉"],
    "ショッピングモール": ["アクアシティお台場","あべのキューズモール","アリオ橋本","イーアスつくば","インターパークスタジアム","エミテラス所沢","エミフルMASAKI","おのだサンパーク","オリナス錦糸町","キャナルシティ博多","くずはモール","コクーンシティ","スマーク伊勢崎","セブンパークアリオ柏","トレッサ横浜","ならファミリー","なんばパークス","モラージュ菖浦","モレラ岐阜","ラソラ札幌","ララガーデン長町","浦添 PARCO CITY","新宿マルイ アネックス","神戸ハーバーランドumie","西宮ガーデンズ","大同生命札幌ビル miredo","二子玉川ライズ","有明ガーデン"],
    "アウトレット": ["りんくうプレミアム・アウトレット","三井アウトレットパーク岡崎","酒々井プレミアム・アウトレット","木更津"],
    "駅ビル": ["キラリナ京王吉祥寺","ルクア大阪","池袋サンシャインシティ"],
    "路面店": ["御堂筋本町","渋谷宮下公園前","八千代","名古屋栄"],
    "MARK IS": ["MARK IS みなとみらい","MARK IS 静岡","MARK IS 福岡ももち"],
    "アミュプラザ": ["アミュプラザおおいた","アミュプラザくまもと","アミュプラザ長崎"]
}

@st.cache_data(ttl=5)
def load_raw_data_auth(gid):
    try:
        import google.auth.transport.requests
        request = google.auth.transport.requests.Request()
        auth_creds.refresh(request)
        token = auth_creds.token
        export_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(export_url, headers=headers)
        if response.status_code == 200:
            return pd.read_csv(io.BytesIO(response.content), header=None)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def get_score(df, row, col):
    try:
        val = df.iloc[row-1, col-1]
        if pd.isna(val): return 0
        s_val = str(val).replace(',','').replace('%','').replace('¥','').replace('円','').strip()
        return pd.to_numeric(s_val, errors='coerce') if s_val else 0
    except: return 0

def fetch_sheet_text_live(search_key):
    try:
        sh = gc.open_by_key(SAVE_SHEET_ID)
        ws = sh.worksheet("シート1")
        all_data = ws.get_all_values()
        res = {"zasu": "", "tanka": "", "cvr": "", "kyaku": "", "summary": ""}
        search_key_clean = str(search_key).strip()
        for row in all_data:
            if row and str(row[0]).strip() == search_key_clean:
                res["zasu"] = str(row[1]) if len(row) > 1 else ""
                res["tanka"] = str(row[2]) if len(row) > 2 else ""
                res["cvr"] = str(row[3]) if len(row) > 3 else ""
                res["kyaku"] = row[4] if len(row) > 4 else ""
                res["summary"] = row[5] if len(row) > 5 else ""
                return res
        return res
    except:
        return {"zasu": "", "tanka": "", "cvr": "", "kyaku": "", "summary": ""}

def save_to_sheet_live(search_key, data_list):
    try:
        sh = gc.open_by_key(SAVE_SHEET_ID)
        ws = sh.worksheet("シート1")
        all_values = ws.get_all_values()
        target_row = -1
        search_key_clean = str(search_key).strip()
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

st.sidebar.header("📅 期間選択")
sel_year = "2026"
sel_month = st.sidebar.selectbox("月", list(DYNAMIC_MONTH_CONFIG.keys()), index=len(DYNAMIC_MONTH_CONFIG)-1)
week_row_map = {"W1": 57, "W2": 58, "W3": 59, "W4": 60, "W5": 61, "W6": 62}
week_juchu_start_map = {"W1": 12, "W2": 19, "W3": 26, "W4": 33, "W5": 40, "W6": 47}
sel_week = st.sidebar.selectbox("週", list(week_row_map.keys()))
current_key = f"{sel_year}-{sel_month}-{sel_week}"
current_txt = fetch_sheet_text_live(current_key)

with st.sidebar.form("input_form"):
    st.info(f"📍 読込中キー: {current_key}")
    r_zasu = st.text_area("座数の理由", value=current_txt["zasu"])
    r_tanka = st.text_area("客単価の理由", value=current_txt["tanka"])
    r_cvr = st.text_area("CVRの理由", value=current_txt["cvr"])
    r_kyaku = st.text_area("客数の理由", value=current_txt["kyaku"])
    sum_text = st.text_area("■総評 / 今週のアクション", value=current_txt["summary"], height=150)
    if st.form_submit_button("全ユーザーに共有保存"):
        if save_to_sheet_live(current_key, [r_zasu, r_tanka, r_cvr, r_kyaku, sum_text]):
            st.success("保存完了！")
            st.cache_data.clear()
            st.rerun()

current_gid = DYNAMIC_MONTH_CONFIG[sel_month]
df_raw = load_raw_data_auth(current_gid)

if not df_raw.empty:
    st.markdown(f'''
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
        <img src="{LOGO_URL}" style="height: 50px; width: auto; border-radius: 4px; object-fit: contain;">
        <h1 style="margin: 0; padding: 0; color: #3b484e; font-family: 'Meiryo', sans-serif; font-size: 2.2rem;">
            ストアカルテ {sel_year}年{sel_month}
        </h1>
    </div>
    ''', unsafe_allow_html=True)
    
    st.markdown('''
    <style>
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
    </style>
    ''', unsafe_allow_html=True)

    def fmt_v(val, cond, unit=""):
        cls = "reach" if cond else "unmet"
        t = f"{unit}{abs(val):,.0f}" if abs(val) >= 100 else f"{unit}{abs(val):.2f}"
        return f'<span class="{cls}">{t}</span>'

    def fmt_p(val, cond):
        cls = "reach" if cond else "unmet"
        return f'<span class="{cls}">{val:.1f}%</span>'

    act = sum([get_score(df_raw, i, 6) for i in range(12, 54)])
    tgt, bgt, ly = get_score(df_raw, 3, 7), get_score(df_raw, 3, 9), get_score(df_raw, 3, 11)
    mt, mb
