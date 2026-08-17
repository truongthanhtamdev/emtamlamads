// ============================================================
// Em Tâm Làm Ads — shared site behaviour (every page loads this)
// ============================================================

// Scroll progress bar
(function(){
  var progressBar = document.getElementById('progressBar');
  if(!progressBar) return;
  function updateProgress(){
    var h = document.documentElement;
    var scrolled = h.scrollTop;
    var height = h.scrollHeight - h.clientHeight;
    progressBar.style.width = (height > 0 ? (scrolled / height) * 100 : 0) + '%';
  }
  document.addEventListener('scroll', updateProgress, { passive:true });
  updateProgress();
})();

// Mobile menu toggle
(function(){
  var navToggle = document.getElementById('navToggle');
  var mobileMenu = document.getElementById('mobileMenu');
  if(!navToggle || !mobileMenu) return;
  navToggle.addEventListener('click', function(){
    var open = mobileMenu.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  mobileMenu.querySelectorAll('a').forEach(function(a){
    a.addEventListener('click', function(){
      mobileMenu.classList.remove('is-open');
      navToggle.setAttribute('aria-expanded', 'false');
    });
  });
})();

// Scroll reveal + count-up numbers
(function(){
  var revealEls = document.querySelectorAll('.reveal, .clip-reveal');
  if(!revealEls.length) return;
  function animateCounts(root){
    root.querySelectorAll('[data-count]').forEach(function(el){
      var target = parseFloat(el.getAttribute('data-count'));
      var suffix = el.getAttribute('data-suffix') || '';
      var dur = 1400, start = null;
      function step(ts){
        if(!start) start = ts;
        var p = Math.min((ts - start) / dur, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        var val = Math.round(target * eased);
        el.innerHTML = suffix ? (val + '<span class="u">' + suffix + '</span>') : val;
        if(p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }
  if('IntersectionObserver' in window){
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if(entry.isIntersecting){
          entry.target.classList.add('is-visible');
          animateCounts(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -60px 0px' });
    revealEls.forEach(function(el){ io.observe(el); });
  } else {
    revealEls.forEach(function(el){ el.classList.add('is-visible'); animateCounts(el); });
  }
})();

// Header: solidify + shrink slightly once the page scrolls
(function(){
  var siteHeader = document.querySelector('header.site');
  if(!siteHeader) return;
  function updateHeaderState(){
    siteHeader.classList.toggle('is-scrolled', window.scrollY > 40);
  }
  document.addEventListener('scroll', updateHeaderState, { passive:true });
  updateHeaderState();
})();

// Real-photo frames: if the <img> loaded successfully, drop the "empty" fallback state
(function(){
  document.querySelectorAll('.ph-frame img, .badge-card .photo img').forEach(function(img){
    img.addEventListener('load', function(){
      img.closest('.ph-empty') && img.closest('.ph-empty').classList.remove('ph-empty');
    });
  });
})();

// Mark the current page's nav link(s) as active based on <body data-page="...">
(function(){
  var page = document.body.getAttribute('data-page');
  if(!page) return;
  document.querySelectorAll('nav a[data-page]').forEach(function(a){
    if(a.getAttribute('data-page') === page) a.classList.add('is-current');
  });
})();
