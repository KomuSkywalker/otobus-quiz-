from flask import Flask, render_template, jsonify, request
import pandas as pd
import os
import requests # Firebase ile konuşmak için bu kütüphaneyi ekledik
from datetime import datetime

# --- AYARLAR ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
EXCEL_FILE = os.path.join(BASE_DIR, 'sorular.xlsx')

# --- FIREBASE AYARI (Burası Değişti) ---
# Harita projesindeki veritabanını kullanıyoruz, sonuna /bus_scores.json ekledik.
FIREBASE_DB_URL = "https://map-9488e-default-rtdb.firebaseio.com/bus_scores.json"

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

# --- SAYFALAR ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/hakkimizda')
def hakkimizda():
    return render_template('hakkimizda.html')

@app.route('/gizlilik')
def gizlilik():
    return render_template('gizlilik.html')

@app.route('/iletisim')
def iletisim():
    return render_template('iletisim.html')

# --- API: SORULARI GETİR (Excel Mantığı Aynen Korundu) ---
@app.route('/api/sorular')
def get_sorular():
    bolge_secimi = request.args.get('bolge', 'Karışık')

    try:
        if not os.path.exists(EXCEL_FILE):
            print("Excel dosyası bulunamadı!")
            return jsonify([])
        
        # Excel'i oku
        df = pd.read_excel(EXCEL_FILE, engine='openpyxl').fillna('')
        df.columns = df.columns.str.strip() 
        
        # Zorluk sütunu yoksa hepsini 2 (Zor) say
        if 'Zorluk' not in df.columns:
            df['Zorluk'] = 2
        else:
            df['Zorluk'] = pd.to_numeric(df['Zorluk'], errors='coerce').fillna(2).astype(int)

        # Bölgeye Göre Filtrele
        if 'Bolge' in df.columns:
            if bolge_secimi == 'Avrupa':
                df = df[df['Bolge'] == 'Avrupa']
            elif bolge_secimi == 'Anadolu':
                df = df[df['Bolge'] == 'Anadolu']
        
        # --- ALGORİTMA: 7 Kolay + 13 Zor ---
        pool_kolay = df[df['Zorluk'] == 1]
        pool_diger = df[df['Zorluk'] != 1] 
        
        # Yeterli soru var mı kontrolü
        if len(pool_kolay) < 7 or len(pool_diger) < 13:
            # Yeterli ayrım yoksa direkt rastgele 20 tane al
            final_df = df.sample(n=min(20, len(df))).reset_index(drop=True)
        else:
            pool_kolay = pool_kolay.sample(frac=1).reset_index(drop=True)
            pool_diger = pool_diger.sample(frac=1).reset_index(drop=True)
            secilen_kolay = pool_kolay.head(7)
            secilen_diger = pool_diger.head(13)
            final_df = pd.concat([secilen_kolay, secilen_diger])
        
        # JSON'a Çevir
        quiz_data = []
        for index, row in final_df.iterrows():
            if not str(row['Soru']).strip() or not str(row['Dogru_Cevap']).strip():
                continue

            soru_objesi = {
                "id": index + 1,
                "soru": str(row['Soru']),
                "secenekler": [str(row['A']), str(row['B']), str(row['C']), str(row['D'])],
                "dogru_cevap": str(row['Dogru_Cevap'])
            }
            quiz_data.append(soru_objesi)
            
        return jsonify(quiz_data)
        
    except Exception as e:
        print(f"Excel Hatası: {e}")
        return jsonify([])

# --- API: SKOR KAYDET (Firebase Entegrasyonu) ---
@app.route('/api/skor-kaydet', methods=['POST'])
def skor_kaydet():
    try:
        data = request.json
        isim = data.get('isim', 'Anonim').strip()[:15]
        puan = data.get('puan', 0)
        bolge = data.get('bolge', 'Karışık')
        
        if not isim: isim = "Anonim"
        bugun = datetime.now().strftime("%Y-%m-%d %H:%M")

        # SQLite Yerine Firebase'e Gönderiyoruz
        yeni_skor = {
            "isim": isim,
            "puan": puan,
            "bolge": bolge,
            "tarih": bugun
        }
        
        # requests kütüphanesi ile internete (Firebase'e) yazıyoruz
        requests.post(FIREBASE_DB_URL, json=yeni_skor)

        return jsonify({"mesaj": "Kaydedildi!"})
    except Exception as e:
        print(f"Skor Kayıt Hatası: {e}")
        return jsonify({"hata": str(e)})

# --- API: LİDERLİK TABLOSU (Firebase Entegrasyonu) ---
@app.route('/api/liderlik')
def liderlik_tablosu():
    try:
        # Firebase'den verileri çek
        response = requests.get(FIREBASE_DB_URL)
        
        if response.status_code != 200 or not response.json():
            return jsonify([])

        veriler = response.json()
        
        # Firebase verisi {"-Key1": {veri}, "-Key2": {veri}} şeklinde gelir.
        # Bunu listeye çevirmemiz lazım: [{veri}, {veri}]
        skor_listesi = []
        for key, value in veriler.items():
            skor_listesi.append(value)
        
        # Puana göre BÜYÜKTEN KÜÇÜĞE sırala
        # (reverse=True yüksek puan en üstte demek)
        skor_listesi = sorted(skor_listesi, key=lambda x: x.get('puan', 0), reverse=True)
        
        # İlk 15 kişiyi al
        top_15 = skor_listesi[:15]
        
        return jsonify(top_15)

    except Exception as e:
        print(f"Liderlik Hatası: {e}")
        return jsonify([])

if __name__ == '__main__':
    app.run(debug=True)
    