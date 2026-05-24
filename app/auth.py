"""
Burası giriş, güvenlik ve token işleri için.
Şifre şifreleme ve token (JWT) üretme burada yapılıyor.
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

# Gizli anahtar (aslında .env'de olmalı)
SECRET_KEY = "super_secret_key_sifa_poliklinik"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # Token süresi (1 gün)

# Giriş yapma adresi
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Şifreleri karşılaştırır"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    """Şifreyi hashler (güvenlik için)"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Giriş yapan kullanıcı için token oluşturur"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    # Token'a bitiş süresini ekle
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """
    Giriş yapmış olan kullanıcıyı bulur.
    Token'ı çözüp veritabanından kullanıcıyı getirir.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik doğrulama başarısız. Lütfen tekrar giriş yapın.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Token'ı çözmeye çalış
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub") # sub içinde kullanıcı adı var
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # Veritabanında kullanıcıyı ara
    result = await db.execute(select(models.User).where(models.User.username == username))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user
