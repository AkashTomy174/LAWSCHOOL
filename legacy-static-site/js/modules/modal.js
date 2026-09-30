/* ==========================================================================
   MODULE: Enrollment Modal & Form Handler
   ========================================================================== */

export function initEnrollmentModal() {
  const modal = document.getElementById('enroll-modal');
  const triggers = document.querySelectorAll('.open-enroll-modal');
  const closeBtn = document.getElementById('enroll-modal-close');
  const form = document.getElementById('enrollment-form');
  const successBox = document.getElementById('enroll-success-box');

  const openModal = (courseName) => {
    const selectElem = document.getElementById('form-course-select');
    if (courseName && selectElem) {
      let found = false;
      for (let i = 0; i < selectElem.options.length; i++) {
        if (selectElem.options[i].value === courseName || selectElem.options[i].text.toLowerCase().includes(courseName.toLowerCase()) || courseName.toLowerCase().includes(selectElem.options[i].value.toLowerCase())) {
          selectElem.selectedIndex = i;
          found = true;
          break;
        }
      }
      if (!found) selectElem.value = courseName;
    }
    if (modal) {
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  };

  const closeModal = () => {
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
  };

  triggers.forEach(trig => {
    trig.addEventListener('click', (e) => {
      e.preventDefault();
      const courseName = trig.getAttribute('data-course');
      openModal(courseName);
    });
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', closeModal);
  }

  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      form.style.display = 'none';
      if (successBox) {
        successBox.style.display = 'block';
        const randomRegId = 'ILS-' + Math.floor(100000 + Math.random() * 900000);
        const regDisplay = document.getElementById('reg-id-display');
        if (regDisplay) regDisplay.textContent = randomRegId;
      }
    });
  }
}

export function initNavbarScroll() {
  const navbar = document.querySelector('.navbar');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 40) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  });

  const mobileBtn = document.getElementById('mobile-toggle');
  const mobileCloseBtn = document.getElementById('mobile-close-btn');
  const navLinks = document.getElementById('nav-menu-links');
  const mobileOverlay = document.getElementById('mobile-overlay');

  const openMobileMenu = () => {
    if (navLinks) navLinks.classList.add('active-mobile');
    if (mobileOverlay) mobileOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  };

  const closeMobileMenu = () => {
    if (navLinks) navLinks.classList.remove('active-mobile');
    if (mobileOverlay) mobileOverlay.classList.remove('active');
    document.body.style.overflow = '';
  };

  if (mobileBtn) {
    mobileBtn.addEventListener('click', () => {
      if (navLinks && navLinks.classList.contains('active-mobile')) {
        closeMobileMenu();
      } else {
        openMobileMenu();
      }
    });
  }

  if (mobileCloseBtn) {
    mobileCloseBtn.addEventListener('click', closeMobileMenu);
  }

  if (mobileOverlay) {
    mobileOverlay.addEventListener('click', closeMobileMenu);
  }

  // Close mobile drawer when clicking any link
  const links = navLinks ? navLinks.querySelectorAll('a') : [];
  links.forEach(link => {
    link.addEventListener('click', closeMobileMenu);
  });
}

