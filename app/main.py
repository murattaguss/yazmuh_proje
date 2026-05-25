"""
FastAPI ana çalıştırma dosyası.
Bütün endpoint'ler ve başlangıç ayarları burada toplanıyor.
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

# FastAPI nesnesini oluştur
app = FastAPI(
    title="Şifa Polikliniği",
    description="Hasta kayıt, rezervasyon, doktor muayene ve vezne/ödeme modüllerini içeren API.",
    version="1.0.0"
)

# Frontend klasörünü oluştur
os.makedirs("frontend", exist_ok=True)
# Static dosyalar için yolu tanımla
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Ana sayfaya girince index.html'i açar"""
    return FileResponse("frontend/index.html")

@app.on_event("startup")
async def startup():
    """
    Uygulama açılırken tabloları ve örnek verileri yükler.
    """
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        
    from app.database import AsyncSessionLocal
    from sqlalchemy.future import select
    
    async with AsyncSessionLocal() as db:
        # Hiç klinik yoksa örnek klinikler ekle
        result = await db.execute(select(models.Clinic).limit(1))
        if not result.scalar_one_or_none():
            clinics = ["Göz", "Üroloji", "Ortopedi", "Psikiyatri"]
            db_clinics = []
            for c_name in clinics:
                new_clinic = models.Clinic(name=c_name)
                db.add(new_clinic)
                db_clinics.append(new_clinic)
            await db.commit()
            
            # Eklenen kliniklere birer doktor ata
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
            
        # Varsayılan kullanıcıları (admin, vezne vb.) ekle
        result_user = await db.execute(select(models.User).limit(1))
        if not result_user.scalar_one_or_none():
            users_data = [
                {"user": "admin", "pass": "admin123", "role": models.UserRole.ADMIN, "doc_id": None},
                {"user": "vezne", "pass": "vezne123", "role": models.UserRole.CASHIER, "doc_id": None},
                {"user": "kayit", "pass": "kayit123", "role": models.UserRole.RECEPTION, "doc_id": None},
                {"user": "rezervasyon", "pass": "rezervasyon123", "role": models.UserRole.APPOINTMENT, "doc_id": None},
            ]
            
            # İlk doktora da giriş hesabı aç
            doc_result = await db.execute(select(models.Doctor).limit(1))
            first_doctor = doc_result.scalar_one_or_none()
            if first_doctor:
                users_data.append({"user": first_doctor.tc_no, "pass": "D0kt0r_M3d", "role": models.UserRole.DOCTOR, "doc_id": first_doctor.id})

            # Kullanıcıları db'ye kaydet ve şifrelerini hashle
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

# Yetkilendirme (Auth) İşlemleri
@app.post("/login", response_model=schemas.Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Kullanıcının giriş yapıp token aldığı yer"""
    result = await db.execute(select(models.User).where(models.User.username == form_data.username))
    user = result.scalar_one_or_none()
    
    # Şifre veya kullanıcı adı yanlışsa hata ver
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre hatalı",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Giriş başarılıysa token üret
    access_token_expires = datetime.timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": user.role.value}

# Yönetici (Admin) İşlemleri
@app.get("/admin/clinics", response_model=List[schemas.ClinicResponse], tags=["Admin"])
async def list_clinics(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Bütün klinikleri listeler"""
    return await crud.get_all_clinics(db=db)

@app.post("/admin/clinics", response_model=schemas.ClinicResponse, tags=["Admin"])
async def create_clinic(clinic: schemas.ClinicCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Yeni klinik ekler"""
    return await crud.create_clinic(db=db, clinic=clinic)

@app.get("/admin/doctors", response_model=List[schemas.DoctorListResponse], tags=["Admin"])
async def list_doctors_admin(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Bütün doktorları listeler"""
    return await crud.get_all_doctors(db=db)



@app.post("/admin/doctors", response_model=schemas.DoctorResponse, tags=["Admin"])
async def create_doctor(doctor: schemas.DoctorCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Doktor ekler ve ona giriş hesabı açar"""
    return await crud.create_doctor(db=db, doctor=doctor)

# Kayıt ve Rezervasyon İşlemleri
@app.get("/reception/doctors", response_model=List[schemas.DoctorListResponse], tags=["Reception"])
async def get_all_doctors(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Randevu alırken doktor seçebilmek için doktor listesini getirir"""
    return await crud.get_all_doctors(db=db)

@app.post("/reception/patients", response_model=schemas.PatientResponse, tags=["Reception"])
async def create_patient(patient: schemas.PatientCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Yeni hasta kaydeder"""
    return await crud.create_patient(db=db, patient=patient)

@app.get("/reception/availability", response_model=schemas.AvailabilityResponse, tags=["Reception"])
async def check_availability(doctor_id: int, date: datetime.date, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Doktorun boş saatlerini kontrol eder"""
    return await crud.check_availability(db=db, doctor_id=doctor_id, date_req=date)

@app.post("/reception/appointments", response_model=schemas.AppointmentResponse, tags=["Reception"])
async def create_appointment(appointment: schemas.AppointmentCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Yeni randevu oluşturur. Doluysa alternatifleri gösterir"""
    return await crud.create_appointment(db=db, appointment=appointment)

@app.get("/reception/appointments/search", response_model=List[schemas.AppointmentSearchResponse], tags=["Reception"])
async def search_appointments(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastanın randevularını TC ile arar"""
    return await crud.search_appointments_by_tc(db=db, tc_no=tc_no)

@app.put("/reception/appointments/{appointment_id}/cancel", response_model=schemas.AppointmentResponse, tags=["Reception"])
async def cancel_appointment(appointment_id: int, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Randevuyu iptal eder"""
    return await crud.cancel_appointment(db=db, appointment_id=appointment_id)

@app.put("/reception/appointments/{appointment_id}/reschedule", response_model=schemas.AppointmentResponse, tags=["Reception"])
async def reschedule_appointment(appointment_id: int, reschedule_data: schemas.AppointmentReschedule, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Randevu tarihini veya saatini değiştirir"""
    return await crud.reschedule_appointment(db=db, appointment_id=appointment_id, reschedule_data=reschedule_data)

# Doktor İşlemleri
@app.get("/doctor/my-appointments", response_model=schemas.DoctorDailyResponse, tags=["Doctor"])
async def get_my_appointments(date: datetime.date = datetime.date.today(), db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Doktorun kendi günlük hasta listesi"""
    if current_user.role != models.UserRole.DOCTOR or not current_user.doctor_id:
        raise HTTPException(status_code=403, detail="Bu endpoint sadece doktorlara özeldir.")
    return await crud.get_my_appointments(db=db, doctor_id=current_user.doctor_id, date_req=date)

@app.get("/doctor/appointments/{doctor_id}", response_model=List[schemas.AppointmentResponse], tags=["Doctor"])
async def get_doctor_appointments(doctor_id: int, date: datetime.date = datetime.date.today(), db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Bir doktorun randevularını listeler"""
    return await crud.get_doctor_appointments(db=db, doctor_id=doctor_id, date_req=date)

@app.get("/doctor/patients/{tc_no}", response_model=schemas.PatientHistoryResponse, tags=["Doctor"])
async def get_patient_history(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastanın geçmiş muayene kayıtlarını getirir"""
    return await crud.get_patient_history(db=db, tc_no=tc_no)

@app.post("/doctor/examinations", response_model=schemas.ExaminationResponse, tags=["Doctor"])
async def create_examination(examination: schemas.ExaminationCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Muayene kaydını tamamlar"""
    return await crud.create_examination(db=db, examination=examination, doctor_id=current_user.doctor_id)

@app.get("/doctor/report/{tc_no}", response_model=schemas.ReportResponse, tags=["Doctor"])
async def get_report(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastanın son muayene raporunu getirir"""
    return await crud.get_report(db=db, tc_no=tc_no)

@app.get("/doctor/referral/{tc_no}", response_model=schemas.ReferralResponse, tags=["Doctor"])
async def get_referral(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Hastanın son sevk belgesini getirir"""
    return await crud.get_referral(db=db, tc_no=tc_no)

# Vezne (Ödeme) İşlemleri
@app.get("/cashier/billing/{tc_no}", response_model=schemas.BillingResponse, tags=["Cashier"])
async def calculate_billing(tc_no: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Fatura tutarını hesaplar"""
    return await crud.calculate_billing(db=db, tc_no=tc_no)

@app.post("/cashier/payments", response_model=schemas.PaymentResponse, tags=["Cashier"])
async def process_payment(payment: schemas.PaymentCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Ödemeyi alır ve kaydeder"""
    return await crud.process_payment(db=db, payment_data=payment)

@app.get("/cashier/transactions", response_model=List[schemas.TransactionResponse], tags=["Cashier"])
async def get_transactions(tc_no: str = None, status: str = None, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Bütün ödemeleri ve işlemlerini listeler"""
    return await crud.get_transactions(db=db, tc_no=tc_no, status_filter=status)
