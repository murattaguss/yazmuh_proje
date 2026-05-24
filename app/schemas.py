"""
API şemalarımız.
Frontend ile veri alışverişi yaparken tipleri kontrol etmek için Pydantic şemaları.
"""
from pydantic import BaseModel, constr, validator
from datetime import date, time
from typing import Optional, List
from app.models import AppointmentStatus, PaymentMethod, PaymentStatus, UserRole

# Giriş/Token Şemaları
class Token(BaseModel):
    """Kullanıcıya dönecek token bilgisi"""
    access_token: str
    token_type: str
    role: str

class TokenData(BaseModel):
    """Token içindeki veri"""
    username: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    doctor_id: Optional[int] = None

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    """Yeni kullanıcı oluşturma şeması"""
    username: str
    password: str
    role: UserRole
    doctor_id: Optional[int] = None

# Klinik Şemaları
class ClinicBase(BaseModel):
    """Klinik genel bilgileri"""
    name: str

class ClinicCreate(ClinicBase):
    """Yeni klinik oluşturma şeması"""
    pass

class ClinicResponse(ClinicBase):
    """Klinik yanıt şeması"""
    id: int
    is_active: bool

    class Config:
        from_attributes = True

# Doktor Şemaları
class DoctorBase(BaseModel):
    """Doktor genel bilgileri"""
    first_name: str
    last_name: str
    tc_no: str
    birth_date: date
    phone_number: str
    session_duration: Optional[int] = 30

class DoctorCreate(DoctorBase):
    """Doktor ekleme şeması"""
    tc_no: constr(min_length=11, max_length=11, pattern=r'^\d{11}$')
    phone_number: constr(min_length=10, max_length=10, pattern=r'^\d{10}$')
    clinic_id: int

class DoctorResponse(DoctorBase):
    """Doktor yanıt şeması"""
    id: int
    clinic_id: int
    generated_password: Optional[str] = None # İlk eklendiğindeki geçici şifre

    class Config:
        from_attributes = True

class DoctorListResponse(DoctorResponse):
    """Doktor listelerken kliniği de gösterir"""
    clinic_name: Optional[str] = None

# Hasta Şemaları
class PatientBase(BaseModel):
    """Hasta genel bilgileri"""
    tc_no: constr(min_length=11, max_length=11)
    first_name: str
    last_name: str
    phone: Optional[str] = None
    birth_date: date
    gender: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    blood_type: Optional[str] = None

class PatientCreate(PatientBase):
    """Hasta ekleme şeması"""
    pass

class PatientResponse(PatientBase):
    """Hasta yanıt şeması"""
    id: int
    created_at: date

    class Config:
        from_attributes = True

# Randevu Şemaları
class AppointmentBase(BaseModel):
    """Randevu zamanı"""
    appointment_date: date
    appointment_time: time

class AppointmentCreate(AppointmentBase):
    """Randevu ekleme şeması"""
    patient_tc: str # Hasta TC numarası
    clinic_id: Optional[int] = None  # Hangi klinik
    doctor_id: Optional[int] = None # Varsa doktor

class AppointmentResponse(AppointmentBase):
    """Randevu yanıt şeması"""
    id: int
    patient_id: int
    doctor_id: int
    status: AppointmentStatus
    doctor_name: Optional[str] = None
    clinic_name: Optional[str] = None
    patient_name: Optional[str] = None

    class Config:
        from_attributes = True

class AvailabilityResponse(BaseModel):
    """Doktorun boş saatleri"""
    doctor_id: int
    date: date
    available_times: List[time]

class AppointmentSearchResponse(BaseModel):
    """Randevu arama sonucu"""
    id: int
    patient_tc: str
    patient_name: str
    doctor_name: str
    clinic_name: str
    appointment_date: date
    appointment_time: time
    status: AppointmentStatus

# Muayene Şemaları
class ExaminationCreate(BaseModel):
    """Muayene ekleme şeması"""
    patient_tc: str
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    medical_report: Optional[str] = None
    is_referred: bool = False

class ExaminationResponse(BaseModel):
    """Muayene yanıt şeması"""
    id: int
    appointment_id: int
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    is_referred: bool

    class Config:
        from_attributes = True

# Ödeme ve Vezne Şemaları
class PaymentCreate(BaseModel):
    """Ödeme oluşturma şeması"""
    patient_tc: constr(min_length=11, max_length=11)
    payment_method: PaymentMethod

class PaymentResponse(BaseModel):
    """Ödeme yanıt şeması"""
    id: int
    examination_id: int
    base_amount: float
    discount_amount: float
    final_amount: float
    payment_method: PaymentMethod
    payment_status: PaymentStatus

    class Config:
        from_attributes = True

# Randevu İşlemleri
class AppointmentCancel(BaseModel):
    """Randevu iptal etme şeması"""
    tc_no: str

class AppointmentReschedule(BaseModel):
    """Randevu erteleme şeması"""
    tc_no: str
    new_date: date
    new_time: time

class PatientHistoryResponse(BaseModel):
    """Hastanın geçmiş muayeneleri"""
    patient: PatientResponse
    examinations: List[ExaminationResponse]

# Doktor Ekranı Şemaları
class DoctorAppointmentDetail(BaseModel):
    """Doktorun göreceği randevu detayı"""
    appointment_id: int
    patient_tc: str
    patient_name: str
    patient_phone: Optional[str] = None
    appointment_time: time
    status: AppointmentStatus

class DoctorDailyResponse(BaseModel):
    """Doktorun o günkü randevuları"""
    doctor_name: str
    date: date
    appointments: List[DoctorAppointmentDetail]

# Rapor ve Sevk Şemaları
class ReportResponse(BaseModel):
    """Muayene raporu şeması"""
    examination_id: int
    patient_tc: str
    patient_name: str
    patient_birth_date: date
    doctor_name: str
    clinic_name: str
    examination_date: date
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    medical_report: Optional[str] = None
    is_referred: bool = False

class ReferralResponse(BaseModel):
    """Sevk belgesi şeması"""
    examination_id: int
    patient_tc: str
    patient_name: str
    patient_birth_date: date
    source_doctor: str
    source_clinic: str
    referral_date: date
    diagnosis: Optional[str] = None
    notes: Optional[str] = None

# Fatura ve İşlemler
class BillingResponse(BaseModel):
    """Fatura dökümü şeması"""
    examination_id: int
    patient_tc: str
    insurance_type: str
    base_amount: float
    discount_percentage: int
    discount_amount: float
    final_amount: float

class TransactionResponse(BaseModel):
    """Geçmiş ödemeler listesi"""
    payment_id: int
    examination_id: int
    patient_tc: str
    patient_name: str
    base_amount: float
    discount_amount: float
    final_amount: float
    payment_method: Optional[str] = None
    payment_status: str
    examination_date: date
