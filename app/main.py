"""
FastAPI Ana Uygulama (Main) Modülü
Projenin kalbi burasıdır. Tüm API uç noktaları (endpoints), bağımlılıklar (dependencies)
ve veritabanı başlangıç ayarları (startup events) bu modülde birleştirilir.
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import datetime
import os

from app import models, schemas, crud, auth
from app.database import engine, get_db

# FastAPI uygulamasını oluşturuyoruz
app = FastAPI(
    title="Şifa Polikliniği",
    description="Hasta kayıt, rezervasyon, doktor muayene ve vezne/ödeme modüllerini içeren API.",
    version="1.0.0"
)

# Frontend dosyalarını sunmak için bir dizin oluşturuyoruz (Yoksa hata vermemesi için)
os.makedirs("frontend", exist_ok=True)
# /static adresi üzerinden frontend klasörüne erişim sağlıyoruz
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Kök dizine girildiğinde (örn: localhost:8000/) direkt olarak index.html sayfasını sunar."""
    return FileResponse("frontend/index.html")

@app.on_event("startup")
async def startup():
    """
    Uygulama ilk başlatıldığında çalışacak olaydır.
    1. Veritabanı tablolarını yoksa oluşturur.
    2. Sistemin çalışabilmesi için örnek klinikler, doktor ve yönetici hesaplarını oluşturur (Seed Data).
    """
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        
    from app.database import AsyncSessionLocal
    from sqlalchemy.future import select
    
    async with AsyncSessionLocal() as db:
        # Örnek klinikler var mı diye kontrol ediyoruz
        result = await db.execute(select(models.Clinic).limit(1))
        if not result.scalar_one_or_none():
            clinics = ["Göz", "Üroloji", "Ortopedi", "Psikiyatri"]
            db_clinics = []
            for c_name in clinics:
                new_clinic = models.Clinic(name=c_name)
                db.add(new_clinic)
                db_clinics.append(new_clinic)
            await db.commit()
            
            # Eklenen her kliniğe bir adet örnek doktor atıyoruz
            import datetime
            doctor_names = [
                ("Ahmet", "Yılmaz"),
                ("Mehmet", "Kaya"),
                ("Ayşe", "Demir"),
                ("Fatma", "Çelik")
            ]
            for i, clinic in enumerate(db_clinics):
                await db.refresh(clinic)
                f_name, l_name = doctor_names[i % len(doctor_names)]
                new_doc = models.Doctor(
                    first_name=f_name, 
                    last_name=l_name, 
                    tc_no=f"100000000{i:02d}",
                    birth_date=datetime.date(1980, 1, 1),
                    phone_number=f"555000000{i}",
                    clinic_id=clinic.id
                )
                db.add(new_doc)
            await db.commit()
            
        # Temel sistem kullanıcılarının (Yönetici, Veznedar vb.) varlığını kontrol ediyoruz
        result_user = await db.execute(select(models.User).limit(1))
        if not result_user.scalar_one_or_none():
            users_data = [
                {"user": "admin", "pass": "admin123", "role": models.UserRole.ADMIN, "doc_id": None},
                {"user": "vezne", "pass": "vezne123", "role": models.UserRole.CASHIER, "doc_id": None},
                {"user": "kayit", "pass": "kayit123", "role": models.UserRole.RECEPTION, "doc_id": None},
                {"user": "rezervasyon", "pass": "rezervasyon123", "role": models.UserRole.APPOINTMENT, "doc_id": None},
            ]
            
            # İlk doktoru bulup ona da bir kullanıcı hesabı açıyoruz
            doc_result = await db.execute(select(models.Doctor).limit(1))
            first_doctor = doc_result.scalar_one_or_none()
            if first_doctor:
                users_data.append({"user": first_doctor.tc_no, "pass": "D0kt0r_M3d", "role": models.UserRole.DOCTOR, "doc_id": first_doctor.id})

            # Tüm kullanıcıları veritabanına ekliyoruz ve şifrelerini de hashliyoruz
            for u in users_data:
                db_user = models.User(
                    username=u["user"],
                    hashed_password=auth.get_password_hash(u["pass"]),
                    role=u["role"],
                    doctor_id=u["doc_id"]
                )
                db.add(db_user)
                print(f"----- SEED HESAP: Kullanıcı: {u['user']} | Şifre: {u['pass']} -----")
            await db.commit()

# --- Yetkilendirme (Auth) İşlemleri ---
@app.post("/login", response_model=schemas.Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Kullanıcının (Yönetici, Doktor, Vezne vb.) sisteme giriş yapıp yetki tokenı aldığı yerdir."""
    result = await db.execute(select(models.User).where(models.User.username == form_data.username))
    user = result.scalar_one_or_none()
    
    # Şifre veya kullanıcı adı eşleşmezse hata fırlat
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre hatalı",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Başarılı girişte Token oluştur ve dön
    access_token_expires = datetime.timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": user.role.value}

# --- Yönetici (Admin) İşlemleri ---
@app.get("/admin/clinics", response_model=List[schemas.ClinicResponse], tags=["Admin"])
async def list_clinics(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Sistemdeki tüm klinikleri listeler."""
    return await crud.get_all_clinics(db=db)

@app.post("/admin/clinics", response_model=schemas.ClinicResponse, tags=["Admin"])
async def create_clinic(clinic: schemas.ClinicCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Sisteme yeni bir klinik/bölüm ekler."""
    return await crud.create_clinic(db=db, clinic=clinic)

@app.get("/admin/doctors", response_model=List[schemas.DoctorListResponse], tags=["Admin"])
async def list_doctors_admin(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Sistemdeki tüm doktorların listesini döndürür."""
    return await crud.get_all_doctors(db=db)

@app.get("/admin/users", response_model=List[schemas.UserResponse], tags=["Admin"])
async def list_users_admin(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Sistemdeki tüm kullanıcıların listesini döndürür."""
    return await crud.get_all_users(db=db)

@app.post("/admin/doctors", response_model=schemas.DoctorResponse, tags=["Admin"])
async def create_doctor(doctor: schemas.DoctorCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Yeni doktor ekler ve o doktora otomatik olarak sisteme girebilmesi için bir kullanıcı hesabı tanımlar."""
    return await crud.create_doctor(db=db, doctor=doctor)

# --- Kayıt ve Rezervasyon İşlemleri ---
@app.get("/reception/doctors", response_model=List[schemas.DoctorListResponse], tags=["Reception"])
async def get_all_doctors(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hasta randevusu oluştururken doktor listesini çekmek için kullanılır."""
    return await crud.get_all_doctors(db=db)

@app.post("/reception/patients", response_model=schemas.PatientResponse, tags=["Reception"])
async def create_patient(patient: schemas.PatientCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Sisteme daha önce gelmemiş yeni bir hastanın kaydını yapar."""
    return await crud.create_patient(db=db, patient=patient)

@app.get("/reception/availability", response_model=schemas.AvailabilityResponse, tags=["Reception"])
async def check_availability(doctor_id: int, date: datetime.date, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Belirli bir gün ve doktorda boş randevu saatlerini listeler."""
    return await crud.check_availability(db=db, doctor_id=doctor_id, date_req=date)

@app.post("/reception/appointments", response_model=schemas.AppointmentResponse, tags=["Reception"])
async def create_appointment(appointment: schemas.AppointmentCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastaya randevu verir. Eğer saat doluysa hata ve alternatif saatler döner."""
    return await crud.create_appointment(db=db, appointment=appointment)

@app.get("/reception/appointments/search", response_model=List[schemas.AppointmentSearchResponse], tags=["Reception"])
async def search_appointments(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """TC kimlik numarasıyla hastanın aktif ve iptal edilebilecek randevularını getirir."""
    return await crud.search_appointments_by_tc(db=db, tc_no=tc_no)

@app.put("/reception/appointments/{appointment_id}/cancel", response_model=schemas.AppointmentResponse, tags=["Reception"])
async def cancel_appointment(appointment_id: int, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Randevuyu iptal statüsüne çeker."""
    return await crud.cancel_appointment(db=db, appointment_id=appointment_id)

@app.put("/reception/appointments/{appointment_id}/reschedule", response_model=schemas.AppointmentResponse, tags=["Reception"])
async def reschedule_appointment(appointment_id: int, reschedule_data: schemas.AppointmentReschedule, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Randevu tarihini veya saatini günceller (Erteleme işlemi)."""
    return await crud.reschedule_appointment(db=db, appointment_id=appointment_id, reschedule_data=reschedule_data)

# --- Doktor (Klinik) İşlemleri ---
@app.get("/doctor/my-appointments", response_model=schemas.DoctorDailyResponse, tags=["Doctor"])
async def get_my_appointments(date: datetime.date = datetime.date.today(), db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Doktorun kendi paneline girdiğinde gördüğü kendi günlük hasta listesi."""
    if current_user.role != models.UserRole.DOCTOR or not current_user.doctor_id:
        raise HTTPException(status_code=403, detail="Bu endpoint sadece doktorlara özeldir.")
    return await crud.get_my_appointments(db=db, doctor_id=current_user.doctor_id, date_req=date)

@app.get("/doctor/appointments/{doctor_id}", response_model=List[schemas.AppointmentResponse], tags=["Doctor"])
async def get_doctor_appointments(doctor_id: int, date: datetime.date = datetime.date.today(), db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """(Gerektiğinde başka bir yetkili tarafından) belirli bir doktorun randevularına bakılmasını sağlar."""
    return await crud.get_doctor_appointments(db=db, doctor_id=doctor_id, date_req=date)

@app.get("/doctor/patients/{tc_no}", response_model=schemas.PatientHistoryResponse, tags=["Doctor"])
async def get_patient_history(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastanın daha önceki muayene kayıtlarını (Tanı, Tedavi) doktora sunar."""
    return await crud.get_patient_history(db=db, tc_no=tc_no)

@app.post("/doctor/examinations", response_model=schemas.ExaminationResponse, tags=["Doctor"])
async def create_examination(examination: schemas.ExaminationCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Muayene kaydını oluşturur, e-reçete yazar ve randevuyu 'Tamamlandı' olarak işaretler."""
    return await crud.create_examination(db=db, examination=examination)

@app.get("/doctor/report/{tc_no}", response_model=schemas.ReportResponse, tags=["Doctor"])
async def get_report(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastanın son muayenesine ait epikriz/reçete raporunu getirir."""
    return await crud.get_report(db=db, tc_no=tc_no)

@app.get("/doctor/referral/{tc_no}", response_model=schemas.ReferralResponse, tags=["Doctor"])
async def get_referral(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastanın son muayenesinde sevk verildiyse o sevk belgesini görüntüler."""
    return await crud.get_referral(db=db, tc_no=tc_no)

# --- Vezne (Tahsilat) İşlemleri ---
@app.get("/cashier/billing/{tc_no}", response_model=schemas.BillingResponse, tags=["Cashier"])
async def calculate_billing(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Muayenesi tamamlanan hastanın SGK/Özel sigorta simülasyonu ile ödenecek net ücretini hesaplar."""
    return await crud.calculate_billing(db=db, tc_no=tc_no)

@app.post("/cashier/payments", response_model=schemas.PaymentResponse, tags=["Cashier"])
async def process_payment(payment: schemas.PaymentCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hasta nakit veya kredi kartıyla ödeme yaptığında bunu sisteme kaydeder."""
    return await crud.process_payment(db=db, payment_data=payment)

@app.get("/cashier/transactions", response_model=List[schemas.TransactionResponse], tags=["Cashier"])
async def get_transactions(tc_no: str = None, status: str = None, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Veznedarın gün sonunda yaptığı tahsilatları ve bekleyen ödemeleri listeler."""
    return await crud.get_transactions(db=db, tc_no=tc_no, status_filter=status)
