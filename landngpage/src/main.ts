/**
 * Infraestructura de IA - Vanilla JS Client Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  const video = document.getElementById('hero-background-video') as HTMLVideoElement | null;
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
