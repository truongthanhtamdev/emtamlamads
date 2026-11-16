/* Trợ lý AI tư vấn & đặt lịch — Em Tâm Làm Ads
   Khung chat nổi góc phải. Chỉ hiện khi trang quản trị đã bật AI (có khoá Claude API).
   Nút bất kỳ có thuộc tính data-ai-open="câu hỏi" sẽ mở khung chat và gửi sẵn câu đó. */
(function(){
  'use strict';
  var API = 'https://admin.emtamlamads.com/api/chat';
  var MESS = 'https://m.me/emtamlamads';
  var me = document.currentScript && document.currentScript.src || '';
  var BASE = me ? me.replace(/ai-chat\.js.*$/, '') : '/assets/';
  var path = location.pathname;
  var store = {
    get:function(k){ try{ return JSON.parse(sessionStorage.getItem(k)); }catch(e){ return null; } },
    set:function(k,v){ try{ sessionStorage.setItem(k, JSON.stringify(v)); }catch(e){} }
  };

  var CHIPS = {
    quaychupdung: ['Mình muốn học thử Quay · Chụp & Dựng', 'Học bằng điện thoại được không?', 'Combo 2 khoá gồm gì?'],
    khoaads:      ['Khoá Ads học những gì?', 'Mình chưa chạy ads bao giờ, học được không?', 'Combo 3 khoá giá bao nhiêu?'],
    lamwebsite:   ['Không biết code có học được không?', 'Học xong làm được web gì?', 'Combo 3 khoá gồm gì?'],
    quangcao:     ['Chạy ads mãi mà ít khách, sai ở đâu?', 'Mình bán thời trang, nên chạy ads thế nào?', 'Gói vận hành 7,5 triệu gồm gì?', 'Đặt lịch tư vấn 1:1'],
    home:         ['Shop mình ít khách, nên làm gì?', 'Mình bán thời trang', 'Mình làm spa – làm đẹp', 'Mình muốn tự học làm video & ads']
  };
  var seg = (path.split('/')[1] || 'home');
  var chips = CHIPS[seg] || CHIPS.home;
  var HELLO = 'Chào anh/chị 👋 Em là trợ lý AI của Em Tâm Làm Ads. Anh/chị đang kinh doanh gì ạ? Em gợi ý chiến lược content – quay dựng – quảng cáo để có thêm khách, và đặt lịch với Tâm nếu cần.';

  function sid(){
    var s = store.get('etla_ai_sid');
    if(!s){
      var a = new Uint8Array(16); (window.crypto || window.msCrypto).getRandomValues(a);
      s = Array.prototype.map.call(a, function(b){ return ('0' + b.toString(16)).slice(-2); }).join('');
      store.set('etla_ai_sid', s);
    }
    return s;
  }

  function esc(s){ return String(s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function fmt(t){
    var h = esc(t);
    h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    h = h.replace(/(^|\s)(m\.me\/emtamlamads)/g, '$1<a href="' + MESS + '" target="_blank" rel="noopener">$2</a>');
    h = h.replace(/(0965[ .]?817[ .]?021)/g, '<a href="tel:0965817021">$1</a>');
    h = h.replace(/^\s*[-•]\s+/gm, '• ');
    return h.replace(/\n/g, '<br>');
  }

  var CSS = '' +
  '.ai-launch{position:fixed;right:1.1rem;bottom:1.1rem;z-index:95;display:flex;align-items:center;gap:.55rem;padding:.4rem .95rem .4rem .4rem;border-radius:999px;border:1px solid rgba(214,179,44,.55);background:#14171A;color:#F5F2E9;font:600 .92rem/1.2 "Be Vietnam Pro",system-ui,sans-serif;box-shadow:0 14px 34px rgba(0,0,0,.45);cursor:pointer;transition:transform .2s}' +
  '.ai-launch:hover{transform:translateY(-2px)}' +
  '.ai-launch img{width:40px;height:40px;border-radius:50%;object-fit:cover;background:#D6B32C}' +
  '.ai-launch small{display:block;font-weight:500;font-size:.74rem;color:#D6B32C}' +
  '.ai-launch .ai-dot{position:absolute;left:34px;top:6px;width:10px;height:10px;border-radius:50%;background:#3DDC84;border:2px solid #14171A}' +
  '.ai-tease{position:fixed;right:1.1rem;bottom:5.4rem;z-index:95;max-width:270px;padding:.8rem 2rem .8rem .9rem;border-radius:14px 14px 4px 14px;background:#F5F2E9;color:#15171A;font:500 .88rem/1.45 "Be Vietnam Pro",system-ui,sans-serif;box-shadow:0 14px 34px rgba(0,0,0,.4);cursor:pointer;animation:ai-up .35s ease}' +
  '.ai-tease button{position:absolute;right:.35rem;top:.3rem;border:0;background:none;font-size:1.1rem;color:#666;cursor:pointer;padding:.2rem .4rem}' +
  '.ai-box{position:fixed;right:1.1rem;bottom:1.1rem;z-index:100;width:380px;height:min(600px,calc(100vh - 2.2rem));display:none;flex-direction:column;border-radius:18px;overflow:hidden;background:#0F1113;color:#F5F2E9;border:1px solid rgba(214,179,44,.35);box-shadow:0 24px 60px rgba(0,0,0,.6);font:400 .93rem/1.5 "Be Vietnam Pro",system-ui,sans-serif;animation:ai-up .25s ease}' +
  '.ai-box.open{display:flex}' +
  '.ai-head{display:flex;align-items:center;gap:.6rem;padding:.75rem .9rem;background:#16191C;border-bottom:1px solid rgba(245,241,231,.1)}' +
  '.ai-head img{width:38px;height:38px;border-radius:50%;object-fit:cover;background:#D6B32C}' +
  '.ai-head b{display:block;font-size:.95rem}.ai-head span{font-size:.75rem;color:#9FD8AE}' +
  '.ai-head .ai-x{margin-left:auto;border:0;background:none;color:#C9C4B6;font-size:1.5rem;line-height:1;cursor:pointer;padding:.2rem .45rem}' +
  '.ai-log{flex:1;overflow-y:auto;padding:.9rem;display:flex;flex-direction:column;gap:.55rem;overscroll-behavior:contain}' +
  '.ai-m{max-width:86%;padding:.6rem .8rem;border-radius:14px;word-wrap:break-word}' +
  '.ai-m a{color:inherit;text-decoration:underline}' +
  '.ai-m.bot{align-self:flex-start;background:#1C2024;border-bottom-left-radius:4px}' +
  '.ai-m.me{align-self:flex-end;background:#D6B32C;color:#15171A;border-bottom-right-radius:4px}' +
  '.ai-m.ok{align-self:stretch;max-width:none;background:#13261C;color:#BFF0CB;border:1px solid #2F6B43}' +
  '.ai-typing{align-self:flex-start;padding:.7rem .9rem;background:#1C2024;border-radius:14px;display:flex;gap:4px}' +
  '.ai-typing i{width:7px;height:7px;border-radius:50%;background:#C9C4B6;animation:ai-b 1s infinite}' +
  '.ai-typing i:nth-child(2){animation-delay:.15s}.ai-typing i:nth-child(3){animation-delay:.3s}' +
  '.ai-chips{display:flex;flex-wrap:wrap;gap:.4rem;padding:0 .9rem .6rem}' +
  '.ai-chips button{border:1px solid rgba(214,179,44,.5);background:transparent;color:#F0D66B;border-radius:999px;padding:.35rem .7rem;font:500 .8rem/1.3 "Be Vietnam Pro",system-ui,sans-serif;cursor:pointer}' +
  '.ai-chips button:hover{background:rgba(214,179,44,.12)}' +
  '.ai-form{display:flex;gap:.45rem;padding:.65rem;border-top:1px solid rgba(245,241,231,.1);background:#16191C}' +
  '.ai-form textarea{flex:1;resize:none;min-height:42px;max-height:110px;padding:.6rem .75rem;border-radius:12px;border:1px solid rgba(245,241,231,.2);background:#0F1113;color:#F5F2E9;font:400 16px/1.4 "Be Vietnam Pro",system-ui,sans-serif}' +
  '.ai-form textarea:focus{outline:none;border-color:#D6B32C}' +
  '.ai-form button{flex:none;width:44px;border:0;border-radius:12px;background:#D6B32C;color:#15171A;font-size:1.2rem;cursor:pointer}' +
  '.ai-form button:disabled{opacity:.5;cursor:default}' +
  '.ai-foot{padding:0 .9rem .55rem;background:#16191C;font-size:.7rem;color:#8E897D;text-align:center}' +
  '.ai-foot a{color:#C9C4B6}' +
  '@keyframes ai-b{0%,60%,100%{opacity:.3;transform:none}30%{opacity:1;transform:translateY(-3px)}}' +
  '@keyframes ai-up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}' +
  '@media(max-width:640px){.ai-launch{bottom:calc(5rem + env(safe-area-inset-bottom));right:.75rem;padding:.3rem .8rem .3rem .3rem;font-size:.85rem}.ai-launch img{width:36px;height:36px}' +
  '.ai-tease{bottom:calc(9rem + env(safe-area-inset-bottom));right:.75rem}' +
  '.ai-box{inset:0;width:auto;height:auto;border-radius:0;border:0;bottom:0;right:0}' +
  '.ai-form{padding-bottom:calc(.65rem + env(safe-area-inset-bottom))}}' +
  '@media(prefers-reduced-motion:reduce){.ai-box,.ai-tease{animation:none}.ai-typing i{animation:none}}';

  var el = {}, history = store.get('etla_ai_log') || [], busy = false, built = false, booked = !!store.get('etla_ai_booked');

  function build(){
    if(built) return; built = true;
    var st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    var av = BASE + 'em-tam-avatar.webp';

    el.launch = document.createElement('button');
    el.launch.type = 'button'; el.launch.className = 'ai-launch';
    el.launch.setAttribute('aria-label', 'Mở trợ lý AI tư vấn và đặt lịch');
    el.launch.innerHTML = '<img src="' + av + '" alt="" width="40" height="40"><span class="ai-dot"></span><span>Tư vấn AI<small>Đặt lịch trong 1 phút</small></span>';
    el.launch.onclick = function(){ open(); };

    el.box = document.createElement('div');
    el.box.className = 'ai-box'; el.box.setAttribute('role', 'dialog'); el.box.setAttribute('aria-label', 'Trợ lý AI Em Tâm Làm Ads');
    el.box.innerHTML =
      '<div class="ai-head"><img src="' + av + '" alt="" width="38" height="38"><div><b>Trợ lý Em Tâm</b><span>● AI tư vấn & đặt lịch · trả lời ngay</span></div>' +
      '<button type="button" class="ai-x" aria-label="Đóng">×</button></div>' +
      '<div class="ai-log" aria-live="polite"></div>' +
      '<div class="ai-chips"></div>' +
      '<form class="ai-form"><textarea rows="1" placeholder="Nhập tin nhắn…" aria-label="Tin nhắn" maxlength="1000"></textarea><button type="submit" aria-label="Gửi">➤</button></form>' +
      '<div class="ai-foot">Trợ lý AI có thể nhầm — giá & lịch được Tâm xác nhận lại. Muốn gặp người thật? <a href="' + MESS + '" target="_blank" rel="noopener">Messenger</a></div>';
    el.log = el.box.querySelector('.ai-log');
    el.chips = el.box.querySelector('.ai-chips');
    el.form = el.box.querySelector('.ai-form');
    el.input = el.form.querySelector('textarea');
    el.send = el.form.querySelector('button');
    el.box.querySelector('.ai-x').onclick = close;
    el.form.onsubmit = function(e){ e.preventDefault(); send(el.input.value); };
    el.input.addEventListener('keydown', function(e){
      if(e.key === 'Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); send(el.input.value); }
    });
    el.input.addEventListener('input', function(){ el.input.style.height = 'auto'; el.input.style.height = Math.min(el.input.scrollHeight, 110) + 'px'; });
    document.addEventListener('keydown', function(e){ if(e.key === 'Escape' && el.box.classList.contains('open')) close(); });

    document.body.appendChild(el.launch);
    document.body.appendChild(el.box);
    render();

    if(!store.get('etla_ai_teased') && !history.length){
      setTimeout(function(){
        if(el.box.classList.contains('open') || store.get('etla_ai_teased')) return;
        store.set('etla_ai_teased', 1);
        var t = document.createElement('div'); t.className = 'ai-tease';
        t.innerHTML = 'Anh/chị đang bán gì ạ? Em gợi ý gói phù hợp & đặt lịch tư vấn miễn phí 👋<button type="button" aria-label="Ẩn">×</button>';
        t.onclick = function(e){ t.remove(); if(e.target.tagName !== 'BUTTON') open(); };
        document.body.appendChild(t); el.tease = t;
      }, 12000);
    }
  }

  function add(role, text, save){
    var d = document.createElement('div');
    d.className = 'ai-m ' + role;
    d.innerHTML = fmt(text);
    el.log.appendChild(d);
    el.log.scrollTop = el.log.scrollHeight;
    if(save !== false){ history.push([role, text]); store.set('etla_ai_log', history.slice(-60)); }
  }

  function render(){
    el.log.innerHTML = '';
    add('bot', HELLO, false);
    history.forEach(function(h){ add(h[0], h[1], false); });
    showChips();
  }

  function showChips(){
    el.chips.innerHTML = '';
    if(history.length) return;
    chips.forEach(function(c){
      var b = document.createElement('button'); b.type = 'button'; b.textContent = c;
      b.onclick = function(){ send(c); };
      el.chips.appendChild(b);
    });
  }

  function open(q){
    build();
    if(el.tease) el.tease.remove();
    el.box.classList.add('open');
    el.launch.style.display = 'none';
    if(window.matchMedia('(max-width:640px)').matches) document.documentElement.style.overflow = 'hidden';
    if(q) send(q); else setTimeout(function(){ el.input.focus(); }, 50);
    track('ai_chat_open');
  }
  function close(){
    el.box.classList.remove('open');
    el.launch.style.display = '';
    document.documentElement.style.overflow = '';
  }

  function track(ev, extra){
    try{ if(window.gtag) gtag('event', ev, extra || {}); }catch(e){}
  }

  function offline(){
    add('bot', 'Xin lỗi, trợ lý đang bận một chút 🙏 Anh/chị nhắn Messenger m.me/emtamlamads hoặc gọi/Zalo 0965 817 021 — Tâm trả lời ngay ạ.');
  }

  function send(text){
    text = String(text || '').trim();
    if(!text || busy) return;
    busy = true; el.send.disabled = true;
    el.input.value = ''; el.input.style.height = '';
    el.chips.innerHTML = '';
    add('me', text);
    var typing = document.createElement('div'); typing.className = 'ai-typing'; typing.innerHTML = '<i></i><i></i><i></i>';
    el.log.appendChild(typing); el.log.scrollTop = el.log.scrollHeight;
    var done = function(){ typing.remove(); busy = false; el.send.disabled = false; el.input.focus(); };

    fetch(API, { method:'POST', headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ sid: sid(), text: text, page: path + location.search }) })
      .then(function(r){ return r.json().catch(function(){ return { ok:false }; }).then(function(j){ j.status = r.status; return j; }); })
      .then(function(j){
        done();
        if(j.ok && j.reply){
          add('bot', j.reply);
          if(j.booked_now && !booked){
            booked = true; store.set('etla_ai_booked', 1);
            add('ok', '✅ Đã giữ lịch! Tâm sẽ liên hệ xác nhận trước giờ hẹn. Cần đổi giờ cứ nhắn em hoặc Messenger nhé.');
            try{ if(window.fbq) fbq('track', 'Lead', { content_name:'AI tư vấn' }); }catch(e){}
            track('generate_lead', { method:'ai_chat' });
          }
        } else if(j.status === 429 && j.error){
          add('bot', j.error);
        } else {
          offline();
        }
      })
      .catch(function(){ done(); offline(); });
  }

  function init(){
    document.addEventListener('click', function(e){
      var t = e.target.closest && e.target.closest('[data-ai-open]');
      if(t && built){ e.preventDefault(); open(t.getAttribute('data-ai-open') || ''); }
    });
    fetch(API + '/status').then(function(r){ return r.json(); }).then(function(j){
      if(!j || !j.on) return;
      document.documentElement.classList.add('ai-on');
      build();
    }).catch(function(){});
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
