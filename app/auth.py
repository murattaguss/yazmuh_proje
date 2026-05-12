"""
Kimlik Doğrulama (Authentication) ve Güvenlik Modülü
Kullanıcı girişleri, şifre hashleme ve JWT (JSON Web Token) oluşturma işlemleri bu modülde yürütülür.
passlib ile şifreler güvenli bir şekilde saklanır.
"""
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models
from app.database import get_db

# Güvenlik için ortam değişkenlerine taşınması daha uygun olan gizli anahtarımız.
SECRET_KEY = "super_secret_key_sifa_poliklinik"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # Token'ın geçerlilik süresi (1 gün olarak ayarlandı)

# FastAPI'nin OAuth2 (şifre akışı) yapısı, giriş yapılacak endpoint'i işaret eder.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Kullanıcının girdiği düz metin şifreyi, veritabanındaki hashlenmiş şifreyle karşılaştırır."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """Yeni oluşturulan şifreleri veritabanına kaydetmeden önce güvenli hale getirir (hashler)."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Giriş yapan kullanıcıya oturumu boyunca kullanacağı JWT'yi üretir."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    # Token içerisine son geçerlilik tarihini 'exp' adıyla ekliyoruz
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """
    Korumalı tüm API uç noktalarında (endpoints) çağrılan bağımlılıktır.
    Gelen isteğin Header'ındaki token'ı çözer, kullanıcının kim olduğunu doğrular
    ve veritabanından kullanıcı bilgilerini getirerek yetkilendirme sağlar.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik doğrulama başarısız. Lütfen tekrar giriş yapın.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Token'ı gizli anahtarımızla açıp okumaya çalışıyoruz
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub") # 'sub' içerisine username koymuştuk
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # Kullanıcıyı veritabanında bul
    result = await db.execute(select(models.User).where(models.User.username == username))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user
