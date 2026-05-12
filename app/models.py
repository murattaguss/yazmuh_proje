"""
Veritabanı Modelleri Modülü
Bu modül, SQLAlchemy ORM (Object-Relational Mapping) kullanarak 
veritabanındaki tablolarımızın yapısını, alanlarını ve birbirleriyle 
olan ilişkilerini (foreign key, relationship) tanımlar.
"""
import datetime
from sqlalchemy import Column, Integer, String, Boolean, Date, Time, ForeignKey, Text, Float, Enum
from sqlalchemy.orm import relationship
from app.database import Base
import enum

# Randevu durumlarını takip ettiğimiz Enum.
class AppointmentStatus(str, enum.Enum):
    AKTIF = "Aktif"
    IPTAL = "İptal"
    TAMAMLANDI = "Tamamlandı"

# Ödeme yöntemleri (Vezne işlemleri için).
class PaymentMethod(str, enum.Enum):
    NAKIT = "Nakit"
    KREDI_KARTI = "Kredi Kartı"

# Fatura / Ödeme durumu.
class PaymentStatus(str, enum.Enum):
    ODENDI = "Ödendi"
    BEKLIYOR = "Bekliyor"

# Kullanıcı yetki (rol) tanımlamaları. Sistemin erişim kontrolleri buna göre yapılır.
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    RECEPTION = "reception"
    APPOINTMENT = "appointment"
    DOCTOR = "doctor"
    CASHIER = "cashier"

class User(Base):
    """
    Sisteme giriş yapan personellerin ve yöneticilerin hesaplarını tutar.
    Doktorlar da buraya bağlıdır, bu sayede kendi panellerine giriş yapabilirler.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False) # TC Kimlik No veya özel bir ad olabilir
    hashed_password = Column(String, nullable=False) # Şifreler kesinlikle hash'lenerek saklanır
    role = Column(Enum(UserRole), nullable=False) # Kullanıcının yetki alanı
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True) # Eğer kullanıcı bir doktorsa, doktor profiliyle eşleşir

    # Sadece doktor profiline sahip kullanıcılar için ilişki
    doctor = relationship("Doctor")

class Clinic(Base):
    """Polikliniğimizde bulunan bölümleri/klinikleri (Örn: Göz, Dahiliye) temsil eder."""
    __tablename__ = "clinics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True) # İleride kliniği silmek yerine pasife alabiliriz

    # Bu klinikte çalışan tüm doktorların listesi
    doctors = relationship("Doctor", back_populates="clinic")

class Doctor(Base):
    """Doktorların kişisel ve mesleki bilgilerini tutan tablomuz."""
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    tc_no = Column(String(11), unique=True, index=True, nullable=False)
    birth_date = Column(Date, nullable=False)
    phone_number = Column(String(15), unique=True, nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False) # Hangi kliniğe bağlı olduğu
    session_duration = Column(Integer, default=30) # Her randevunun kaç dakika süreceği (varsayılan 30 dk)

    clinic = relationship("Clinic", back_populates="doctors")
    appointments = relationship("Appointment", back_populates="doctor")

class Patient(Base):
    """Hastalarımızın demografik ve tıbbi kimlik bilgilerinin tutulduğu yer."""
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
    created_at = Column(Date, default=datetime.date.today) # Sisteme ilk kayıt tarihi

    appointments = relationship("Appointment", back_populates="patient")

class Appointment(Base):
    """
    Kayıt/Rezervasyon modülü tarafından oluşturulan randevular.
    Hasta ve Doktor arasındaki zaman çizelgesini bağlar.
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
    
    # Randevu tamamlandığında ona bağlı bir muayene (examination) oluşturulur.
    examination = relationship("Examination", back_populates="appointment", uselist=False)

class Examination(Base):
    """
    Doktorun randevu sonrasında hastaya koyduğu tanı, verdiği tedavi ve reçete gibi
    muayene kayıtlarını içeren tıbbi döküman tablosudur.
    """
    __tablename__ = "examinations"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=False)
    diagnosis = Column(Text, nullable=True)      # Doktorun koyduğu teşhis
    treatment = Column(Text, nullable=True)      # Önerilen veya uygulanan tedavi
    prescription = Column(Text, nullable=True)   # Yazılan ilaçlar
    medical_report = Column(Text, nullable=True) # Varsa hastaya verilen işgöremezlik vb. rapor
    is_referred = Column(Boolean, default=False) # Hastanın başka bir kuruma sevk edilip edilmediği

    appointment = relationship("Appointment", back_populates="examination")
    # Muayene bittiğinde vezneye yansıyacak olan ödeme
    payment = relationship("Payment", back_populates="examination", uselist=False)

class Payment(Base):
    """
    Vezne (Cashier) modülü için fatura ve tahsilat kayıtlarını içerir.
    Simüle edilen sigorta servisinden dönen tutarlar burada saklanır ve ödenir.
    """
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    examination_id = Column(Integer, ForeignKey("examinations.id"), unique=True, nullable=False)
    base_amount = Column(Float, nullable=False)        # İşlemin indirimsiz tam tutarı
    discount_amount = Column(Float, default=0.0)       # Sigortanın vb. karşıladığı indirim tutarı
    final_amount = Column(Float, nullable=False)       # Hastanın vezneye ödemesi gereken net tutar
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.BEKLIYOR)

    examination = relationship("Examination", back_populates="payment")
