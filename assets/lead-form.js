// ============================================================
// Em Tâm Làm Ads — form đăng ký trên các landing page (.lead-form)
// Gửi về trang quản trị trên VPS (server/app.py) — khách mới hiện trong admin + báo Telegram.
// Chưa có LEAD_ENDPOINT thì tự chuyển sang gửi qua Messenger.
// ============================================================
var LEAD_ENDPOINT = 'https://admin.emtamlamads.com/api/lead';

(function(){
  var MESSENGER = 'https://m.me/emtamlamads';
  var qs = new URLSearchParams(location.search);
  var utm = ['utm_source','utm_medium','utm_campaign','utm_content','fbclid'].filter(function(k){ return qs.get(k); })
    .map(function(k){ return k + '=' + qs.get(k).slice(0, 80); }).join('&');
  var LABELS = { email:'Email', fanpage:'Fanpage', date:'Ngày hẹn', times:'Khung giờ (giờ VN)', budget:'Ngân sách ads/tháng', goal:'Mục tiêu', note:'Ghi chú' };
  var VN_TZ = 'Asia/Ho_Chi_Minh';

  // Giờ Việt Nam hiện tại (+ giờ của khách nếu họ ở múi giờ khác), ngày hẹn không chọn được ngày đã qua
  function vnParts(d){ var o = {}; new Intl.DateTimeFormat('en-CA', { timeZone:VN_TZ, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false })
    .formatToParts(d).forEach(function(x){ o[x.type] = x.value; }); return o; }
  function tick(){
    var now = new Date(), v = vnParts(now), local = now.toLocaleTimeString('vi-VN', { hour:'2-digit', minute:'2-digit' });
    var same = Intl.DateTimeFormat().resolvedOptions().timeZone === VN_TZ || -now.getTimezoneOffset() === 420;
    var txt = v.hour + ':' + v.minute + ' (' + v.day + '/' + v.month + ')' + (same ? '' : ' — giờ chỗ bạn: ' + local);
    document.querySelectorAll('[data-vn-clock]').forEach(function(el){ el.textContent = txt; });
  }
  try { tick(); setInterval(tick, 30000);
    var t = vnParts(new Date()), today = t.year + '-' + t.month + '-' + t.day;
    document.querySelectorAll('input[name="date"]').forEach(function(el){ el.min = today; });
  } catch(err) {}

  function esc(t){ return String(t).replace(/[&<>"]/g, function(c){ return { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]; }); }

  document.querySelectorAll('.lead-form').forEach(function(form){
    var status = form.querySelector('.lf-status');
    var kind = form.getAttribute('data-kind') || 'Tư vấn';
    var doneText = form.getAttribute('data-done') || 'tư vấn cho bạn';
    function val(n){ var el = form.querySelector('[name="' + n + '"]'); return el ? el.value.trim() : ''; }

    form.addEventListener('submit', function(e){
      e.preventDefault();
      var name = val('name'), phone = val('phone').replace(/[\s.\-()]/g, ''), email = val('email');
      function fail(msg, n){ status.textContent = msg; var el = form.querySelector('[name="' + n + '"]'); if(el) el.focus(); }
      if(!name) return fail('Bạn điền giúp Tâm tên nhé.', 'name');
      if(!phone && !email) return fail('Bạn để lại số điện thoại hoặc email để Tâm liên hệ nhé.', 'phone');
      if(phone && !/^\+?\d{9,13}$/.test(phone)) return fail('Số điện thoại chưa đúng, bạn kiểm tra lại giúp Tâm nhé.', 'phone');
      if(email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return fail('Email chưa đúng, bạn kiểm tra lại giúp Tâm nhé.', 'email');
      var date = val('date'); if(date){ var dp = date.split('-'); date = dp[2] + '/' + dp[1] + '/' + dp[0]; }

      var data = { kind:kind, name:name, phone:phone, email:email, date:date,
        times:[].slice.call(form.querySelectorAll('input[name="time"]:checked')).map(function(i){ return i.value; }).join(', '),
        fanpage:val('fanpage'), budget:val('budget'), goal:val('goal'), note:val('note'),
        page:location.pathname.replace(/\/index\.html$/, '/') + (form.getAttribute('data-pos') ? ' (' + form.getAttribute('data-pos') + ')' : ''),
        utm:utm, website:val('website') };
      var lines = ['Chào Tâm, mình muốn ' + kind.toLowerCase() + ':', '- Tên: ' + name]; if(phone) lines.push('- SĐT/Zalo: ' + phone);
      Object.keys(LABELS).forEach(function(k){ if(data[k]) lines.push('- ' + LABELS[k] + ': ' + data[k]); });
      var text = lines.join('\n');
      var btn = form.querySelector('.lf-submit');

      if(!LEAD_ENDPOINT){
        if(navigator.clipboard) navigator.clipboard.writeText(text).catch(function(){});
        var w = window.open(MESSENGER + '?text=' + encodeURIComponent(text), '_blank');
        if(w) w.opener = null;
        status.textContent = 'Đã mở Messenger với thông tin soạn sẵn — bấm Gửi là xong.';
        return;
      }
      btn.disabled = true; status.textContent = 'Đang gửi…';
      fetch(LEAD_ENDPOINT, { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify(data) })
        .then(function(r){ return r.json().catch(function(){ return { ok:false }; }).then(function(j){ if(!r.ok || !j.ok) throw new Error(j.error || 'send'); }); })
        .then(function(){
          if(window.fbq) try{ fbq('track', 'Lead', { content_name:kind }); }catch(err){}
          form.innerHTML = '<div class="lf-done"><div class="lf-check">✓</div><h3>Cảm ơn ' + esc(name) + '!</h3>' +
            '<p>Tâm đã nhận thông tin và sẽ liên hệ qua <b>' + esc(phone || email) + '</b> trong 24 giờ để ' + esc(doneText) +
            (date || data.times ? ' — theo lịch bạn chọn: <b>' + esc([date, data.times].filter(Boolean).join(', ')) + '</b> (giờ Việt Nam)' : '') + '.</p>' +
            '<p>Muốn nhanh hơn? Nhắn luôn cho Tâm:</p>' +
            '<a class="btn btn-primary" target="_blank" rel="noopener" href="' + MESSENGER + '?text=' + encodeURIComponent(text) + '">Nhắn Messenger</a></div>';
        })
        .catch(function(){
          btn.disabled = false;
          status.innerHTML = 'Chưa gửi được — bạn thử lại, hoặc <a target="_blank" rel="noopener" href="' + MESSENGER + '?text=' + encodeURIComponent(text) + '">gửi qua Messenger</a> (đã soạn sẵn).';
        });
    });
  });
})();
