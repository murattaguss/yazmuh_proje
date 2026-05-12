"""
Şemalar (Schemas) Modülü
Bu modül Pydantic kullanılarak, verilerin frontend ve backend arasındaki 
iletişiminde kullanılacak olan "Data Transfer Objects" (DTO) sınıflarını tanımlar.
Bu sayede API'mize gelen istekler (request) ve dönen yanıtlar (response) tipleri 
kontrol edilerek (validation) güvenli bir şekilde işlenir.
"""
from pydantic import BaseModel, constr, validator
from datetime import date, time
from typing import Optional, List
from app.models import AppointmentStatus, PaymentMethod, PaymentStatus, UserRole

# --- Kimlik Doğrulama Şemaları ---
class Token(BaseModel):
    """Giriş yapan kullanıcıya döndürülecek token yapısı."""
    access_token: str
    token_type: str
    role: str

class TokenData(BaseModel):
    """Token içerisindeki taşınan veri."""
    username: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    doctor_id: Optional[int] = None

    class Config:
        from_attributes = True

# --- Klinik Şemaları ---
class ClinicBase(BaseModel):
    """Klinik ortak özelliklerini barındırır."""
    name: str

class ClinicCreate(ClinicBase):
    """Yeni klinik eklerken beklenen veriler."""
    pass

class ClinicResponse(ClinicBase):
    """Klinik bilgileri çekilirken dönülecek veri yapısı."""
    id: int
    is_active: bool

    class Config:
        from_attributes = True

# --- Doktor Şemaları ---
class DoctorBase(BaseModel):
    """Doktorun ortak kişisel ve mesleki bilgileri."""
    first_name: str
    last_name: str
    tc_no: constr(min_length=11, max_length=11)
    birth_date: date
    phone_number: str
    session_duration: Optional[int] = 30

class DoctorCreate(DoctorBase):
    """Sisteme (Admin paneli üzerinden) doktor eklerken kullanılan alanlar."""
    clinic_id: int

class DoctorResponse(DoctorBase):
    """Doktor eklendikten sonra veya bilgileri çekildiğinde dönülen yanıt."""
    id: int
    clinic_id: int
    generated_password: Optional[str] = None # Sadece doktor ilk eklendiğinde gösterilen tek kullanımlık açık şifre

    class Config:
        from_attributes = True

class DoctorListResponse(DoctorResponse):
    """Listelemelerde ekstra olarak kliniğin adı da döndürülür."""
    clinic_name: Optional[str] = None

# --- Hasta Şemaları ---
class PatientBase(BaseModel):
    """Hasta demografik bilgileri ve tıbbi verileri."""
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
    """Yeni hasta kaydı yapılırken kullanılan alanlar."""
    pass

class PatientResponse(PatientBase):
    """Sorgulama sonucunda hastaya ait dönülen bilgiler."""
    id: int
    created_at: date

    class Config:
        from_attributes = True

# --- Randevu Şemaları ---
class AppointmentBase(BaseModel):
    """Randevunun temel zaman parametreleri."""
    appointment_date: date
    appointment_time: time

class AppointmentCreate(AppointmentBase):
    """Rezervasyon görevlisi veya hasta tarafından alınan randevuda beklenen veriler."""
    patient_tc: str # TC numarası ile hastayı buluyoruz
    clinic_id: int  # Randevu alınacak klinik
    doctor_id: Optional[int] = None # Belirli bir doktor seçilmişse

class AppointmentResponse(AppointmentBase):
    """Randevu bilgilerini içeren geri dönüş formatı."""
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
    """Doktorun belirli bir gündeki uygun saatlerini döndürür."""
    doctor_id: int
    date: date
    available_times: List[time]

class AppointmentSearchResponse(BaseModel):
    """Randevu arama sonucunda döndürülen veri."""
    id: int
    patient_tc: str
    patient_name: str
    doctor_name: str
    clinic_name: str
    appointment_date: date
    appointment_time: time
    status: AppointmentStatus

# --- Muayene Şemaları ---
class ExaminationCreate(BaseModel):
    """Doktor panelinden muayene bitirildiğinde girilen tıbbi kayıtlar."""
    patient_tc: str
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    medical_report: Optional[str] = None
    is_referred: bool = False

class ExaminationResponse(BaseModel):
    """Eklenen muayene sonucunun çıktısı."""
    id: int
    appointment_id: int
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    is_referred: bool

    class Config:
        from_attributes = True

# --- Ödeme / Vezne Şemaları ---
class PaymentCreate(BaseModel):
    """Vezne tarafından tahsilat yapıldığında girilen bilgiler."""
    examination_id: int
    payment_method: PaymentMethod

class PaymentResponse(BaseModel):
    """Tahsilat sonrası dönülen makbuz/fatura bilgileri."""
    id: int
    examination_id: int
    base_amount: float
    discount_amount: float
    final_amount: float
    payment_method: PaymentMethod
    payment_status: PaymentStatus

    class Config:
        from_attributes = True

# --- Randevu Yönetim Şemaları ---
class AppointmentCancel(BaseModel):
    """Randevu iptali için kullanılan şema."""
    tc_no: str

class AppointmentReschedule(BaseModel):
    """Randevu erteleme / yeni tarihe alma işleminde kullanılan alanlar."""
    tc_no: str
    new_date: date
    new_time: time

class PatientHistoryResponse(BaseModel):
    """Hastanın geçmiş tıbbi verileriyle beraber döndürüldüğü kapsamlı sorgu yanıtı."""
    patient: PatientResponse
    examinations: List[ExaminationResponse]

# --- Doktor Günlük Görünüm Şemaları ---
class DoctorAppointmentDetail(BaseModel):
    """Doktor ekranında günlük randevu listesinde görünen kısa randevu detayı."""
    appointment_id: int
    patient_tc: str
    patient_name: str
    patient_phone: Optional[str] = None
    appointment_time: time
    status: AppointmentStatus

class DoctorDailyResponse(BaseModel):
    """Doktorun o güne ait randevularını toplu olarak döndüren yapı."""
    doctor_name: str
    date: date
    appointments: List[DoctorAppointmentDetail]

# --- Rapor ve Sevk Şemaları ---
class ReportResponse(BaseModel):
    """Hastaya e-Nabız tarzı verilebilecek detaylı muayene raporu çıktısı."""
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
    """Başka hastaneye / kuruma sevk durumunda hazırlanan sevk belgesi."""
    examination_id: int
    patient_tc: str
    patient_name: str
    patient_birth_date: date
    source_doctor: str
    source_clinic: str
    referral_date: date
    diagnosis: Optional[str] = None
    notes: Optional[str] = None

# --- Diğer Şemalar ---
class BillingResponse(BaseModel):
    """Muayenesi biten hastanın veznede görünen borç dökümü (Dış sigorta simüle edilmiş hali)."""
    examination_id: int
    patient_tc: str
    patient_name: str
    clinic_name: str
    base_amount: float
    discount_amount: float
    final_amount: float
    payment_status: PaymentStatus

class TransactionResponse(BaseModel):
    """Veznedarın sistemden tüm geçmiş fatura/ödeme işlemlerini görüntülemesi."""
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
