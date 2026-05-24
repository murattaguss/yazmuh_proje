document.addEventListener('DOMContentLoaded', () => {
    let authToken = localStorage.getItem('sifa_token');
    let userRole = localStorage.getItem('sifa_role');

    function showDashboard() {
        document.getElementById('login-screen').classList.add('hidden');
        document.getElementById('main-dashboard').classList.remove('hidden');
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        
        let title = 'Hoşgeldiniz';
        if(userRole === 'admin') {
            document.getElementById('admin-view').classList.add('active');
            title = 'Yönetici Paneli';
            loadDoctors(); loadClinics(); loadDoctorsAdmin();
        } else if(userRole === 'reception') {
            document.getElementById('registration-view').classList.add('active');
            title = 'Kayıt Paneli';
        } else if(userRole === 'appointment') {
            document.getElementById('appointment-view').classList.add('active');
            title = 'Rezervasyon Paneli';
            loadDoctors();
        } else if(userRole === 'doctor') {
            document.getElementById('doctor-view').classList.add('active');
            title = 'Doktor Paneli';
            document.getElementById('doc-daily-date').value = new Date().toISOString().split('T')[0];
            loadMyAppointments();
        } else if(userRole === 'cashier') {
            document.getElementById('cashier-view').classList.add('active');
            title = 'Vezne';
        }
        document.getElementById('page-title').textContent = title;
    }

    if(authToken) showDashboard();
    const todayStr = new Date().toISOString().split('T')[0];
    const appDateInput = document.getElementById('app-date');
    if (appDateInput) {
        appDateInput.setAttribute('min', todayStr);
    }

    const formLogin = document.getElementById('form-login');
    if (formLogin) {
        formLogin.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd = new URLSearchParams();
            fd.append('username', document.getElementById('login-username').value);
            fd.append('password', document.getElementById('login-password').value);
            try {
                const res = await fetch('/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: fd });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Giriş başarısız');
                authToken = data.access_token; userRole = data.role;
                localStorage.setItem('sifa_token', authToken); localStorage.setItem('sifa_role', userRole);
                showToast('Giriş başarılı!', 'success'); showDashboard(); formLogin.reset();
            } catch(e) { showToast(e.message, 'error'); }
        });
    }

        // Çıkış yapınca tokenı temizler ve giriş ekranını açar
document.getElementById('btn-logout').addEventListener('click', () => {
        localStorage.removeItem('sifa_token'); localStorage.removeItem('sifa_role');
        authToken = null; userRole = null;
        clearToast();
        document.getElementById('login-screen').classList.remove('hidden');
        document.getElementById('main-dashboard').classList.add('hidden');
    });

    let toastTimer = null;

        // Bildirim mesajları (toast) gösterir
function showToast(message, type = 'success', duration = 3000) {
        const toast = document.getElementById('toast');
        toast.textContent = message; toast.className = `toast show ${type}`;
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { toast.className = 'toast hidden'; toastTimer = null; }, duration);
    }

    function clearToast() {
        if (toastTimer) { clearTimeout(toastTimer); toastTimer = null; }
        const toast = document.getElementById('toast');
        toast.className = 'toast hidden';
    }

        // Sunucuyla haberleşen ana fonksiyon
async function apiCall(endpoint, method = 'GET', body = null) {
        if (!authToken) { showToast("Lütfen önce giriş yapın", "error"); throw new Error("Unauthorized"); }
        const options = { method, headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` } };
        if (body) options.body = JSON.stringify(body);
        const res = await fetch(endpoint, options);
        const data = await res.json();
        if (!res.ok) {
            const msg = data.detail?.message || (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
            if (res.status === 409 && data.detail?.alternatives) return { _conflict: true, ...data.detail };
            throw new Error(msg || 'Bir hata oluştu');
        }
        return data;
    }

    function statusBadge(status) {
        const map = { 'Aktif': 'active', 'İptal': 'cancelled', 'Tamamlandı': 'completed', 'Ödendi': 'paid', 'Bekliyor': 'pending' };
        return `<span class="badge badge-${map[status] || 'active'}">${status}</span>`;
    }
    // Doktor listesini çekip select kutusuna doldurur
    async function loadDoctors() {
        try {
            const doctors = await apiCall('/reception/doctors');
            const html = '<option value="" disabled selected>Doktor Seçin</option>' +
                doctors.map(d => `<option value="${d.id}">${d.first_name} ${d.last_name} (${d.clinic_name})</option>`).join('');
            const s1 = document.getElementById('app-doc-id'); if(s1) s1.innerHTML = html;
            const s2 = document.getElementById('usr-doc-id'); if(s2) s2.innerHTML = html;
        } catch(e) { console.error("Doktorlar yüklenemedi", e); }
    }
        // Yeni hasta ekler
document.getElementById('form-patient').addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            const res = await apiCall('/reception/patients', 'POST', {
                tc_no: document.getElementById('pat-tc').value, first_name: document.getElementById('pat-first').value,
                last_name: document.getElementById('pat-last').value, phone: document.getElementById('pat-phone').value,
                birth_date: document.getElementById('pat-birth').value,
                gender: document.getElementById('pat-gender').value || null,
                blood_type: document.getElementById('pat-blood').value || null,
                height: document.getElementById('pat-height').value ? parseFloat(document.getElementById('pat-height').value) : null,
                weight: document.getElementById('pat-weight').value ? parseFloat(document.getElementById('pat-weight').value) : null
            });
            showToast(`Hasta başarıyla kaydedildi. (ID: ${res.id})`); e.target.reset();
        } catch(e) { showToast(e.message, 'error'); }
    });

        // Seçilen günde doktorun boş saatlerini gösterir
document.getElementById('btn-check-avail').addEventListener('click', async () => {
        const docId = document.getElementById('app-doc-id').value;
        const date = document.getElementById('app-date').value;
        const resultDiv = document.getElementById('avail-result');
        if (!docId || !date) { showToast('Lütfen doktor ve tarih seçin.', 'error'); return; }
        try {
            const res = await apiCall(`/reception/availability?doctor_id=${docId}&date=${date}`);
            if(res.available_times.length > 0) {
                resultDiv.innerHTML = `<strong>Boş Saatler:</strong> ${res.available_times.map(t => t.substring(0,5)).join(', ')}`;
                resultDiv.className = 'alert info';
            } else { resultDiv.innerHTML = 'Seçilen günde boş saat bulunamadı.'; resultDiv.className = 'alert info'; }
        } catch(e) { resultDiv.className = 'hidden'; showToast(e.message, 'error'); }
    });

        // Randevuyu oluşturur
document.getElementById('form-appointment').addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            patient_tc: document.getElementById('app-pat-tc').value,
            doctor_id: parseInt(document.getElementById('app-doc-id').value),
            appointment_date: document.getElementById('app-date').value,
            appointment_time: document.getElementById('app-time').value + ":00"
        };
        try {
            const res = await apiCall('/reception/appointments', 'POST', payload);
            if (res._conflict) {
                showToast(res.message, 'error');
                const panel = document.getElementById('alt-times-panel');
                let altHtml = '';
                if (res.alternatives && res.alternatives.length > 0) {
                    altHtml += `<p><strong>Alternatif boş saatler:</strong></p><div class="alt-times-grid">${
                        res.alternatives.map(t => `<button class="alt-time-btn" data-time="${t}">${t}</button>`).join('')
                    }</div>`;
                }
                if (res.alternative_dates && res.alternative_dates.length > 0) {
                    altHtml += `<p style="margin-top: 10px;"><strong>Alternatif boş günler:</strong></p><div class="alt-dates-grid" style="display:flex; gap:8px; flex-wrap:wrap;">${
                        res.alternative_dates.map(d => `<button class="alt-date-btn btn btn-sm btn-secondary" data-date="${d}" style="margin:0;">${d}</button>`).join('')
                    }</div>`;
                }
                panel.innerHTML = altHtml;
                panel.classList.remove('hidden');
                panel.querySelectorAll('.alt-time-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        document.getElementById('app-time').value = btn.dataset.time;
                        showToast(`Saat ${btn.dataset.time} olarak ayarlandı.`, 'success');
                    });
                });
                panel.querySelectorAll('.alt-date-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        document.getElementById('app-date').value = btn.dataset.date;
                        showToast(`Tarih ${btn.dataset.date} olarak ayarlandı.`, 'success');
                    });
                });
                return;
            }
            showToast(`Randevu oluşturuldu! (ID: ${res.id})`); e.target.reset();
            document.getElementById('avail-result').className = 'hidden';
            document.getElementById('alt-times-panel').classList.add('hidden');
        } catch(e) { showToast(e.message, 'error'); }
    });
    document.getElementById('form-search-appt').addEventListener('submit', async (e) => {
        e.preventDefault();
        const tc = document.getElementById('search-appt-tc').value;
        try {
            const appointments = await apiCall(`/reception/appointments/search?tc_no=${tc}`);
            const tbody = document.getElementById('appt-search-tbody');
            if(appointments.length === 0) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Randevu bulunamadı.</td></tr>'; }
            else {
                tbody.innerHTML = appointments.map(a => `<tr>
                    <td>${a.doctor_name}<br><small>${a.clinic_name}</small></td>
                    <td>${a.appointment_date}</td><td>${String(a.appointment_time).substring(0,5)}</td>
                    <td>${statusBadge(a.status)}</td>
                    <td>${a.status === 'Aktif' ? `<div class="btn-group">
                        <button class="btn-sm btn-danger" onclick="cancelAppt(${a.id})">İptal</button>
                        <button class="btn-sm btn-warning" onclick="showReschedule(${a.id})">Ertele</button>
                    </div>` : '-'}</td></tr>`).join('');
            }
            document.getElementById('appt-search-result').classList.remove('hidden');
        } catch(e) { showToast(e.message, 'error'); }
    });

    window.cancelAppt = async function(id) {
        if(!confirm('Bu randevuyu iptal etmek istediğinize emin misiniz?')) return;
        try {
            await apiCall(`/reception/appointments/${id}/cancel`, 'PUT');
            showToast('Randevu iptal edildi. Slot serbest bırakıldı.');
            document.getElementById('form-search-appt').dispatchEvent(new Event('submit'));
        } catch(e) { showToast(e.message, 'error'); }
    };

    window.showReschedule = function(id) {
        const panel = document.getElementById('reschedule-panel');
        const todayStr = new Date().toISOString().split('T')[0];
        panel.innerHTML = `<div class="reschedule-form">
            <div class="form-group"><label>Yeni Tarih</label><input type="date" id="resc-date" min="${todayStr}"></div>
            <div class="form-group"><label>Yeni Saat</label><input type="time" id="resc-time" min="09:00" max="16:30"></div>
            <button class="btn btn-primary btn-sm" onclick="doReschedule(${id})">Onayla</button>
        </div>`;
        panel.classList.remove('hidden');
    };

    window.doReschedule = async function(id) {
        const nd = document.getElementById('resc-date').value;
        const nt = document.getElementById('resc-time').value;
        if(!nd || !nt) { showToast('Tarih ve saat seçin.', 'error'); return; }
        try {
            const res = await apiCall(`/reception/appointments/${id}/reschedule`, 'PUT', { new_date: nd, new_time: nt + ':00' });
            if(res._conflict) { 
                let msg = res.message + ' Alternatif Saatler: ' + res.alternatives.join(', ');
                if (res.alternative_dates && res.alternative_dates.length > 0) {
                    msg += ' | Alternatif Günler: ' + res.alternative_dates.join(', ');
                }
                showToast(msg, 'error'); 
                return; 
            }
            showToast('Randevu ertelendi!');
            document.getElementById('reschedule-panel').classList.add('hidden');
            document.getElementById('form-search-appt').dispatchEvent(new Event('submit'));
        } catch(e) { showToast(e.message, 'error'); }
    };
    // Doktorun o günkü hastalarını listeler
    async function loadMyAppointments() {
        const date = document.getElementById('doc-daily-date').value;
        if(!date) return;
        try {
            const res = await apiCall(`/doctor/my-appointments?date=${date}`);
            document.getElementById('doctor-welcome-name').textContent = "Hoş Geldiniz, " + res.doctor_name;
            const container = document.getElementById('daily-appointments-container');
            const statsDiv = document.getElementById('daily-stats');
            const appts = res.appointments;
            const activeCount = appts.filter(a => a.status === 'Aktif').length;
            const doneCount = appts.filter(a => a.status === 'Tamamlandı').length;
            statsDiv.innerHTML = `<span class="stat-chip total">Toplam: ${appts.length}</span>
                <span class="stat-chip active">Aktif: ${activeCount}</span>
                <span class="stat-chip completed">Tamamlandı: ${doneCount}</span>`;
            statsDiv.classList.remove('hidden');
            if(appts.length === 0) {
                container.innerHTML = '<div class="empty-state"><span>📋</span><p>Bu tarihte randevu bulunmuyor.</p></div>';
            } else {
                container.innerHTML = `<table class="data-table"><thead><tr>
                    <th>Saat</th><th>Hasta</th><th>TC</th><th>Telefon</th><th>Durum</th></tr></thead><tbody>${
                    appts.map(a => `<tr class="clickable-row" data-tc="${a.patient_tc}">
                        <td><strong>${String(a.appointment_time).substring(0,5)}</strong></td>
                        <td>${a.patient_name}</td><td>${a.patient_tc}</td>
                        <td>${a.patient_phone || '-'}</td><td>${statusBadge(a.status)}</td></tr>`).join('')
                }</tbody></table>`;
                container.querySelectorAll('.clickable-row').forEach(row => {
                    row.addEventListener('click', () => {
                        document.getElementById('query-pat-tc').value = row.dataset.tc;
                        document.getElementById('form-query-patient').dispatchEvent(new Event('submit'));
                        showToast(`${row.dataset.tc} hastası sorgulanıyor...`);
                    });
                });
            }
        } catch(e) { console.error(e); }
    }

    document.getElementById('btn-load-daily').addEventListener('click', loadMyAppointments);

    document.getElementById('form-query-patient').addEventListener('submit', async (e) => {
        e.preventDefault();
        const tcNo = document.getElementById('query-pat-tc').value;
        const resultDiv = document.getElementById('patient-info-result');
        try {
            const res = await apiCall(`/doctor/patients/${tcNo}`);
            document.getElementById('exam-pat-tc').value = tcNo;
            let html = `<h4 style="color: var(--primary-color); margin-bottom: 5px;">${res.patient.first_name} ${res.patient.last_name}</h4>`;
            html += `<p class="text-muted" style="font-size: 0.9em; margin-bottom: 10px;">D.Tarihi: ${res.patient.birth_date} | Tel: ${res.patient.phone || 'Yok'}</p>`;
            if (res.examinations.length === 0) { html += `<p style="font-size: 0.9em;">Geçmiş muayene kaydı bulunamadı.</p>`; }
            else {
                html += `<h5 style="margin-top: 10px; border-bottom: 1px solid var(--border-color); padding-bottom: 5px;">Geçmiş Muayeneler:</h5><ul style="padding-left: 20px; font-size: 0.9em; margin-top: 10px;">`;
                res.examinations.forEach(ex => {
                    html += `<li style="margin-bottom: 8px;"><strong>Muayene #${ex.id}</strong> — <strong>Tanı:</strong> ${ex.diagnosis || 'Belirtilmemiş'} <br> <strong>Tedavi:</strong> ${ex.treatment || 'Belirtilmemiş'} | <strong>Reçete:</strong> ${ex.prescription || 'Yok'} ${ex.is_referred ? ' | <span class="badge badge-pending">Sevk Edildi</span>' : ''}</li>`;
                });
                html += `</ul>`;
            }
            resultDiv.innerHTML = html; resultDiv.classList.remove('hidden');
            showToast('Hasta bilgileri getirildi.');
        } catch(e) { resultDiv.classList.add('hidden'); document.getElementById('exam-pat-tc').value = ''; }
    });

        // Muayene ve reçete bilgilerini kaydeder
document.getElementById('form-examination').addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            const res = await apiCall('/doctor/examinations', 'POST', {
                patient_tc: document.getElementById('exam-pat-tc').value,
                diagnosis: document.getElementById('exam-diag').value,
                treatment: document.getElementById('exam-treat').value,
                prescription: document.getElementById('exam-presc').value,
                is_referred: document.getElementById('exam-refer').checked
            });
            showToast(`Muayene kaydı tamamlandı! (Muayene ID: ${res.id})`); e.target.reset();
            loadMyAppointments();
        } catch(e) { showToast(e.message, 'error'); }
    });
        // Hastanın raporunu modal içinde açar
document.getElementById('form-report').addEventListener('submit', async (e) => {
        e.preventDefault();
        const tcNo = document.getElementById('report-pat-tc').value;
        try {
            const r = await apiCall(`/doctor/report/${tcNo}`);
            openModal('Muayene Raporu / Reçete', `
                <div class="report-brand"><h2>Şifa Polikliniği</h2><p>Muayene Raporu</p></div>
                <div class="report-field"><label>Hasta</label><p>${r.patient_name} (TC: ${r.patient_tc})</p></div>
                <div class="report-field"><label>Doğum Tarihi</label><p>${r.patient_birth_date}</p></div>
                <div class="report-field"><label>Doktor</label><p>${r.doctor_name} — ${r.clinic_name}</p></div>
                <div class="report-field"><label>Muayene Tarihi</label><p>${r.examination_date}</p></div>
                <div class="report-field"><label>Tanı</label><p>${r.diagnosis || 'Belirtilmemiş'}</p></div>
                <div class="report-field"><label>Tedavi</label><p>${r.treatment || 'Belirtilmemiş'}</p></div>
                <div class="report-field"><label>Reçete</label><p>${r.prescription || 'Reçete yok'}</p></div>
                ${r.is_referred ? '<div class="report-field"><label>Sevk</label><p>Hasta başka kuruma sevk edilmiştir.</p></div>' : ''}
            `);
        } catch(e) { showToast(e.message, 'error'); }
    });

    document.getElementById('btn-referral').addEventListener('click', async () => {
        const tcNo = document.getElementById('report-pat-tc').value;
        if(!tcNo) { showToast('Hasta TC Kimlik No girin.', 'error'); return; }
        try {
            const r = await apiCall(`/doctor/referral/${tcNo}`);
            openModal('Sevk Belgesi', `
                <div class="report-brand"><h2>Şifa Polikliniği</h2><p>Sevk Belgesi</p></div>
                <div class="report-field"><label>Hasta</label><p>${r.patient_name} (TC: ${r.patient_tc})</p></div>
                <div class="report-field"><label>Doğum Tarihi</label><p>${r.patient_birth_date}</p></div>
                <div class="report-field"><label>Sevk Eden Doktor</label><p>${r.source_doctor}</p></div>
                <div class="report-field"><label>Kaynak Klinik</label><p>${r.source_clinic}</p></div>
                <div class="report-field"><label>Sevk Tarihi</label><p>${r.referral_date}</p></div>
                <div class="report-field"><label>Tanı</label><p>${r.diagnosis || 'Belirtilmemiş'}</p></div>
                <div class="report-field"><label>Notlar</label><p>${r.notes || '-'}</p></div>
            `);
        } catch(e) { showToast(e.message, 'error'); }
    });
    function openModal(title, bodyHtml) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = bodyHtml;
        document.getElementById('modal-overlay').classList.remove('hidden');
    }
    function closeModal() { document.getElementById('modal-overlay').classList.add('hidden'); }
    document.getElementById('modal-close-btn').addEventListener('click', closeModal);
    document.getElementById('modal-close-btn2').addEventListener('click', closeModal);
    document.getElementById('modal-print-btn').addEventListener('click', () => window.print());
    document.getElementById('modal-overlay').addEventListener('click', (e) => { if(e.target.id === 'modal-overlay') closeModal(); });
    document.getElementById('form-calc-bill').addEventListener('submit', async (e) => {
        e.preventDefault();
        const tcNo = document.getElementById('bill-pat-tc').value;
        try {
            const res = await apiCall(`/cashier/billing/${tcNo}`);
            document.getElementById('res-tc').textContent = res.patient_tc;
            document.getElementById('res-ins-type').textContent = res.insurance_type;
            document.getElementById('res-base').textContent = res.base_amount;
            document.getElementById('res-disc-perc').textContent = res.discount_percentage;
            document.getElementById('res-disc-amt').textContent = res.discount_amount;
            document.getElementById('res-final').textContent = res.final_amount;
            document.getElementById('bill-result').classList.remove('hidden');
            showToast('Fatura hesaplandı.');
        } catch(e) { document.getElementById('bill-result').classList.add('hidden'); showToast(e.message, 'error'); }
    });

        // Ödemeyi alır (kart/nakit)
document.getElementById('form-payment').addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            const res = await apiCall('/cashier/payments', 'POST', {
                patient_tc: document.getElementById('pay-pat-tc').value,
                payment_method: document.getElementById('pay-method').value
            });
            showToast(`Ödeme başarıyla alındı! (Yöntem: ${res.payment_method})`);
            e.target.reset(); document.getElementById('bill-result').classList.add('hidden');
        } catch(e) { showToast(e.message, 'error'); }
    });

    document.getElementById('form-transactions').addEventListener('submit', async (e) => {
        e.preventDefault();
        const tc = document.getElementById('txn-tc').value;
        const st = document.getElementById('txn-status').value;
        let url = '/cashier/transactions?';
        if(tc) url += `tc_no=${tc}&`;
        if(st) url += `status=${st}&`;
        try {
            const txns = await apiCall(url);
            const tbody = document.getElementById('txn-tbody');
            if(txns.length === 0) { tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;">Kayıt bulunamadı.</td></tr>'; }
            else {
                tbody.innerHTML = txns.map(t => `<tr>
                    <td>${t.payment_id}</td><td>${t.patient_name}</td><td>${t.patient_tc}</td>
                    <td>${t.examination_date}</td><td>${t.base_amount} TL</td><td>${t.discount_amount} TL</td>
                    <td><strong>${t.final_amount} TL</strong></td><td>${t.payment_method || '-'}</td>
                    <td>${statusBadge(t.payment_status)}</td></tr>`).join('');
            }
            document.getElementById('txn-result').classList.remove('hidden');
            showToast(`${txns.length} kayıt bulundu.`);
        } catch(e) { showToast(e.message, 'error'); }
    });
    document.getElementById('form-clinic').addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            const res = await apiCall('/admin/clinics', 'POST', { name: document.getElementById('clinic-name').value });
            showToast(`Klinik eklendi! (ID: ${res.id})`); e.target.reset(); loadClinics();
        } catch(e) { showToast(e.message, 'error'); }
    });

        // Doktor ekler (şifreyi 30 saniye gösterir)
document.getElementById('form-doctor').addEventListener('submit', async (e) => {
        e.preventDefault();
        const tcNo = document.getElementById('doc-tc').value;
        const phone = document.getElementById('doc-phone').value;

        if (!/^\d{11}$/.test(tcNo)) {
            showToast('T.C. Kimlik Numarası tam olarak 11 haneli ve sadece rakamlardan oluşmalıdır.', 'error');
            return;
        }

        if (!/^\d{10}$/.test(phone)) {
            showToast('Telefon numarası tam olarak 10 haneli (örn: 5013302285) ve sadece rakamlardan oluşmalıdır.', 'error');
            return;
        }

        try {
            const res = await apiCall('/admin/doctors', 'POST', {
                clinic_id: parseInt(document.getElementById('doc-clinic-id').value),
                first_name: document.getElementById('doc-first').value,
                last_name: document.getElementById('doc-last').value,
                tc_no: tcNo,
                birth_date: document.getElementById('doc-birth').value,
                phone_number: phone || null
            });
            showToast(`Doktor eklendi! Kullanıcı Adı: ${res.tc_no} | Şifre: ${res.generated_password}`, 'success', 30000); 
            e.target.reset(); loadDoctors(); loadDoctorsAdmin();
        } catch(e) { showToast(e.message, 'error'); }
    });
    window.switchAdminTab = function(tabId) {
        document.querySelectorAll('.admin-tab-content').forEach(tab => tab.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        
        document.querySelectorAll('.admin-menu-btn').forEach(btn => {
            const onclickAttr = btn.getAttribute('onclick') || '';
            if(onclickAttr.includes(`'${tabId}'`) || onclickAttr.includes(`"${tabId}"`)) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    };
    window.switchDocTab = function(tabId) {
        document.querySelectorAll('#doctor-view .admin-tab-content').forEach(tab => tab.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        
        document.querySelectorAll('#doctor-view .admin-menu-btn').forEach(btn => {
            const onclickAttr = btn.getAttribute('onclick') || '';
            if(onclickAttr.includes(`'${tabId}'`) || onclickAttr.includes(`"${tabId}"`)) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    };

    async function loadClinics() {
        try {
            const clinics = await apiCall('/admin/clinics');
            document.getElementById('clinics-tbody').innerHTML = clinics.map(c => `<tr>
                <td>${c.name}</td><td>${statusBadge(c.is_active ? 'Aktif' : 'İptal')}</td>
            </tr>`).join('');
            
            const docClinicSelect = document.getElementById('doc-clinic-id');
            if(docClinicSelect) {
                docClinicSelect.innerHTML = '<option value="" disabled selected>Klinik Seçiniz</option>' + 
                    clinics.filter(c => c.is_active).map(c => `<option value="${c.id}">${c.name}</option>`).join('');
            }
        } catch(e) {}
    }

    // Yönetici panelindeki doktor tablosunu doldurur
    async function loadDoctorsAdmin() {
        try {
            const docs = await apiCall('/admin/doctors');
            document.getElementById('doctors-tbody').innerHTML = docs.map(d => `<tr>
                <td>${d.tc_no}</td><td>${d.first_name} ${d.last_name}</td><td>${d.clinic_name}</td><td>${d.phone_number || '-'}</td>
            </tr>`).join('');
        } catch(e) {}
    }

    document.getElementById('btn-load-clinics').addEventListener('click', loadClinics);
    document.getElementById('btn-load-doctors-admin').addEventListener('click', loadDoctorsAdmin);
});
