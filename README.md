# Şifa Polikliniği

Tıbbi klinik yönetim sistemi. Hasta kayıt, randevu ve doktor işlemleri.

## Gereksinimler
- Python 3.8+
- PostgreSQL

## Kurulum
1. Virtual environment oluştur: `python -m venv venv`
2. Aktifleştir: `venv\Scripts\activate` (Windows)
3. Bağımlılıkları yükle: `pip install -r requirements.txt`
4. PostgreSQL veritabanı oluştur (sifa_db)
5. `.env` dosyası oluştur:
   ```
   DATABASE_URL=postgresql+asyncpg://kullanici:sifre@localhost/sifa_db
   ```

## Çalıştırma
```
uvicorn app.main:app --reload
```

## Kullanıcılar
- Admin: admin / admin123
- Vezne: vezne / vezne123
- Kayıt: kayit / kayit123
- Rezervasyon: rezervasyon / rezervasyon123