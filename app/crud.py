from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, update, desc
from sqlalchemy.orm import selectinload
from app import models, schemas, auth
import datetime
import secrets
from fastapi import HTTPException

async def create_clinic(db: AsyncSession, clinic: schemas.ClinicCreate):
    """Klinik ekler"""
    db_clinic = models.Clinic(**clinic.model_dump())
    db.add(db_clinic)
    await db.commit()
    await db.refresh(db_clinic)
    return db_clinic

async def create_doctor(db: AsyncSession, doctor: schemas.DoctorCreate):
    """Doktor ekleyip ona bir kullanıcı hesabı oluşturur"""
    result = await db.execute(select(models.Clinic).where(models.Clinic.id == doctor.clinic_id))
    clinic = result.scalar_one_or_none()
    if not clinic:
        raise HTTPException(status_code=404, detail="Klinik bulunamadı")
    result_tc = await db.execute(select(models.Doctor).where(models.Doctor.tc_no == doctor.tc_no))
    if result_tc.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Bu TC Kimlik Numarası ile kayıtlı bir doktor zaten var.")
    db_doctor = models.Doctor(**doctor.model_dump())
    db.add(db_doctor)
    await db.commit()
    await db.refresh(db_doctor)
    random_password = secrets.token_hex(4)
    hashed_pwd = auth.get_password_hash(random_password)
    
    db_user = models.User(
        username=doctor.tc_no,
        hashed_password=hashed_pwd,
        role=models.UserRole.DOCTOR,
        doctor_id=db_doctor.id
    )
    db.add(db_user)
    await db.commit()
    db_doctor.generated_password = random_password

    return db_doctor

async def create_patient(db: AsyncSession, patient: schemas.PatientCreate):
    """Hasta ekler. Hasta zaten varsa hata verir."""
    result = await db.execute(select(models.Patient).where(models.Patient.tc_no == patient.tc_no))
    existing_patient = result.scalar_one_or_none()
    if existing_patient:
        raise HTTPException(status_code=400, detail="Bu TC Kimlik numarası ile kayıtlı bir hasta zaten var.")

    db_patient = models.Patient(**patient.model_dump())
    db.add(db_patient)
    await db.commit()
    await db.refresh(db_patient)
    return db_patient

async def get_patient_by_tc(db: AsyncSession, tc_no: str):
    """TC'ye göre hastayı arar"""
    result = await db.execute(select(models.Patient).where(models.Patient.tc_no == tc_no))
    return result.scalar_one_or_none()

async def check_availability(db: AsyncSession, doctor_id: int, date_req: datetime.date):
    """Doktorun seçilen gündeki boş saatlerini bulur"""
    result = await db.execute(select(models.Doctor).where(models.Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doktor bulunamadı")
    all_slots = []
    start_time = datetime.datetime.combine(date_req, datetime.time(9, 0))
    end_time = datetime.datetime.combine(date_req, datetime.time(17, 0))
    current = start_time
    while current < end_time:
        all_slots.append(current.time())
        current += datetime.timedelta(minutes=doctor.session_duration)
    stmt = select(models.Appointment).where(
        and_(
            models.Appointment.doctor_id == doctor_id,
            models.Appointment.appointment_date == date_req,
            models.Appointment.status != models.AppointmentStatus.IPTAL
        )
    )
    result = await db.execute(stmt)
    booked_appointments = result.scalars().all()
    booked_times = [appt.appointment_time for appt in booked_appointments]
    available_slots = [t for t in all_slots if t not in booked_times]

    return schemas.AvailabilityResponse(doctor_id=doctor_id, date=date_req, available_times=available_slots)

async def create_appointment(db: AsyncSession, appointment: schemas.AppointmentCreate):
    """Randevu verir. Doluysa alternatif saat/tarih önerir"""
    result = await db.execute(select(models.Patient).where(models.Patient.tc_no == appointment.patient_tc))
    patient = result.scalar_one_or_none()
    if not patient:
         raise HTTPException(status_code=404, detail="Girdiğiniz TC Kimlik numarasına ait hasta bulunamadı. Lütfen önce hasta kaydını gerçekleştirin.")
    if not (datetime.time(9, 0) <= appointment.appointment_time <= datetime.time(16, 30)):
        raise HTTPException(status_code=400, detail="Randevu saatleri 09:00 ile 16:30 arasında olmalıdır.")

    # 1. Geçmiş tarih kontrolü
    today = datetime.date.today()
    if appointment.appointment_date < today:
        raise HTTPException(status_code=400, detail="Geçmiş bir tarihe randevu alınamaz.")

    # 2. Hafta içi kontrolü
    if appointment.appointment_date.weekday() >= 5:
        raise HTTPException(status_code=400, detail="Poliklinik sadece hafta içi günlerde (Pazartesi-Cuma) hizmet vermektedir.")

    # 3. Geçmiş saat kontrolü (Bugün için randevu alınıyorsa)
    if appointment.appointment_date == today:
        now_time = datetime.datetime.now().time()
        if now_time > appointment.appointment_time:
            raise HTTPException(status_code=400, detail="Bugün için seçilen randevu saati geçmiştir.")

    # 4. Aynı gün, aynı doktordan birden fazla aktif randevu alınamaması kontrolü
    stmt_check = select(models.Appointment).where(
        and_(
            models.Appointment.patient_id == patient.id,
            models.Appointment.doctor_id == appointment.doctor_id,
            models.Appointment.appointment_date == appointment.appointment_date,
            models.Appointment.status == models.AppointmentStatus.AKTIF
        )
    )
    res_check = await db.execute(stmt_check)
    if res_check.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Hastanın bu doktordan aynı gün için zaten aktif bir randevusu bulunmaktadır.")

    stmt = select(models.Appointment).where(
        and_(
            models.Appointment.doctor_id == appointment.doctor_id,
            models.Appointment.appointment_date == appointment.appointment_date,
            models.Appointment.appointment_time == appointment.appointment_time,
            models.Appointment.status != models.AppointmentStatus.IPTAL
        )
    )
    result = await db.execute(stmt)
    existing_appt = result.scalar_one_or_none()
    
    if existing_appt:
        avail = await check_availability(db, appointment.doctor_id, appointment.appointment_date)
        alt_dates = []
        search_date = appointment.appointment_date + datetime.timedelta(days=1)
        for _ in range(7):  # sonraki 7 güne bak
            if len(alt_dates) >= 3:
                break
            if search_date.weekday() >= 5:  # Hafta sonunu geç
                search_date += datetime.timedelta(days=1)
                continue
            day_avail = await check_availability(db, appointment.doctor_id, search_date)
            if day_avail.available_times:
                alt_dates.append(search_date.strftime("%Y-%m-%d"))
            search_date += datetime.timedelta(days=1)
        raise HTTPException(
            status_code=409, 
            detail={
                "message": "Seçilen saatte doktorun başka bir randevusu bulunmaktadır.",
                "alternatives": [t.strftime("%H:%M") for t in avail.available_times[:3]],
                "alternative_dates": alt_dates
            }
        )

    db_appointment = models.Appointment(
        patient_id=patient.id,
        doctor_id=appointment.doctor_id,
        appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time
    )
    db.add(db_appointment)
    await db.commit()
    await db.refresh(db_appointment)
    return db_appointment

async def get_all_doctors(db: AsyncSession):
    """Tüm doktorları kliniğiyle beraber getirir"""
    stmt = select(models.Doctor).options(selectinload(models.Doctor.clinic))
    result = await db.execute(stmt)
    doctors = result.scalars().all()
    
    return [
        schemas.DoctorListResponse(
            id=d.id,
            first_name=d.first_name,
            last_name=d.last_name,
            clinic_name=d.clinic.name if d.clinic else "Bilinmiyor",
            tc_no=d.tc_no,
            phone_number=d.phone_number,
            birth_date=d.birth_date,
            clinic_id=d.clinic_id
        )
        for d in doctors
    ]



async def get_doctor_appointments(db: AsyncSession, doctor_id: int, date_req: datetime.date):
    """Doktorun bir gündeki randevularını getirir"""
    stmt = select(models.Appointment).where(
        and_(
            models.Appointment.doctor_id == doctor_id,
            models.Appointment.appointment_date == date_req,
            models.Appointment.status == models.AppointmentStatus.AKTIF
        )
    ).order_by(models.Appointment.appointment_time)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_patient_history(db: AsyncSession, tc_no: str):
    """Hastanın geçmiş muayenelerini sondan başa getirir"""
    result = await db.execute(select(models.Patient).where(models.Patient.tc_no == tc_no))
    patient = result.scalar_one_or_none()
    if not patient:
         raise HTTPException(status_code=404, detail="Hasta bulunamadı")
    stmt = select(models.Examination).join(models.Appointment).where(
        models.Appointment.patient_id == patient.id
    ).order_by(models.Examination.id.desc())
    result = await db.execute(stmt)
    examinations = result.scalars().all()
    
    return schemas.PatientHistoryResponse(patient=patient, examinations=examinations)

async def create_examination(db: AsyncSession, examination: schemas.ExaminationCreate, doctor_id: int = None):
    """Muayeneyi kaydeder ve randevuyu tamamlandı yapar"""
    patient_result = await db.execute(select(models.Patient).where(models.Patient.tc_no == examination.patient_tc))
    patient = patient_result.scalar_one_or_none()
    if not patient:
         raise HTTPException(status_code=404, detail="Bu TC numarasına ait hasta bulunamadı.")
    
    # Aktif randevuları sorgula. Eğer muayene yapan doktorun ID'si varsa, sadece o doktorun randevularına bak.
    stmt_filters = [
        models.Appointment.patient_id == patient.id,
        models.Appointment.status == models.AppointmentStatus.AKTIF
    ]
    if doctor_id is not None:
        stmt_filters.append(models.Appointment.doctor_id == doctor_id)

    stmt = select(models.Appointment).where(and_(*stmt_filters))
    result = await db.execute(stmt)
    active_appointments = result.scalars().all()
    
    if not active_appointments:
        if doctor_id is not None:
            raise HTTPException(status_code=404, detail="Bu hastanın bu doktorda aktif bir randevusu bulunamadı.")
        else:
            raise HTTPException(status_code=404, detail="Bu hastanın aktif bir randevusu bulunamadı.")
            
    if len(active_appointments) > 1:
        raise HTTPException(status_code=400, detail="Hastanın birden fazla aktif randevusu var. Lütfen manuel kontrol edin.")
        
    appointment = active_appointments[0]
    db_examination = models.Examination(
        appointment_id=appointment.id,
        diagnosis=examination.diagnosis,
        treatment=examination.treatment,
        prescription=examination.prescription,
        medical_report=examination.medical_report,
        is_referred=examination.is_referred
    )
    db.add(db_examination)
    appointment.status = models.AppointmentStatus.TAMAMLANDI

    await db.commit()
    await db.refresh(db_examination)
    return db_examination

def determine_insurance(tc_no: str, birth_date: datetime.date) -> dict:
    """Hastanın yaşına ve TC'sine göre sigorta indirimi hesaplar"""
    today = datetime.date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    
    if age >= 65:
        return {"type": "Emekli", "coverage": 90}
    if age < 18:
        return {"type": "SGK Yakını", "coverage": 80}
        
    try:
        mod_val = int(tc_no) % 4
    except ValueError:
        mod_val = -1
        
    if mod_val == 0:
        return {"type": "SGK", "coverage": 80}
    elif mod_val == 1:
        return {"type": "Özel Sigorta", "coverage": 50}
    elif mod_val == 2:
        return {"type": "Tamamlayıcı Sigorta", "coverage": 100}
    else:
        return {"type": "Sigortasız", "coverage": 0}

async def calculate_billing(db: AsyncSession, tc_no: str):
    """Hastanın ödeyeceği borcu sigortaya göre hesaplar"""
    stmt = select(models.Examination, models.Patient).join(
        models.Appointment, models.Appointment.id == models.Examination.appointment_id
    ).join(
        models.Patient, models.Patient.id == models.Appointment.patient_id
    ).where(models.Patient.tc_no == tc_no).order_by(models.Examination.id.desc())

    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Bu TC numarasına ait muayene bulunamadı")

    examination, patient = row
    examination_id = examination.id
    pay_result = await db.execute(select(models.Payment).where(models.Payment.examination_id == examination_id))
    existing_payment = pay_result.scalar_one_or_none()
    base_amount = 1000.0

    insurance_info = determine_insurance(patient.tc_no, patient.birth_date)

    if existing_payment:
        return schemas.BillingResponse(
            examination_id=examination_id,
            patient_tc=patient.tc_no,
            insurance_type=insurance_info["type"],
            base_amount=existing_payment.base_amount,
            discount_percentage=int((existing_payment.discount_amount / existing_payment.base_amount) * 100) if existing_payment.base_amount else 0,
            discount_amount=existing_payment.discount_amount,
            final_amount=existing_payment.final_amount
        )
    discount_rate = insurance_info["coverage"] / 100.0
    discount_amount = base_amount * discount_rate
    final_amount = base_amount - discount_amount
    db_payment = models.Payment(
        examination_id=examination_id,
        base_amount=base_amount,
        discount_amount=discount_amount,
        final_amount=final_amount,
        payment_status=models.PaymentStatus.BEKLIYOR
    )
    db.add(db_payment)
    await db.commit()
    await db.refresh(db_payment)

    return schemas.BillingResponse(
        examination_id=examination_id,
        patient_tc=patient.tc_no,
        insurance_type=insurance_info["type"],
        base_amount=base_amount,
        discount_percentage=insurance_info["coverage"],
        discount_amount=discount_amount,
        final_amount=final_amount
    )

async def process_payment(db: AsyncSession, payment_data: schemas.PaymentCreate):
    """Ödemeyi sisteme kaydeder (nakit/kart)"""
    stmt = select(models.Examination).join(
        models.Appointment
    ).join(
        models.Patient
    ).where(models.Patient.tc_no == payment_data.patient_tc).order_by(models.Examination.id.desc())
    
    result = await db.execute(stmt)
    examination = result.scalars().first()
    
    if not examination:
        raise HTTPException(status_code=404, detail="Bu TC numarasına ait muayene bulunamadı.")
        
    result = await db.execute(select(models.Payment).where(models.Payment.examination_id == examination.id))
    payment = result.scalar_one_or_none()

    if not payment:
         raise HTTPException(status_code=404, detail="Bekleyen ödeme bulunamadı. Lütfen önce fatura hesaplaması yapın.")
    
    if payment.payment_status == models.PaymentStatus.ODENDI:
         raise HTTPException(status_code=400, detail="Bu fatura zaten ödenmiş.")

    payment.payment_method = payment_data.payment_method
    payment.payment_status = models.PaymentStatus.ODENDI

    await db.commit()
    await db.refresh(payment)
    return payment
async def create_user(db: AsyncSession, user: schemas.UserCreate):
    result = await db.execute(select(models.User).where(models.User.username == user.username))
    if result.scalar_one_or_none():
        raise ValueError("Bu kullanıcı adı zaten alınmış.")
    
    hashed_pwd = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        hashed_password=hashed_pwd,
        role=user.role,
        doctor_id=user.doctor_id
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def cancel_appointment(db: AsyncSession, appointment_id: int):
    """Randevuyu iptal eder"""
    result = await db.execute(select(models.Appointment).where(models.Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Randevu bulunamadı.")
    if appointment.status == models.AppointmentStatus.IPTAL:
        raise HTTPException(status_code=400, detail="Bu randevu zaten iptal edilmiş.")
    if appointment.status == models.AppointmentStatus.TAMAMLANDI:
        raise HTTPException(status_code=400, detail="Tamamlanmış bir randevu iptal edilemez.")
    
    appointment.status = models.AppointmentStatus.IPTAL
    await db.commit()
    await db.refresh(appointment)
    return appointment

async def reschedule_appointment(db: AsyncSession, appointment_id: int, reschedule_data: schemas.AppointmentReschedule):
    """Randevuyu erteler veya saatini değiştirir"""
    result = await db.execute(select(models.Appointment).where(models.Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Randevu bulunamadı.")
    if appointment.status != models.AppointmentStatus.AKTIF:
        raise HTTPException(status_code=400, detail="Sadece aktif randevular ertelenebilir.")
    
    if not (datetime.time(9, 0) <= reschedule_data.new_time <= datetime.time(16, 30)):
        raise HTTPException(status_code=400, detail="Randevu saatleri 09:00 ile 16:30 arasında olmalıdır.")

    # 1. Geçmiş tarih kontrolü
    today = datetime.date.today()
    if reschedule_data.new_date < today:
        raise HTTPException(status_code=400, detail="Geçmiş bir tarihe randevu ertelenemez.")

    # 2. Hafta içi kontrolü
    if reschedule_data.new_date.weekday() >= 5:
        raise HTTPException(status_code=400, detail="Poliklinik sadece hafta içi günlerde (Pazartesi-Cuma) hizmet vermektedir.")

    # 3. Geçmiş saat kontrolü (Bugün için randevu erteleniyorsa)
    if reschedule_data.new_date == today:
        now_time = datetime.datetime.now().time()
        if now_time > reschedule_data.new_time:
            raise HTTPException(status_code=400, detail="Bugün için seçilen erteleme saati geçmiştir.")

    # 4. Aynı gün, aynı doktordan birden fazla aktif randevu alınamaması kontrolü (kendi randevusu hariç)
    stmt_check = select(models.Appointment).where(
        and_(
            models.Appointment.patient_id == appointment.patient_id,
            models.Appointment.doctor_id == appointment.doctor_id,
            models.Appointment.appointment_date == reschedule_data.new_date,
            models.Appointment.status == models.AppointmentStatus.AKTIF,
            models.Appointment.id != appointment.id
        )
    )
    res_check = await db.execute(stmt_check)
    if res_check.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Hastanın bu doktordan aynı gün için zaten aktif bir başka randevusu bulunmaktadır.")

    stmt = select(models.Appointment).where(
        and_(
            models.Appointment.doctor_id == appointment.doctor_id,
            models.Appointment.appointment_date == reschedule_data.new_date,
            models.Appointment.appointment_time == reschedule_data.new_time,
            models.Appointment.status != models.AppointmentStatus.IPTAL
        )
    )
    conflict_result = await db.execute(stmt)
    if conflict_result.scalar_one_or_none():
        avail = await check_availability(db, appointment.doctor_id, reschedule_data.new_date)
        alt_dates = []
        search_date = reschedule_data.new_date + datetime.timedelta(days=1)
        for _ in range(7):  # sonraki 7 güne bak
            if len(alt_dates) >= 3:
                break
            if search_date.weekday() >= 5:  # Hafta sonunu geç
                search_date += datetime.timedelta(days=1)
                continue
            day_avail = await check_availability(db, appointment.doctor_id, search_date)
            if day_avail.available_times:
                alt_dates.append(search_date.strftime("%Y-%m-%d"))
            search_date += datetime.timedelta(days=1)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Yeni seçilen saatte doktorun başka bir randevusu var.",
                "alternatives": [t.strftime("%H:%M") for t in avail.available_times[:5]],
                "alternative_dates": alt_dates
            }
        )
    appointment.appointment_date = reschedule_data.new_date
    appointment.appointment_time = reschedule_data.new_time
    await db.commit()
    await db.refresh(appointment)
    return appointment

async def search_appointments_by_tc(db: AsyncSession, tc_no: str):
    """Hastanın iptal edilmemiş randevularını TC ile arar"""
    patient_result = await db.execute(select(models.Patient).where(models.Patient.tc_no == tc_no))
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Bu TC numarasına ait hasta bulunamadı.")
    
    stmt = select(models.Appointment).options(
        selectinload(models.Appointment.doctor).selectinload(models.Doctor.clinic)
    ).where(
        models.Appointment.patient_id == patient.id
    ).order_by(models.Appointment.appointment_date.desc(), models.Appointment.appointment_time.desc())
    
    result = await db.execute(stmt)
    appointments = result.scalars().all()
    
    return [
        schemas.AppointmentSearchResponse(
            id=a.id,
            patient_tc=patient.tc_no,
            patient_name=f"{patient.first_name} {patient.last_name}",
            doctor_name=f"{a.doctor.first_name} {a.doctor.last_name}",
            clinic_name=a.doctor.clinic.name if a.doctor.clinic else "Bilinmiyor",
            appointment_date=a.appointment_date,
            appointment_time=a.appointment_time,
            status=a.status
        )
        for a in appointments
    ]

async def get_my_appointments(db: AsyncSession, doctor_id: int, date_req: datetime.date):
    """Doktorun o günkü hasta listesini getirir"""
    doc_result = await db.execute(
        select(models.Doctor).options(selectinload(models.Doctor.clinic)).where(models.Doctor.id == doctor_id)
    )
    doctor = doc_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doktor bulunamadı.")
    
    stmt = select(models.Appointment).options(
        selectinload(models.Appointment.patient)
    ).where(
        and_(
            models.Appointment.doctor_id == doctor_id,
            models.Appointment.appointment_date == date_req,
        )
    ).order_by(models.Appointment.appointment_time)
    
    result = await db.execute(stmt)
    appointments = result.scalars().all()
    
    return schemas.DoctorDailyResponse(
        doctor_name=f"{doctor.first_name} {doctor.last_name}",
        date=date_req,
        appointments=[
            schemas.DoctorAppointmentDetail(
                appointment_id=a.id,
                patient_tc=a.patient.tc_no,
                patient_name=f"{a.patient.first_name} {a.patient.last_name}",
                patient_phone=a.patient.phone,
                appointment_time=a.appointment_time,
                status=a.status
            )
            for a in appointments
        ]
    )


async def get_all_clinics(db: AsyncSession):
    """Bütün klinikleri getirir"""
    result = await db.execute(select(models.Clinic))
    return result.scalars().all()

async def get_report(db: AsyncSession, tc_no: str):
    """Hastanın son muayene raporunu getirir"""
    stmt = select(
        models.Examination, models.Appointment, models.Patient, models.Doctor, models.Clinic
    ).join(
        models.Appointment, models.Appointment.id == models.Examination.appointment_id
    ).join(
        models.Patient, models.Patient.id == models.Appointment.patient_id
    ).join(
        models.Doctor, models.Doctor.id == models.Appointment.doctor_id
    ).join(
        models.Clinic, models.Clinic.id == models.Doctor.clinic_id
    ).where(models.Patient.tc_no == tc_no).order_by(desc(models.Examination.id))
    
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Muayene bulunamadı.")
    
    exam, appt, patient, doctor, clinic = row
    
    return schemas.ReportResponse(
        examination_id=exam.id,
        patient_tc=patient.tc_no,
        patient_name=f"{patient.first_name} {patient.last_name}",
        patient_birth_date=patient.birth_date,
        doctor_name=f"{doctor.first_name} {doctor.last_name}",
        clinic_name=clinic.name,
        examination_date=appt.appointment_date,
        diagnosis=exam.diagnosis,
        treatment=exam.treatment,
        prescription=exam.prescription,
        medical_report=exam.medical_report,
        is_referred=exam.is_referred
    )

async def get_referral(db: AsyncSession, tc_no: str):
    """Hastanın son muayenesinde sevk varsa sevk belgesi hazırlar"""
    stmt = select(
        models.Examination, models.Appointment, models.Patient, models.Doctor, models.Clinic
    ).join(
        models.Appointment, models.Appointment.id == models.Examination.appointment_id
    ).join(
        models.Patient, models.Patient.id == models.Appointment.patient_id
    ).join(
        models.Doctor, models.Doctor.id == models.Appointment.doctor_id
    ).join(
        models.Clinic, models.Clinic.id == models.Doctor.clinic_id
    ).where(models.Patient.tc_no == tc_no).order_by(desc(models.Examination.id))
    
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Muayene bulunamadı.")
    
    exam, appt, patient, doctor, clinic = row
    
    if not exam.is_referred:
        raise HTTPException(status_code=400, detail="Bu muayene için sevk kaydı bulunmuyor.")
    
    return schemas.ReferralResponse(
        examination_id=exam.id,
        patient_tc=patient.tc_no,
        patient_name=f"{patient.first_name} {patient.last_name}",
        patient_birth_date=patient.birth_date,
        source_doctor=f"{doctor.first_name} {doctor.last_name}",
        source_clinic=clinic.name,
        referral_date=appt.appointment_date,
        diagnosis=exam.diagnosis,
        notes=exam.treatment
    )

async def get_transactions(db: AsyncSession, tc_no: str = None, status_filter: str = None):
    """Geçmiş tüm fatura ve ödemeleri listeler"""
    stmt = select(
        models.Payment, models.Examination, models.Appointment, models.Patient
    ).join(
        models.Examination, models.Examination.id == models.Payment.examination_id
    ).join(
        models.Appointment, models.Appointment.id == models.Examination.appointment_id
    ).join(
        models.Patient, models.Patient.id == models.Appointment.patient_id
    )
    
    if tc_no:
        stmt = stmt.where(models.Patient.tc_no == tc_no)
    if status_filter:
        stmt = stmt.where(models.Payment.payment_status == status_filter)
    
    stmt = stmt.order_by(models.Payment.id.desc())
    
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        schemas.TransactionResponse(
            payment_id=payment.id,
            examination_id=payment.examination_id,
            patient_tc=patient.tc_no,
            patient_name=f"{patient.first_name} {patient.last_name}",
            base_amount=payment.base_amount,
            discount_amount=payment.discount_amount,
            final_amount=payment.final_amount,
            payment_method=payment.payment_method.value if payment.payment_method else None,
            payment_status=payment.payment_status.value,
            examination_date=appt.appointment_date
        )
        for payment, exam, appt, patient in rows
    ]

