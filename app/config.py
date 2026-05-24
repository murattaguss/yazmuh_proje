"""
Ayarlar dosyası.
.env dosyasındaki değişkenleri okumak için.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Veritabanı adresi (.env'den okunacak)
    DATABASE_URL: str
    
    # .env dosyasını okumak için gereken ayar
    model_config = SettingsConfigDict(env_file=".env")

# Ayarlar nesnesi
settings = Settings()
