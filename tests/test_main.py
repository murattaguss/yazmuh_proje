import unittest
import asyncio
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from fastapi import HTTPException

from app import models, schemas, crud, auth
from app.database import Base
from app.config import settings

def get_next_weekday(start_date=None):
    if start_date is None:
        start_date = datetime.date.today()
    next_day = start_date + datetime.timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += datetime.timedelta(days=1)
    return next_day

class ClinicSystemTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # 1. SQLite kontrolü
        # SQLite varsa hafızada çalıştır, yoksa Postgres kullanıp geri al
        self.use_sqlite = True
        try:
            import aiosqlite
            self.db_url = "sqlite+aiosqlite:///:memory:"
        except ImportError:
            # sqlite kütüphanesi yoksa normal db kullanıp geri alıcaz
            self.db_url = settings.DATABASE_URL
            self.use_sqlite = False
            
        self.engine = create_async_engine(self.db_url, echo=False)
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # 2. Tabloları oluştur
        if self.use_sqlite:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
        # 3. Bağlantıyı başlat
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.session = AsyncSession(bind=self.connection, expire_on_commit=False)
        
        # 4. Test için örnek verileri yükle
        if self.use_sqlite:
            # Örnek Klinik
            self.clinic = models.Clinic(id=1, name="Göz", is_active=True)
            self.session.add(self.clinic)
            await self.session.commit()
            
            # Örnek Doktor
            self.doctor = models.Doctor(
                id=1,
                first_name="Hakan",
                last_name="Bulut",
                tc_no="22222222222",
                birth_date=datetime.date(1985, 5, 20),
                phone_number="5552222222",
                clinic_id=1,
                session_duration=30
            )
            self.session.add(self.doctor)
            await self.session.commit()
            
            # Örnek Kullanıcı
            self.user = models.User(
                id=1,
                username="kayit",
                hashed_password=auth.get_password_hash("kayit123"),
                role=models.UserRole.RECEPTION
            )
            self.session.add(self.user)
            await self.session.commit()

    async def asyncTearDown(self):
        # Test bitince veritabanını temizle
        await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    # TEST 1: Hasta kaydetme testi
    async def test_create_patient(self):
        patient_data = schemas.PatientCreate(
            tc_no="12345678999",
            first_name="Murat",
            last_name="Tagus",
            phone="5551234567",
            birth_date=datetime.date(1995, 10, 15),
            gender="Erkek",
            height=180.0,
            weight=75.0,
            blood_type="A+"
        )
        
        # Normal kayıt
        db_patient = await crud.create_patient(self.session, patient_data)
        self.assertIsNotNone(db_patient.id)
        self.assertEqual(db_patient.tc_no, "12345678999")
        
        # Aynı TC ile tekrar kayıt (Hata vermeli)
        with self.assertRaises(HTTPException) as context:
            await crud.create_patient(self.session, patient_data)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("zaten var", context.exception.detail)

    # TEST 2: Randevu alma testi
    async def test_create_appointment_success(self):
        # Önce hasta ekle
        patient = models.Patient(
            tc_no="98765432101",
            first_name="Deniz",
            last_name="Yılmaz",
            birth_date=datetime.date(1990, 1, 1)
        )
        self.session.add(patient)
        await self.session.commit()
        
        appt_data = schemas.AppointmentCreate(
            patient_tc="98765432101",
            clinic_id=1,
            doctor_id=1,
            appointment_date=get_next_weekday(),
            appointment_time=datetime.time(10, 0)
        )
        
        db_appt = await crud.create_appointment(self.session, appt_data)
        self.assertIsNotNone(db_appt.id)
        self.assertEqual(db_appt.patient_id, patient.id)
        self.assertEqual(db_appt.status, models.AppointmentStatus.AKTIF)

    # TEST 3: Randevu çakışması testi
    async def test_create_appointment_conflict(self):
        # Hastaları ekle
        p1 = models.Patient(tc_no="11111111112", first_name="Ali", last_name="Can", birth_date=datetime.date(1990, 1, 1))
        p2 = models.Patient(tc_no="11111111113", first_name="Can", last_name="Tekin", birth_date=datetime.date(1990, 1, 1))
        self.session.add_all([p1, p2])
        await self.session.commit()
        
        date = get_next_weekday()
            
        time = datetime.time(11, 0)
        
        # 1. İlk randevuyu al
        appt_data1 = schemas.AppointmentCreate(patient_tc=p1.tc_no, clinic_id=1, doctor_id=1, appointment_date=date, appointment_time=time)
        await crud.create_appointment(self.session, appt_data1)
        
        # 2. Aynı saate randevu almayı dene (Çakışma kontrolü)
        appt_data2 = schemas.AppointmentCreate(patient_tc=p2.tc_no, clinic_id=1, doctor_id=1, appointment_date=date, appointment_time=time)
        with self.assertRaises(HTTPException) as context:
            await crud.create_appointment(self.session, appt_data2)
            
        self.assertEqual(context.exception.status_code, 409)
        detail = context.exception.detail
        self.assertIn("message", detail)
        self.assertIn("alternatives", detail)
        self.assertIn("alternative_dates", detail) # Alternatif tarihler var mı diye bak
        self.assertTrue(len(detail["alternative_dates"]) > 0)

    # TEST 4: Çalışma saatleri dışı randevu testi
    async def test_create_appointment_invalid_time(self):
        p = models.Patient(tc_no="11111111114", first_name="Aysu", last_name="Gül", birth_date=datetime.date(1992, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        # Çalışma saati dışı (23:00)
        appt_data = schemas.AppointmentCreate(
            patient_tc=p.tc_no,
            clinic_id=1,
            doctor_id=1,
            appointment_date=get_next_weekday(),
            appointment_time=datetime.time(23, 0)
        )
        
        with self.assertRaises(HTTPException) as context:
            await crud.create_appointment(self.session, appt_data)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("09:00 ile 16:30 arasında", context.exception.detail)

    # TEST 5: Doktorun randevu listesi testi
    async def test_get_my_appointments(self):
        p = models.Patient(tc_no="11111111115", first_name="Cem", last_name="Mert", birth_date=datetime.date(1993, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        date = get_next_weekday()
        time = datetime.time(14, 0)
        
        # Randevu al
        appt_data = schemas.AppointmentCreate(patient_tc=p.tc_no, clinic_id=1, doctor_id=1, appointment_date=date, appointment_time=time)
        await crud.create_appointment(self.session, appt_data)
        
        # Doktorun randevularını getir
        res = await crud.get_my_appointments(self.session, doctor_id=1, date_req=date)
        doc_result = await self.session.execute(select(models.Doctor).where(models.Doctor.id == 1))
        doc = doc_result.scalar_one()
        self.assertEqual(res.doctor_name, f"{doc.first_name} {doc.last_name}")
        self.assertEqual(len(res.appointments), 1)
        self.assertEqual(res.appointments[0].patient_tc, p.tc_no)

    # TEST 6: Muayene ve rapor kaydetme testi
    async def test_create_examination_and_save_report(self):
        p = models.Patient(tc_no="11111111116", first_name="Ebru", last_name="Şen", birth_date=datetime.date(1994, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        # Randevu al ve tamamla
        appt = models.Appointment(patient_id=p.id, doctor_id=1, appointment_date=datetime.date.today(), appointment_time=datetime.time(10, 0), status=models.AppointmentStatus.AKTIF)
        self.session.add(appt)
        await self.session.commit()
        
        exam_data = schemas.ExaminationCreate(
            patient_tc=p.tc_no,
            diagnosis="Miyopi",
            treatment="Gözlük kullanımı önerildi.",
            prescription="Göz Damlası A",
            medical_report="3 Gün İstirahat Uygundur.", # Eskiden kaydedilmeyen alan
            is_referred=False
        )
        
        db_exam = await crud.create_examination(self.session, exam_data)
        self.assertIsNotNone(db_exam.id)
        self.assertEqual(db_exam.medical_report, "3 Gün İstirahat Uygundur.") # Başarıyla kaydedildi mi bak

    # TEST 7: Hasta geçmişi sorgulama testi
    async def test_get_patient_history(self):
        p = models.Patient(tc_no="11111111117", first_name="Fatih", last_name="Kaya", birth_date=datetime.date(1995, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        appt = models.Appointment(patient_id=p.id, doctor_id=1, appointment_date=datetime.date.today(), appointment_time=datetime.time(10, 0), status=models.AppointmentStatus.TAMAMLANDI)
        self.session.add(appt)
        await self.session.commit()
        
        exam = models.Examination(appointment_id=appt.id, diagnosis="Göz Nezlesi", treatment="İlaç tedavisi", prescription="Damla", is_referred=False)
        self.session.add(exam)
        await self.session.commit()
        
        history = await crud.get_patient_history(self.session, tc_no=p.tc_no)
        self.assertEqual(history.patient.tc_no, p.tc_no)
        self.assertEqual(len(history.examinations), 1)
        self.assertEqual(history.examinations[0].diagnosis, "Göz Nezlesi")

    # TEST 8: Sigorta ve fatura hesaplama testi
    async def test_calculate_billing_insurance_discount(self):
        # 65 yaş üstü emekli hasta (%90 indirimli)
        p = models.Patient(tc_no="11111111118", first_name="Kemal", last_name="Dede", birth_date=datetime.date(1950, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        appt = models.Appointment(patient_id=p.id, doctor_id=1, appointment_date=datetime.date.today(), appointment_time=datetime.time(10, 0), status=models.AppointmentStatus.TAMAMLANDI)
        self.session.add(appt)
        await self.session.commit()
        
        exam = models.Examination(appointment_id=appt.id, diagnosis="Katarakt", treatment="Ameliyat önerildi", is_referred=False)
        self.session.add(exam)
        await self.session.commit()
        
        # Fatura hesapla
        bill = await crud.calculate_billing(self.session, tc_no=p.tc_no)
        self.assertEqual(bill.patient_tc, p.tc_no)
        self.assertEqual(bill.insurance_type, "Emekli")
        self.assertEqual(bill.base_amount, 1000.0)
        self.assertEqual(bill.discount_percentage, 90)
        self.assertEqual(bill.discount_amount, 900.0)
        self.assertEqual(bill.final_amount, 100.0) # 1000 - 900 = 100 TL

    # TEST 9: Ödeme alma testi
    async def test_process_payment_success(self):
        p = models.Patient(tc_no="11111111119", first_name="Lale", last_name="Sol", birth_date=datetime.date(1988, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        appt = models.Appointment(patient_id=p.id, doctor_id=1, appointment_date=datetime.date.today(), appointment_time=datetime.time(10, 0), status=models.AppointmentStatus.TAMAMLANDI)
        self.session.add(appt)
        await self.session.commit()
        
        exam = models.Examination(appointment_id=appt.id, diagnosis="Genel Kontrol", treatment="Gerek yok", is_referred=False)
        self.session.add(exam)
        await self.session.commit()
        
        # Fatura oluştur
        await crud.calculate_billing(self.session, tc_no=p.tc_no)
        
        # Ödeme yap
        pay_data = schemas.PaymentCreate(
            patient_tc=p.tc_no,
            payment_method=models.PaymentMethod.KREDI_KARTI
        )
        
        db_payment = await crud.process_payment(self.session, pay_data)
        self.assertEqual(db_payment.payment_status, models.PaymentStatus.ODENDI)
        self.assertEqual(db_payment.payment_method, models.PaymentMethod.KREDI_KARTI)

    # TEST 10: Kullanıcı giriş ve şifre doğrulama testi
    async def test_user_login(self):
        # Şifre kontrolü
        plain_password = "kayit123"
        hashed = auth.get_password_hash(plain_password)
        
        self.assertTrue(auth.verify_password(plain_password, hashed))
        self.assertFalse(auth.verify_password("yanlis_sifre", hashed))

    # TEST 11: Klinik ekleme testi
    async def test_create_clinic(self):
        # Yeni bir klinik ekle
        clinic_data = schemas.ClinicCreate(name="Kardiyoloji")
        db_clinic = await crud.create_clinic(self.session, clinic_data)
        
        # Eklenmiş mi diye kontrol et
        self.assertIsNotNone(db_clinic.id)
        self.assertEqual(db_clinic.name, "Kardiyoloji")
        self.assertTrue(db_clinic.is_active)

    # TEST 12: Doktor ekleme testi
    async def test_create_doctor(self):
        # Yeni doktor bilgileri
        doc_data = schemas.DoctorCreate(
            first_name="Hasan",
            last_name="Yazıcı",
            tc_no="33333333333",
            birth_date=datetime.date(1980, 1, 1),
            phone_number="5553333333",
            clinic_id=1,
            session_duration=30
        )
        # Doktoru kaydet
        db_doctor = await crud.create_doctor(self.session, doc_data)
        
        # Doktor ve ona bağlı oluşturulan kullanıcı hesabını kontrol et
        self.assertIsNotNone(db_doctor.id)
        self.assertEqual(db_doctor.first_name, "Hasan")
        
        # Otomatik açılan kullanıcı hesabını kontrol et
        user_result = await self.session.execute(
            select(models.User).where(models.User.username == "33333333333")
        )
        user = user_result.scalar_one_or_none()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, models.UserRole.DOCTOR)
        self.assertEqual(user.doctor_id, db_doctor.id)

    # TEST 13: Doktor ekleme doğrulama hataları testi
    async def test_create_doctor_validation_errors(self):
        from pydantic import ValidationError
        
        # Test: Invalid TC (too short)
        with self.assertRaises(ValidationError):
            schemas.DoctorCreate(
                first_name="Hasan",
                last_name="Yazıcı",
                tc_no="3333333333", # 10 digits
                birth_date=datetime.date(1980, 1, 1),
                phone_number="5553333333",
                clinic_id=1
            )

        # Test: Invalid TC (has letters)
        with self.assertRaises(ValidationError):
            schemas.DoctorCreate(
                first_name="Hasan",
                last_name="Yazıcı",
                tc_no="3333333333a", # letters
                birth_date=datetime.date(1980, 1, 1),
                phone_number="5553333333",
                clinic_id=1
            )

        # Test: Invalid Phone (too long)
        with self.assertRaises(ValidationError):
            schemas.DoctorCreate(
                first_name="Hasan",
                last_name="Yazıcı",
                tc_no="33333333333",
                birth_date=datetime.date(1980, 1, 1),
                phone_number="55533333333", # 11 digits
                clinic_id=1
            )

        # Test: Invalid Phone (has letters)
        with self.assertRaises(ValidationError):
            schemas.DoctorCreate(
                first_name="Hasan",
                last_name="Yazıcı",
                tc_no="33333333333",
                birth_date=datetime.date(1980, 1, 1),
                phone_number="555333333a", # letters
                clinic_id=1
            )

    # TEST 14: Randevu iptal testi
    async def test_cancel_appointment(self):
        # Önce hasta ve randevu oluştur
        p = models.Patient(tc_no="11111111120", first_name="Oya", last_name="Başar", birth_date=datetime.date(1990, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        appt = models.Appointment(
            patient_id=p.id,
            doctor_id=1,
            appointment_date=datetime.date.today(),
            appointment_time=datetime.time(15, 0),
            status=models.AppointmentStatus.AKTIF
        )
        self.session.add(appt)
        await self.session.commit()
        
        # Randevuyu iptal et
        cancelled_appt = await crud.cancel_appointment(self.session, appt.id)
        self.assertEqual(cancelled_appt.status, models.AppointmentStatus.IPTAL)
        
        # Zaten iptal edilmiş olanı tekrar iptal etmeyi dene (Hata vermeli)
        with self.assertRaises(HTTPException) as context:
            await crud.cancel_appointment(self.session, appt.id)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("zaten iptal", context.exception.detail)

    # TEST 15: Randevu erteleme testi
    async def test_reschedule_appointment(self):
        # Önce hasta ve randevu oluştur
        p = models.Patient(tc_no="11111111121", first_name="Can", last_name="Yılmaz", birth_date=datetime.date(1991, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        date1 = get_next_weekday()
        appt = models.Appointment(
            patient_id=p.id,
            doctor_id=1,
            appointment_date=date1,
            appointment_time=datetime.time(10, 0),
            status=models.AppointmentStatus.AKTIF
        )
        self.session.add(appt)
        await self.session.commit()
        
        # Randevuyu ertele
        new_date = get_next_weekday(date1)
        new_time = datetime.time(11, 30)
        resched_data = schemas.AppointmentReschedule(
            tc_no=p.tc_no,
            new_date=new_date,
            new_time=new_time
        )
        updated_appt = await crud.reschedule_appointment(self.session, appt.id, resched_data)
        
        # Güncellendi mi diye kontrol et
        self.assertEqual(updated_appt.appointment_date, new_date)
        self.assertEqual(updated_appt.appointment_time, new_time)

    # TEST 16: Olmayan sevk belgesi hata testi
    async def test_get_referral_fail(self):
        # Önce sevk edilmemiş muayene kaydı olan bir hasta oluştur
        p = models.Patient(tc_no="11111111122", first_name="Ela", last_name="Göz", birth_date=datetime.date(1995, 1, 1))
        self.session.add(p)
        await self.session.commit()
        
        appt = models.Appointment(
            patient_id=p.id,
            doctor_id=1,
            appointment_date=datetime.date.today(),
            appointment_time=datetime.time(10, 0),
            status=models.AppointmentStatus.TAMAMLANDI
        )
        self.session.add(appt)
        await self.session.commit()
        
        # Sevk edilmeyen muayene (is_referred=False)
        exam = models.Examination(
            appointment_id=appt.id,
            diagnosis="Sağlıklı",
            treatment="Sorun yok",
            is_referred=False
        )
        self.session.add(exam)
        await self.session.commit()
        
        # Sevk kaydı olmadığı için sevk belgesini almaya çalışınca hata vermeli
        with self.assertRaises(HTTPException) as context:
            await crud.get_referral(self.session, tc_no=p.tc_no)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("sevk kaydı bulunmuyor", context.exception.detail)

    # TEST 17: Hafta sonu ve geçmiş zamanlı randevu engeli testi
    async def test_create_appointment_weekend_and_past_checks(self):
        # Önce hasta oluştur
        p = models.Patient(tc_no="98765432101", first_name="Deniz", last_name="Yılmaz", birth_date=datetime.date(1990, 1, 1))
        self.session.add(p)
        await self.session.commit()

        # 1. Hafta sonu randevu denemesi
        future_saturday = datetime.date.today() + datetime.timedelta(days=1)
        while future_saturday.weekday() != 5: # 5: Saturday
            future_saturday += datetime.timedelta(days=1)
            
        appt_weekend = schemas.AppointmentCreate(
            patient_tc="98765432101",
            clinic_id=1,
            doctor_id=1,
            appointment_date=future_saturday,
            appointment_time=datetime.time(10, 0)
        )
        with self.assertRaises(HTTPException) as context:
            await crud.create_appointment(self.session, appt_weekend)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("sadece hafta içi", context.exception.detail)

        # 2. Geçmiş tarih randevu denemesi
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        appt_past_date = schemas.AppointmentCreate(
            patient_tc="98765432101",
            clinic_id=1,
            doctor_id=1,
            appointment_date=yesterday,
            appointment_time=datetime.time(10, 0)
        )
        with self.assertRaises(HTTPException) as context:
            await crud.create_appointment(self.session, appt_past_date)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Geçmiş bir tarihe", context.exception.detail)

        # 3. Bugün için geçmiş saat randevu denemesi
        now_time = datetime.datetime.now()
        test_time = datetime.time(10, 0)
        if now_time.time() > datetime.time(16, 30):
            test_time = datetime.time(10, 0)
        else:
            if now_time.time() > datetime.time(9, 0):
                test_time = datetime.time(9, 0)
            else:
                test_time = (now_time - datetime.timedelta(hours=1)).time()
                
        if datetime.time(9, 0) <= test_time <= datetime.time(16, 30) and now_time.time() > test_time:
            if datetime.date.today().weekday() < 5:
                appt_past_time = schemas.AppointmentCreate(
                    patient_tc="98765432101",
                    clinic_id=1,
                    doctor_id=1,
                    appointment_date=datetime.date.today(),
                    appointment_time=test_time
                )
                with self.assertRaises(HTTPException) as context:
                    await crud.create_appointment(self.session, appt_past_time)
                self.assertEqual(context.exception.status_code, 400)
                self.assertIn("geçmiştir", context.exception.detail)

    # TEST 18: Aynı doktor ve gün için tek aktif randevu sınırı testi
    async def test_create_appointment_same_doctor_same_day_limit(self):
        # Önce hasta oluştur
        p = models.Patient(tc_no="98765432199", first_name="Berna", last_name="Çakır", birth_date=datetime.date(1990, 1, 1))
        self.session.add(p)
        await self.session.commit()

        date = get_next_weekday()
        
        # 1. İlk randevuyu başarıyla al
        appt_data1 = schemas.AppointmentCreate(
            patient_tc=p.tc_no,
            clinic_id=1,
            doctor_id=1,
            appointment_date=date,
            appointment_time=datetime.time(10, 0)
        )
        await crud.create_appointment(self.session, appt_data1)
        
        # 2. Aynı gün aynı doktordan başka saate ikinci randevuyu almayı dene (Engellenmeli)
        appt_data2 = schemas.AppointmentCreate(
            patient_tc=p.tc_no,
            clinic_id=1,
            doctor_id=1,
            appointment_date=date,
            appointment_time=datetime.time(11, 0)
        )
        with self.assertRaises(HTTPException) as context:
            await crud.create_appointment(self.session, appt_data2)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("zaten aktif bir randevusu bulunmaktadır", context.exception.detail)

if __name__ == "__main__":
    unittest.main()