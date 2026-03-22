/* ============================================= */
/* deadweight — frontend interactions              */
/* ============================================= */

(function () {
  'use strict';

  // -----------------------------------------
  // 1. NAV: scroll state + mobile toggle
  // -----------------------------------------

  const nav = document.getElementById('nav');
  const toggle = document.getElementById('nav-toggle');
  const mobileMenu = document.getElementById('nav-mobile');

  let lastScroll = 0;
  window.addEventListener('scroll', () => {
    const y = window.scrollY;
    nav.classList.toggle('scrolled', y > 40);
    lastScroll = y;
  }, { passive: true });

  if (toggle && mobileMenu) {
    toggle.addEventListener('click', () => {
      mobileMenu.classList.toggle('open');
      toggle.setAttribute('aria-expanded', mobileMenu.classList.contains('open'));
    });

    // Close on link click
    mobileMenu.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => mobileMenu.classList.remove('open'));
    });
  }

  // -----------------------------------------
  // 2. HERO TERMINAL: staggered reveal
  // -----------------------------------------

  function animateTerminal() {
    const lines = document.querySelectorAll('.terminal-line');
    lines.forEach(line => {
      const delay = parseInt(line.dataset.delay || '0', 10);
      setTimeout(() => line.classList.add('visible'), delay);
    });
  }

  // Start terminal animation when hero is visible
  const heroTerminal = document.getElementById('hero-terminal');
  if (heroTerminal) {
    const termObs = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateTerminal();
          termObs.disconnect();
        }
      });
    }, { threshold: 0.2 });
    termObs.observe(heroTerminal);
  }

  // -----------------------------------------
  // 3. SCROLL REVEAL: sections fade in
  // -----------------------------------------

  const reveals = document.querySelectorAll('.reveal');
  if (reveals.length > 0) {
    const revealObs = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          // Stagger children if they exist
          const children = entry.target.querySelectorAll('.reveal');
          if (children.length > 0) {
            children.forEach((child, i) => {
              setTimeout(() => child.classList.add('visible'), i * 100);
            });
          }
          entry.target.classList.add('visible');
          revealObs.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -60px 0px'
    });

    reveals.forEach(el => revealObs.observe(el));
  }

  // -----------------------------------------
  // 4. STAT COUNTERS: animate on reveal
  // -----------------------------------------

  function animateCounter(el) {
    const target = parseFloat(el.dataset.target);
    const suffix = el.dataset.suffix || '';
    const isFloat = target % 1 !== 0;
    const duration = 1200;
    const start = performance.now();

    function tick(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = eased * target;

      if (isFloat) {
        el.textContent = current.toFixed(1) + suffix;
      } else {
        el.textContent = Math.round(current) + suffix;
      }

      if (progress < 1) {
        requestAnimationFrame(tick);
      }
    }

    requestAnimationFrame(tick);
  }

  const statNums = document.querySelectorAll('.stat-num[data-target]');
  if (statNums.length > 0) {
    const statObs = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          statObs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });

    statNums.forEach(el => statObs.observe(el));
  }

  // -----------------------------------------
  // 5. COPY BUTTONS
  // -----------------------------------------

  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const text = btn.dataset.copy;
      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
        btn.classList.add('copied');
        const original = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => {
          btn.classList.remove('copied');
          btn.textContent = original;
        }, 1800);
      } catch {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1800);
      }
    });
  });

  // -----------------------------------------
  // 6. SMOOTH ANCHOR SCROLL (offset for nav)
  // -----------------------------------------

  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', (e) => {
      const id = a.getAttribute('href');
      if (id === '#') return;
      const target = document.querySelector(id);
      if (!target) return;
      e.preventDefault();
      const offset = 70;
      const top = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top, behavior: 'smooth' });
    });
  });

})();
