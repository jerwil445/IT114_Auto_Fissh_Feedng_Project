/**
 * Infraestructura de IA - Vanilla JS Client Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  const video = document.getElementById('hero-background-video');
  const heroSection = document.getElementById('hero-section');
  const mobileToggle = document.getElementById('mobile-menu-toggle');
  const mobileMenu = document.getElementById('mobile-nav-drawer');

  // 1. Reduced Motion Detection
  const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

  const applyMotionPreference = () => {
    if (!video) return;
    if (reducedMotionQuery.matches) {
      video.pause();
    } else if (video.paused && !document.hidden) {
      video.play().catch(() => {
        // Autoplay may be restricted
      });
    }
  };

  applyMotionPreference();
  reducedMotionQuery.addEventListener('change', applyMotionPreference);

  // 2. Pause video when out of viewport using IntersectionObserver
  if (video && heroSection && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            video.pause();
          } else if (!reducedMotionQuery.matches) {
            video.play().catch(() => {
              // Ignore play interruptions
            });
          }
        });
      },
      { threshold: 0.1 }
    );

    observer.observe(heroSection);
  }

  // 3. Mobile Navigation Toggle
  if (mobileToggle && mobileMenu) {
    mobileToggle.addEventListener('click', () => {
      const isOpen = mobileMenu.classList.toggle('is-open');
      mobileToggle.setAttribute('aria-expanded', String(isOpen));
    });

    // Close mobile menu when clicking any nav link
    const mobileLinks = mobileMenu.querySelectorAll('.nav-link');
    mobileLinks.forEach((link) => {
      link.addEventListener('click', () => {
        mobileMenu.classList.remove('is-open');
        mobileToggle.setAttribute('aria-expanded', 'false');
      });
    });

    // Close on Escape key
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && mobileMenu.classList.contains('is-open')) {
        mobileMenu.classList.remove('is-open');
        mobileToggle.setAttribute('aria-expanded', 'false');
      }
    });
  }
});

// Account forms share a native dialog for keyboard focus and Escape support.
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('auth-modal');
  const errorBox = document.getElementById('auth-error');
  let busy = false;
  const token = document.querySelector('meta[name="csrf-token"]');
  function showError(message) { errorBox.textContent = message; errorBox.hidden = false; }
  function selectForm(mode) {
    if (busy) return;
    const registering = mode === 'register';
    document.getElementById('login-form').hidden = registering;
    document.getElementById('register-form').hidden = !registering;
    document.getElementById('auth-title').textContent = registering ? 'Start your daily routine' : 'Welcome back';
    document.getElementById('auth-description').textContent = registering ? 'Create your AquaFeed account.' : 'Log in to manage your feeder.';
    modal.querySelectorAll('.auth-tabs button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.authTab === mode)));
    errorBox.hidden = true;
    if (modal.open) document.getElementById(registering ? 'register-name' : 'login-email').focus();
  }
  function openModal(mode) {
    selectForm(mode);
    if (!modal.open) modal.showModal();
    document.getElementById(mode === 'register' ? 'register-name' : 'login-email').focus();
  }
  document.querySelectorAll('[data-auth]').forEach(button => button.addEventListener('click', () => openModal(button.dataset.auth)));
  modal.querySelectorAll('[data-auth-tab]').forEach(button => button.addEventListener('click', () => selectForm(button.dataset.authTab)));
  document.getElementById('auth-close').addEventListener('click', () => { if (!busy) modal.close(); });
  modal.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  modal.addEventListener('click', event => {
    const rect = modal.getBoundingClientRect();
    if (!busy && event.target === modal && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) modal.close();
  });
  modal.addEventListener('close', () => {
    modal.querySelectorAll('input[name*="password"]').forEach(input => { input.value = ''; input.type = 'password'; });
    modal.querySelectorAll('[data-password]').forEach(button => { button.textContent = 'Show'; button.setAttribute('aria-pressed', 'false'); button.setAttribute('aria-label', 'Show password'); });
    errorBox.hidden = true;
  });
  modal.querySelectorAll('[data-password]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.password);
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.textContent = visible ? 'Hide' : 'Show';
    button.setAttribute('aria-pressed', String(visible));
    button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
  }));
  ['login', 'register'].forEach(mode => {
    const form = document.getElementById(`${mode}-form`);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy || !form.reportValidity()) return;
      const data = Object.fromEntries(new FormData(form));
      if (mode === 'register' && data.password !== data.confirm_password) { showError('Passwords do not match.'); document.getElementById('register-confirm').focus(); return; }
      busy = true;
      errorBox.hidden = true;
      const submit = form.querySelector('[type="submit"]');
      const label = submit.textContent;
      modal.querySelectorAll('button').forEach(button => button.disabled = true);
      submit.textContent = mode === 'login' ? 'Logging in…' : 'Creating account…';
      try {
        // Refresh the token in case another browser tab changed the session.
        const sessionResponse = await fetch('/api/auth/session', {cache:'no-store', signal:AbortSignal.timeout(12000)});
        if (!sessionResponse.ok) throw new Error('Cannot reach the server. Please try again.');
        const session = await sessionResponse.json();
        token.content = session.csrf_token;
        const response = await fetch(`/api/auth/${mode}`, {method:'POST', headers:{'Content-Type':'application/json', 'X-CSRF-Token':token.content}, body:JSON.stringify(data), signal:AbortSignal.timeout(12000)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.message || 'Please try again.');
        window.location.assign('/dashboard');
      } catch (error) {
        showError(error.name === 'TimeoutError' || error instanceof TypeError ? 'Cannot reach the server. Please try again.' : error.message);
      } finally {
        busy = false;
        submit.textContent = label;
        modal.querySelectorAll('button').forEach(button => button.disabled = false);
      }
    });
  });
  const initial = new URLSearchParams(window.location.search).get('auth');
  if (initial === 'login' || initial === 'register') openModal(initial);
});
