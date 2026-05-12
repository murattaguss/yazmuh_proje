"""
Yapılandırma (Configuration) Modülü
Projenin çevresel (environment) değişkenlerini yönettiğimiz kısımdır.
pydantic_settings kullanılarak tip güvenli (type-safe) bir konfigürasyon sağlanmıştır.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Veritabanı bağlantı dizesi .env dosyasından okunacaktır.
    DATABASE_URL: str
    
    # .env dosyasının okunması için Pydantic V2 uyumlu ayarlar
    model_config = SettingsConfigDict(env_file=".env")

# Tüm uygulamada kullanılacak ayarlar nesnemizi oluşturuyoruz.
settings = Settings()
