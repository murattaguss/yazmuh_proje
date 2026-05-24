"""
Veritabanı bağlantısı.
SQLite ile asenkron çalışmak için bu modülü kullanıyoruz.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# Veritabanı motorunu oluşturduk, echo=True ile SQL sorgularını terminalde görebiliyoruz
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# Oturum (session) oluşturucu nesne
# expire_on_commit=False ile commit sonrasında nesnelerin veritabanından kopmasını önlüyoruz
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Modellerimizin miras alacağı ana sınıf
Base = declarative_base()

async def get_db():
    """
    FastAPI db bağlantısı için db oturumu açar.
    İşlem bitince otomatik kapanır.
    """
    async with AsyncSessionLocal() as session:
        yield session
