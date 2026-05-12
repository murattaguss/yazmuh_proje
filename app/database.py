"""
Veritabanı Bağlantı ve Oturum Yönetimi
Bu modül uygulamanın veritabanı (SQLite) ile asenkron iletişimini sağlar.
SQLAlchemy'nin asenkron özellikleri kullanılarak yüksek performanslı bir yapı hedeflenmiştir.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# Veritabanı motorunu oluşturuyoruz. 'echo=True' ile SQL sorgularını loglarda görebiliriz.
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# Asenkron veritabanı oturumlarını (session) yönetecek fabrika (factory) nesnesi.
# expire_on_commit=False, nesnelerin commit sonrası hemen veritabanından kopmamasını sağlar.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Tüm veritabanı modellerimizin (tabloların) miras alacağı temel sınıfımız
Base = declarative_base()

async def get_db():
    """
    FastAPI dependency injection (bağımlılık enjeksiyonu) için veritabanı oturumu sağlar.
    Her istek (request) için yeni bir session açılır ve işlem bitince güvenle kapatılır.
    """
    async with AsyncSessionLocal() as session:
        yield session
