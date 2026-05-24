# Şifa Polikliniği

Tıbbi klinik yönetim sistemi. Hasta kayıt, randevu, doktor ve vezne işlemleri.

## Gereksinimler
- Python 3.8+
- PostgreSQL veya SQLite

## Kurulum
1. Sanal ortam (venv) oluştur: `python -m venv venv`
2. Sanal ortamı aktifleştir: `venv\Scripts\activate` (Windows)
3. Gerekli kütüphaneleri yükle: `pip install -r requirements.txt`
4. Bir `.env` dosyası oluşturup veritabanı adresini yazın:
   ```env
   DATABASE_URL=sqlite+aiosqlite:///./test.db
   ```

## Çalıştırma
```bash
uvicorn app.main:app --reload
```

## Testleri Çalıştırma
Bütün testleri çalıştırmak için şu komutu kullanın:
```bash
.\venv\Scripts\python.exe -m unittest tests/test_main.py
```

## Varsayılan Giriş Hesapları
- **Admin**: admin / admin123
- **Vezne**: vezne / vezne123
- **Kayıt**: kayit / kayit123
- **Rezervasyon**: rezervasyon / rezervasyon123