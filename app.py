# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
import requests
import os
import re
import base64  # 画像変換用に追加

# --- 1. ページ基本設定 ---
st.set_page_config(page_title="ストアカルテ", layout="wide")

# --- 2. ローカル画像読み込み関数 ---
def get_base64_image(image_path):
    """ローカルの画像ファイルをHTMLで表示可能な形式に変換する"""
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return None

# --- 3. Googleスプレッドシート接続設定 ---
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

# --- 4. シート自動検知ロジック ---
@st.cache_data(ttl=0)
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

# 業態・ストア対応リスト (変更なし)
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

# --- 5. サイドバー UI ---
st.sidebar.header("📅 期間選択")
sel_year = "2026"
sel_month = st.sidebar.selectbox("月", list(DYNAMIC_MONTH_CONFIG.keys()), index=len(DYNAMIC_MONTH_CONFIG)-1)

week_row_map = {"W1": 57, "W2": 58, "W3": 59, "W4": 60, "W5": 61, "W6": 62}
week_juchu_start_map = {"W1": 12, "W2": 19, "W3": 26, "W4": 33, "W5": 40, "W6": 47}

sel_week = st.sidebar.selectbox("週", list(week_row_map.keys()))

# ここで集計ロジックを回すなどの部分は変更なし...（中略）

# --- 6. メイン表示 ---
current_gid = DYNAMIC_MONTH_CONFIG[sel_month]
df_raw = load_raw_data_auth(current_gid)

if not df_raw.empty:
    # --- ロゴの読み込みと表示 ---
    logo_base64 = get_base64_image("logo.png")
    
    # HTMLでヘッダーを作成
    header_html = f'''
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 25px;">
    '''
    if logo_base64:
        header_html += f'<img src="data:image/png;base64,{logo_base64}" style="height: 55px; width: auto; object-fit: contain;">'
    else:
        # 画像がない場合のバックアップアイコン
        header_html += '<div style="font-size: 40px;">🏢</div>'
        
    header_html += f'''
        <h1 style="margin: 0; padding: 0; color: #3b484e; font-family: 'Meiryo', sans-serif; font-size: 2.2rem; font-weight: bold;">
            ストアカルテ {sel_year}年{sel_month}
        </h1>
    </div>
    '''
    st.markdown(header_html, unsafe_allow_html=True)
    
    # ...（以下、既存のテーブル表示・保存フォーム等は変更なし）
