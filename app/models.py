"""
Veritabanı tablolarımız.
SQLAlchemy ile tabloları ve birbirleriyle olan ilişkileri burada tanımladık.
"""
import datetime
from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey, Text, Float, Enum
from sqlalchemy.orm import relationship
from app.database import Base
import enum

# Randevu durumları
class AppointmentStatus(str, enum.Enum):
    AKTIF = "Aktif"
    IPTAL = "İptal"
    TAMAMLANDI = "Tamamlandı"

# Ödeme yöntemleri
class PaymentMethod(str, enum.Enum):
    NAKIT = "Nakit"
    KREDI_KARTI = "Kredi Kartı"

# Ödeme durumu
class PaymentStatus(str, enum.Enum):
    ODENDI = "Ödendi"
    BEKLIYOR = "Bekliyor"

# Kullanıcı rolleri (admin, vezne vb.)
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    RECEPTION = "reception"
    APPOINTMENT = "appointment"
    DOCTOR = "doctor"
    CASHIER = "cashier"

class User(Base):
    """
    Sisteme giriş yapan herkesin (admin, doktor, vezne vb.) hesabı buradadır.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False) # Kullanıcı adı (TC de olabilir)
    hashed_password = Column(String, nullable=False) # Güvenlik için şifreyi hashliyoruz
    role = Column(Enum(UserRole), nullable=False) # Rolü
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True) # Doktorsa id'si burada yazar

    # Doktor tablosu ile ilişki
    doctor = relationship("Doctor")

class Clinic(Base):
    """Klinikler (Göz, Dahiliye vs.)"""
    __tablename__ = "clinics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True) # Aktif mi pasif mi (silmek yerine pasif yapabilmek için)

    # Klinikteki doktorlar
    doctors = relationship("Doctor", back_populates="clinic")

class Doctor(Base):
    """Doktorların bilgileri"""
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    tc_no = Column(String(11), unique=True, index=True, nullable=False)
    birth_date = Column(Date, nullable=False)
    phone_number = Column(String(15), unique=True, nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False) # Çalıştığı klinik id'si
    session_duration = Column(Integer, default=30) # Randevu süresi (dk olarak, default 30)

    clinic = relationship("Clinic", back_populates="doctors")
    appointments = relationship("Appointment", back_populates="doctor")

class Patient(Base):
    """Hastaların kişisel ve tıbbi bilgileri"""
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    tc_no = Column(String(11), unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=True)
    birth_date = Column(Date, nullable=False)
    gender = Column(String(10), nullable=True)
    height = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    blood_type = Column(String(5), nullable=True)
    created_at = Column(Date, default=datetime.date.today) # Kayıt tarihi

    appointments = relationship("Appointment", back_populates="patient")

class Appointment(Base):
    """
    Randevular tablosu
    """
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    appointment_date = Column(Date, nullable=False)
    appointment_time = Column(Time, nullable=False)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.AKTIF)

    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")
    
    # Muayene ile ilişki
    examination = relationship("Examination", back_populates="appointment", uselist=False)

class Examination(Base):
    """
    Muayene bittikten sonra doktorun yazdığı rapor, tanı, ilaçlar vs.
    """
    __tablename__ = "examinations"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=False)
    diagnosis = Column(Text, nullable=True)      # Teşhis
    treatment = Column(Text, nullable=True)      # Tedavi yöntemi
    prescription = Column(Text, nullable=True)   # İlaçlar / Reçete
    medical_report = Column(Text, nullable=True) # Rapor (istirahat vb.)
    is_referred = Column(Boolean, default=False) # Başka yere sevk edilme durumu

    appointment = relationship("Appointment", back_populates="examination")
    # Ödeme tablosuyla ilişki
    payment = relationship("Payment", back_populates="examination", uselist=False)

class Payment(Base):
    """
    Fatura ve ödeme bilgileri
    """
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    examination_id = Column(Integer, ForeignKey("examinations.id"), unique=True, nullable=False)
    base_amount = Column(Float, nullable=False)        # İndirimsiz normal ücret
    discount_amount = Column(Float, default=0.0)       # Sigorta indirimi
    final_amount = Column(Float, nullable=False)       # Ödenecek net ücret
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.BEKLIYOR)

    examination = relationship("Examination", back_populates="payment")
