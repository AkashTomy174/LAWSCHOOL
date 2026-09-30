/* ==========================================================================
   MODULE: SPA Hash Router & Standalone Full Landing Page Renderer
   ========================================================================== */

import { COURSE_DATA } from '../course-data.js?v=5.0';
import { BLOG_POSTS } from '../blog-data.js?v=5.0';

export function initRouter() {
  const mainView = document.getElementById('main-landing-view');
  const courseView = document.getElementById('course-landing-view');
  const blogView = document.getElementById('blog-article-view');

  const handleRoute = () => {
    const hash = window.location.hash || '';

    // Course Page Routing (#course/klee, #course/super-batch, #course/open-merit, #course/mastery, etc.)
    if (hash.startsWith('#course/')) {
      const courseId = hash.replace('#course/', '').trim();
      let data = COURSE_DATA[courseId];

      if (courseView) {
        if (mainView) mainView.style.display = 'none';
        if (blogView) blogView.style.display = 'none';
        courseView.style.display = 'block';

        if (courseId === 'super-batch') {
          renderSuperBatchLandingPage(COURSE_DATA.klee, courseView);
          updateNavbarState('course', 'KLEE 2027 Super Batch Syndicate');
        } else if (courseId === 'open-merit' || courseId === 'pay-on-result') {
          renderOpenMeritLandingPage(COURSE_DATA.klee, courseView);
          updateNavbarState('course', 'KLEE 2027 Open Merit Syndicate');
        } else if (data && data.id === 'klee') {
          renderKleeLandingPage(data, courseView);
          updateNavbarState('course', data.title);
        } else if (data) {
          renderCourseLandingPage(data, courseView);
          updateNavbarState('course', data.title);
        } else {
          // Fallback to KLEE hub page
          renderKleeLandingPage(COURSE_DATA.klee, courseView);
          updateNavbarState('course', COURSE_DATA.klee.title);
        }
        window.scrollTo({ top: 0, behavior: 'instant' });
        return;
      }
    }

    // Blog Article Routing (#blog/post-id)
    if (hash.startsWith('#blog/')) {
      const blogId = hash.replace('#blog/', '').trim();
      const post = BLOG_POSTS.find(p => p.id === blogId);
      if (post && blogView) {
        if (mainView) mainView.style.display = 'none';
        if (courseView) courseView.style.display = 'none';
        blogView.style.display = 'block';
        renderBlogArticlePage(post, blogView);
        window.scrollTo({ top: 0, behavior: 'instant' });
        updateNavbarState('blog', post.title);
        return;
      }
    }

    // Default: Main Landing Page View
    if (courseView) courseView.style.display = 'none';
    if (blogView) blogView.style.display = 'none';
    if (mainView) mainView.style.display = 'block';
    updateNavbarState('home');

    // If anchor exists on main page (e.g. #courses, #commitment, #knowledge-hub), scroll smoothly to it
    if (hash && hash !== '#' && hash !== '#home') {
      const targetElem = document.querySelector(hash);
      if (targetElem) {
        setTimeout(() => {
          targetElem.scrollIntoView({ behavior: 'smooth' });
        }, 80);
      }
    }
  };

  window.addEventListener('hashchange', handleRoute);
  window.addEventListener('DOMContentLoaded', handleRoute);
  
  // Expose global course navigator for easy inline triggers
  window.navigateToCourse = (courseId) => {
    window.location.hash = `#course/${courseId}`;
  };

  window.navigateToBlog = (blogId) => {
    window.location.hash = `#blog/${blogId}`;
  };

  // Run initial route check
  handleRoute();
}

function updateNavbarState(type, title = '') {
  const backNavBtn = document.getElementById('nav-back-button');

  if (!backNavBtn) return;

  if (type === 'course' || type === 'blog') {
    backNavBtn.style.display = 'inline-flex';
    backNavBtn.innerHTML = `<i class="fa-solid fa-arrow-left"></i> Main Platform`;
  } else {
    backNavBtn.style.display = 'none';
  }
}

function renderSuperBatchLandingPage(data, container) {
  let html = `
    <div class="standalone-landing-wrapper">
      
      <!-- Sub-Header Breadcrumb Bar -->
      <div class="landing-subhead-bar">
        <div class="container" style="display: flex; justify-content: space-between; align-items: center; padding: 0.85rem 0;">
          <div class="breadcrumb-box">
            <a href="#home" class="breadcrumb-link"><i class="fa-solid fa-house"></i> Home</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#courses" class="breadcrumb-link">Courses</a>
            <span class="breadcrumb-sep">/</span>
            <span class="breadcrumb-active">KLEE 2027 Super Batch Syndicate</span>
          </div>
          <a href="#home" class="btn btn-glass btn-sm">
            <i class="fa-solid fa-arrow-left"></i> Back to Main Platform
          </a>
        </div>
      </div>

      <!-- Hero Section -->
      <section class="standalone-hero">
        <div class="container">
          <div class="standalone-hero-grid">
            <div class="standalone-hero-main">
              <div class="ticker-badge pulse-badge-glow" style="margin-bottom: 1rem;">
                <span class="pulse-dot"></span>
                <span class="ticker-text">STRICTLY 15 CANDIDATES PER BATCH • 100% MONEY-BACK GUARANTEE</span>
              </div>

              <p style="color: var(--gold-light); font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; font-size: 0.85rem; margin-bottom: 0.5rem;">
                TRACK 01: THE ULTRA-HIGH ACCOUNTABILITY 1-ON-1 ACCELERATOR
              </p>

              <h1 class="standalone-hero-title" style="font-size: 2.3rem; line-height: 1.25;">
                KLEE 2027 Super Batch Syndicate
              </h1>

              <p class="standalone-hero-subtitle" style="margin-top: 1rem; color: var(--white-bright); font-size: 1.05rem; line-height: 1.6;">
                Engineered for candidates demanding 100% financial protection and relentless personal 1-on-1 ranker accountability. Taught exclusively by state top rank holders from GLC Ernakulam.
              </p>

              <!-- Social Proof Chips -->
              <div class="social-proof-strip-wrapper">
                <span class="social-proof-chip"><i class="fa-solid fa-shield-halved" style="color: var(--gold-primary);"></i> 100% Full Refund Guarantee</span>
                <span class="social-proof-chip"><i class="fa-solid fa-user-gear" style="color: var(--gold-primary);"></i> Weekly 1-on-1 Mentor Deep-Dive</span>
                <span class="social-proof-chip"><i class="fa-solid fa-robot" style="color: var(--gold-primary);"></i> AI Weak-Area Diagnostics</span>
              </div>

              <div class="standalone-cta-group" style="margin-top: 1.75rem; display: flex; gap: 1rem; flex-wrap: wrap;">
                <button class="btn btn-gold btn-lg open-enroll-modal" data-course="KLEE 2027 Super Batch Syndicate">
                  <i class="fa-solid fa-bolt"></i> Apply for Super Batch (₹1L 100% Refundable) &rarr;
                </button>
                <a href="#course/open-merit" class="btn btn-glass btn-lg" style="border-color: var(--gold-border); color: var(--gold-light);">
                  <i class="fa-solid fa-handshake"></i> View Pay-On-Result Open Merit Track &rarr;
                </a>
              </div>
            </div>

            <!-- Hero Side Pricing Card -->
            <div class="standalone-hero-side">
              <div class="standalone-pricing-card tri-border-card" style="border-color: var(--gold-primary);">
                <div class="pricing-card-badge"><i class="fa-solid fa-shield-halved"></i> 100% PROTECTED INVESTMENT</div>
                <h3 class="pricing-summary-text" style="font-size: 1.8rem; color: var(--gold-primary); text-align: center; margin-top: 0.5rem;">
                  ₹1,00,000
                </h3>
                <p style="color: var(--white-muted); font-size: 0.8rem; text-align: center; margin-bottom: 1rem;">
                  (Inclusive of GST — Protected by 100% Admission Commitment)
                </p>
                
                <div class="pricing-details-stack" style="margin: 1rem 0;">
                  <div class="pricing-detail-item">
                    <div class="detail-item-title" style="color: #fff; font-weight: 700;">Cohort Bandwidth</div>
                    <div class="detail-item-note" style="color: var(--gold-light);">Strictly 15 Students per batch</div>
                  </div>
                  <div class="detail-item-note" style="color: var(--white-muted); margin-top: 0.5rem; font-size: 0.85rem; line-height: 1.5;">
                    If you satisfy 90% attendance & mocks but miss a Government Law College merit seat, 100% of your tuition fee is refunded without administrative deductions.
                  </div>
                </div>

                <button class="btn btn-gold open-enroll-modal" data-course="KLEE 2027 Super Batch Syndicate" style="width: 100%;">
                  <i class="fa-solid fa-user-plus"></i> Claim Priority Super Batch Seat &rarr;
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Main Body Container -->
      <div class="container" style="padding-top: 3rem; padding-bottom: 5rem;">

        <!-- Features Deep Dive Card -->
        <div class="standalone-section-card tri-border-card" style="border-color: var(--gold-primary); margin-bottom: 2.5rem;">
          <h2 class="standalone-section-heading">
            <i class="fa-solid fa-star"></i> What Makes The Super Batch Syndicate Unique?
          </h2>
          <div class="detail-grid-2" style="margin-top: 1.5rem;">
            ${data.trackSuperBatch.features.map(f => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--gold-border); background: rgba(0, 0, 0, 0.6);">
                <div style="display: flex; gap: 0.75rem; align-items: flex-start;">
                  <span style="color: var(--gold-primary); font-weight: 800; font-size: 1.2rem;">✓</span>
                  <span style="color: #ffffff; font-size: 0.95rem; line-height: 1.6;">${f}</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Curriculum Architecture -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;">
          <h2 class="standalone-section-heading">
            <i class="fa-solid fa-layer-group"></i> Core Curriculum Architecture
          </h2>
          <div class="detail-grid-2" style="margin-top: 1.5rem;">
            ${data.curriculumArchitecture.map(curr => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--white-border); background: rgba(0, 0, 0, 0.6);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                  <h3 style="color: var(--gold-light); font-size: 1.1rem; margin: 0; font-family: var(--font-serif);">
                    <i class="fa-solid ${curr.icon}" style="color: var(--gold-primary); margin-right: 0.4rem;"></i> ${curr.title}
                  </h3>
                  <span class="subject-badge" style="background: rgba(212, 175, 55, 0.15); color: var(--gold-light); border: 1px solid var(--gold-border); padding: 0.25rem 0.6rem; border-radius: 6px; font-weight: 700; font-size: 0.8rem;">
                    ${curr.marks}
                  </span>
                </div>
                <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">${curr.desc}</p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Side-by-Side Comparison Matrix -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem; border-color: var(--gold-border);">
          <h2 class="standalone-section-heading">
            <i class="fa-solid fa-code-compare"></i> ${data.comparisonTable.headline}
          </h2>
          <p style="color: var(--white-muted); font-size: 0.95rem; margin-bottom: 1.5rem;">
            ${data.comparisonTable.subHeadline}
          </p>

          <div class="syndicate-table-container">
            <table class="syndicate-comparison-table">
              <thead>
                <tr>
                  <th style="width: 25%;">Parameter</th>
                  <th style="width: 37.5%; color: var(--gold-primary);">KLEE 2027 Super Batch</th>
                  <th style="width: 37.5%; color: var(--gold-light);">KLEE 2027 Open Merit</th>
                </tr>
              </thead>
              <tbody>
                ${data.comparisonTable.rows.map(row => `
                  <tr>
                    <td class="param-name">${row.param}</td>
                    <td style="color: #ffffff; font-size: 0.9rem;">${row.superBatch}</td>
                    <td style="color: var(--white-muted); font-size: 0.9rem;">${row.openMerit}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>

        <!-- 4-Step Admission Process -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;">
          <div style="text-align: center; margin-bottom: 1.5rem;">
            <h2 style="font-family: var(--font-serif); font-size: 2rem; color: #ffffff;">
              ${data.admissionProcess.headline}
            </h2>
          </div>
          <div class="admission-process-grid">
            ${data.admissionProcess.steps.map(step => `
              <div class="step-card">
                <span class="step-num-badge">${step.num}</span>
                <div class="step-title">${step.title}</div>
                <p class="step-desc">${step.desc}</p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- FAQs -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;">
          <h2 class="standalone-section-heading"><i class="fa-solid fa-circle-question"></i> Frequently Asked Questions</h2>
          <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1.5rem;">
            ${data.faqs.filter(f => f.q.toLowerCase().includes('super batch') || f.q.toLowerCase().includes('refund')).map(faq => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--white-border); background: rgba(0, 0, 0, 0.6);">
                <h3 style="color: var(--gold-light); font-size: 1.05rem; margin-bottom: 0.5rem; font-family: var(--font-serif);">❓ ${faq.q}</h3>
                <p style="color: var(--white-muted); font-size: 0.9rem; line-height: 1.6; margin: 0;">${faq.a}</p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Final CTA -->
        <div class="standalone-section-card tri-border-card" style="text-align: center; background: radial-gradient(circle at center, rgba(212, 175, 55, 0.2) 0%, rgba(0,0,0,0.95) 100%); padding: 4rem 2rem; border-color: var(--gold-primary);">
          <h2 style="font-family: var(--font-serif); font-size: 2.2rem; color: #fff; margin-bottom: 0.75rem;">
            Back Yourself. We Are Ready to Back You.
          </h2>
          <p style="color: var(--white-muted); max-width: 650px; margin: 0 auto 2rem auto; font-size: 1rem;">
            Strict 15-candidate capacity enforced. Reserve your seat in the Super Batch Syndicate today.
          </p>
          <button class="btn btn-gold btn-lg open-enroll-modal" data-course="KLEE 2027 Super Batch Syndicate">
            <i class="fa-solid fa-bolt"></i> Apply for Super Batch (₹1L 100% Refundable) &rarr;
          </button>
        </div>

      </div>

      <footer style="background: #000; border-top: 1px solid var(--white-border); padding: 2.5rem 0; text-align: center; color: var(--white-muted); font-size: 0.88rem;">
        <div class="container">
          <p>© 2026 Indian Law School (ILS). KLEE 2027 Super Batch Syndicate. Taught Exclusively by GLC Ernakulam Top Rank Holders.</p>
        </div>
      </footer>
    </div>
  `;

  container.innerHTML = html;
  bindModalTriggers(container);
}

function renderOpenMeritLandingPage(data, container) {
  let html = `
    <div class="standalone-landing-wrapper">
      
      <!-- Sub-Header Breadcrumb Bar -->
      <div class="landing-subhead-bar">
        <div class="container" style="display: flex; justify-content: space-between; align-items: center; padding: 0.85rem 0;">
          <div class="breadcrumb-box">
            <a href="#home" class="breadcrumb-link"><i class="fa-solid fa-house"></i> Home</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#courses" class="breadcrumb-link">Courses</a>
            <span class="breadcrumb-sep">/</span>
            <span class="breadcrumb-active">KLEE 2027 Open Merit Syndicate</span>
          </div>
          <a href="#home" class="btn btn-glass btn-sm">
            <i class="fa-solid fa-arrow-left"></i> Back to Main Platform
          </a>
        </div>
      </div>

      <!-- Hero Section -->
      <section class="standalone-hero">
        <div class="container">
          <div class="standalone-hero-grid">
            <div class="standalone-hero-main">
              <div class="ticker-badge pulse-badge-glow" style="margin-bottom: 1rem;">
                <span class="pulse-dot"></span>
                <span class="ticker-text" style="color: var(--gold-light);">ZERO TUITION RISK • PAY FEE ONLY AFTER SELECTION</span>
              </div>

              <p style="color: var(--gold-light); font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; font-size: 0.85rem; margin-bottom: 0.5rem;">
                THE PAY-ON-RESULT KLEE INITIATIVE
              </p>

              <h1 class="standalone-hero-title" style="font-size: 2.3rem; line-height: 1.25;">
                Get Trained by Government Law College Top Rank Holders. Pay the Coaching Fee Only After You Crack GLC.
              </h1>

              <p class="standalone-hero-subtitle" style="margin-top: 1rem; color: var(--white-bright); font-size: 1.05rem; line-height: 1.6;">
                Stop risking ₹40,000 upfront on generic commercial coaching centers. Pay a ₹2,500 commitment deposit today—pay the rest only when your official CEE Kerala merit allotment memo is in your hands.
              </p>

              <!-- Social Proof Chips -->
              <div class="social-proof-strip-wrapper">
                <span class="social-proof-chip"><i class="fa-solid fa-shield-halved" style="color: #4ade80;"></i> Zero Tuition Risk</span>
                <span class="social-proof-chip"><i class="fa-solid fa-ranking-star" style="color: var(--gold-primary);"></i> Real-Time Leaderboards</span>
                <span class="social-proof-chip"><i class="fa-solid fa-gavel" style="color: var(--gold-primary);"></i> GLC Ernakulam Faculty</span>
              </div>

              <div class="standalone-cta-group" style="margin-top: 1.75rem; display: flex; gap: 1rem; flex-wrap: wrap;">
                <button class="btn btn-gold btn-lg open-enroll-modal" data-course="KLEE 2027 Open Merit Syndicate">
                  <i class="fa-solid fa-bolt"></i> Apply for Open Merit Syndicate &rarr;
                </button>
                <a href="#course/super-batch" class="btn btn-glass btn-lg" style="border-color: var(--gold-border); color: var(--gold-light);">
                  <i class="fa-solid fa-user-plus"></i> View 15-Seat Super Batch Track &rarr;
                </a>
              </div>
            </div>

            <!-- Hero Side Pricing Card -->
            <div class="standalone-hero-side">
              <div class="standalone-pricing-card tri-border-card" style="border-color: var(--gold-border);">
                <div class="pricing-card-badge" style="background: rgba(212, 175, 55, 0.15); color: var(--gold-light);"><i class="fa-solid fa-handshake"></i> PAY ON SELECTION MODEL</div>
                <h3 class="pricing-summary-text" style="font-size: 1.6rem; color: var(--gold-primary); text-align: center; margin-top: 0.5rem;">
                  ₹2,500 + ₹20,000
                </h3>
                <p style="color: var(--white-muted); font-size: 0.8rem; text-align: center; margin-bottom: 1rem;">
                  (₹2,500 deposit today • ₹20,000 success fee ONLY upon official GLC allotment)
                </p>

                <div class="pricing-details-stack" style="margin: 1rem 0;">
                  <div class="pricing-detail-item">
                    <div class="detail-item-title" style="color: #fff; font-weight: 700;">Step 1: ₹2,500 Deposit</div>
                    <div class="detail-item-note" style="color: var(--white-muted);">Instant LMS, test engines & digital vault access</div>
                  </div>
                  <div class="pricing-detail-item" style="margin-top: 0.5rem;">
                    <div class="detail-item-title" style="color: #4ade80; font-weight: 700;">Step 2: Ranker Training</div>
                    <div class="detail-item-note" style="color: var(--white-muted);">Taught by GLC Ernakulam top rank holders</div>
                  </div>
                  <div class="pricing-detail-item" style="margin-top: 0.5rem;">
                    <div class="detail-item-title" style="color: var(--gold-light); font-weight: 700;">Step 3: ₹20,000 Success Fee</div>
                    <div class="detail-item-note" style="color: var(--white-muted);">Payable ONLY after your CEE allotment memo arrives</div>
                  </div>
                </div>

                <button class="btn btn-gold open-enroll-modal" data-course="KLEE 2027 Open Merit Syndicate" style="width: 100%;">
                  <i class="fa-solid fa-handshake"></i> Register for Open Merit &rarr;
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Main Body Container -->
      <div class="container" style="padding-top: 3rem; padding-bottom: 5rem;">

        <!-- Problem Section -->
        <div class="standalone-section-card tri-border-card" style="border-color: var(--gold-border); background: linear-gradient(135deg, rgba(212, 175, 55, 0.08) 0%, rgba(5, 10, 25, 0.95) 100%); margin-bottom: 2.5rem;">
          <h2 class="standalone-section-heading" style="color: #ffffff;">
            ${data.brutalReality.headline}
          </h2>
          <p style="color: var(--white-muted); font-size: 1rem; margin-bottom: 1.75rem;">
            ${data.brutalReality.subtitle}
          </p>

          <div class="detail-grid-3">
            ${data.brutalReality.points.map(pt => `
              <div class="glass-panel" style="border-color: var(--gold-border); background: rgba(0, 0, 0, 0.5); padding: 1.5rem;">
                <h3 style="color: var(--gold-light); font-size: 1.05rem; margin-bottom: 0.6rem; font-family: var(--font-serif);">❌ ${pt.title}</h3>
                <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">${pt.desc}</p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- 3 Steps Grid -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem; border-color: var(--gold-primary);">
          <h2 class="standalone-section-heading"><i class="fa-solid fa-hand-holding-dollar"></i> ${data.payOnResultDetails.headline}</h2>
          
          <div class="detail-grid-3" style="margin: 1.5rem 0;">
            ${data.payOnResultDetails.steps.map(s => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--gold-border); background: rgba(0, 0, 0, 0.6);">
                <span style="background: var(--gold-primary); color: #000; font-weight: 800; font-size: 0.75rem; padding: 0.2rem 0.6rem; border-radius: 4px; text-transform: uppercase;">${s.step}</span>
                <h3 style="color: var(--gold-light); font-size: 1.1rem; margin: 0.75rem 0 0.4rem 0; font-family: var(--font-serif);">${s.title}</h3>
                <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">${s.desc}</p>
              </div>
            `).join('')}
          </div>

          <!-- Zero Risk Box -->
          <div class="zero-risk-rule-box">
            <span class="zero-risk-badge"><i class="fa-solid fa-shield-halved"></i> ABSOLUTE GUARANTEE</span>
            <p class="zero-risk-rule-text">${data.payOnResultDetails.zeroRiskRule}</p>
          </div>

          <!-- Faculty Difference -->
          <h3 style="font-family: var(--font-serif); color: var(--gold-light); font-size: 1.3rem; margin: 2rem 0 1rem 0;">
            The Faculty Difference: Learn From Those Who Cracked It
          </h3>
          <div class="detail-grid-3">
            ${data.payOnResultDetails.facultyMethods.map(fm => `
              <div class="glass-panel" style="padding: 1.25rem;">
                <h4 style="color: #ffffff; font-size: 1rem; margin-bottom: 0.4rem; font-family: var(--font-serif);">⚡ ${fm.title}</h4>
                <p style="color: var(--white-muted); font-size: 0.85rem; line-height: 1.5; margin: 0;">${fm.desc}</p>
              </div>
            `).join('')}
          </div>

          <!-- What You Get -->
          <h3 style="font-family: var(--font-serif); color: var(--gold-light); font-size: 1.3rem; margin: 2.5rem 0 1rem 0;">
            What You Get Inside The Syndicate
          </h3>
          <div class="access-points-grid-2">
            ${data.payOnResultDetails.whatYouGet.map(wyg => `
              <div class="access-point-card">
                <span style="color: var(--gold-primary); font-weight: 800; font-size: 1.1rem;">✓</span>
                <span style="color: #fff; font-size: 0.9rem; line-height: 1.5;">${wyg}</span>
              </div>
            `).join('')}
          </div>

          <!-- Hard Filter -->
          <div style="margin-top: 2.5rem;">
            <h3 style="font-family: var(--font-serif); color: #ffffff; font-size: 1.5rem; margin-bottom: 0.3rem;">
              ${data.payOnResultDetails.hardFilter.headline}
            </h3>
            <p style="color: var(--white-muted); font-size: 0.95rem; margin-bottom: 1.5rem;">
              ${data.payOnResultDetails.hardFilter.subHeadline}
            </p>

            <div class="selection-filter-grid">
              <div class="filter-card who-for">
                <div class="filter-card-title"><i class="fa-solid fa-circle-check"></i> Who This Is For:</div>
                <ul class="filter-list">
                  ${data.payOnResultDetails.hardFilter.whoFor.map(wf => `<li><span style="color: #4ade80;">✓</span><span>${wf}</span></li>`).join('')}
                </ul>
              </div>

              <div class="filter-card who-not-for">
                <div class="filter-card-title"><i class="fa-solid fa-circle-xmark"></i> Who This Is NOT For:</div>
                <ul class="filter-list">
                  ${data.payOnResultDetails.hardFilter.whoNotFor.map(wnf => `<li><span style="color: var(--gold-light);">✕</span><span>${wnf}</span></li>`).join('')}
                </ul>
              </div>
            </div>
          </div>

          <!-- Numbers Table -->
          <div style="margin-top: 2.5rem;">
            <h3 style="font-family: var(--font-serif); color: var(--gold-light); font-size: 1.3rem; margin-bottom: 1rem;">
              The Numbers (Why This Is A No-Brainer)
            </h3>
            <div class="syndicate-table-container">
              <table class="syndicate-comparison-table">
                <thead>
                  <tr>
                    <th style="width: 25%;">Metric</th>
                    <th style="width: 37.5%; color: var(--gold-light);">Private Law College Management Route</th>
                    <th style="width: 37.5%; color: #4ade80;">Open Merit Syndicate Route</th>
                  </tr>
                </thead>
                <tbody>
                  ${data.payOnResultDetails.numbersTable.map(num => `
                    <tr>
                      <td class="param-name">${num.metric}</td>
                      <td style="color: var(--white-muted); font-size: 0.9rem;">${num.privateRoute}</td>
                      <td style="color: #ffffff; font-weight: 700; font-size: 0.95rem;">${num.syndicateRoute}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>

        </div>

        <!-- Side-by-Side Comparison Matrix -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem; border-color: var(--gold-border);">
          <h2 class="standalone-section-heading">
            <i class="fa-solid fa-code-compare"></i> ${data.comparisonTable.headline}
          </h2>
          <p style="color: var(--white-muted); font-size: 0.95rem; margin-bottom: 1.5rem;">
            ${data.comparisonTable.subHeadline}
          </p>

          <div class="syndicate-table-container">
            <table class="syndicate-comparison-table">
              <thead>
                <tr>
                  <th style="width: 25%;">Parameter</th>
                  <th style="width: 37.5%; color: var(--gold-primary);">KLEE 2027 Super Batch</th>
                  <th style="width: 37.5%; color: var(--gold-light);">KLEE 2027 Open Merit</th>
                </tr>
              </thead>
              <tbody>
                ${data.comparisonTable.rows.map(row => `
                  <tr>
                    <td class="param-name">${row.param}</td>
                    <td style="color: #ffffff; font-size: 0.9rem;">${row.superBatch}</td>
                    <td style="color: var(--white-muted); font-size: 0.9rem;">${row.openMerit}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>

        <!-- 4-Step Admission Process -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;">
          <div style="text-align: center; margin-bottom: 1.5rem;">
            <h2 style="font-family: var(--font-serif); font-size: 2rem; color: #ffffff;">
              ${data.admissionProcess.headline}
            </h2>
          </div>
          <div class="admission-process-grid">
            ${data.admissionProcess.steps.map(step => `
              <div class="step-card">
                <span class="step-num-badge">${step.num}</span>
                <div class="step-title">${step.title}</div>
                <p class="step-desc">${step.desc}</p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- FAQs -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;">
          <h2 class="standalone-section-heading"><i class="fa-solid fa-circle-question"></i> Frequently Asked Questions</h2>
          <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1.5rem;">
            ${data.faqs.map(faq => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--white-border); background: rgba(0, 0, 0, 0.6);">
                <h3 style="color: var(--gold-light); font-size: 1.05rem; margin-bottom: 0.5rem; font-family: var(--font-serif);">❓ ${faq.q}</h3>
                <p style="color: var(--white-muted); font-size: 0.9rem; line-height: 1.6; margin: 0;">${faq.a}</p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Final CTA -->
        <div class="standalone-section-card tri-border-card" style="text-align: center; background: radial-gradient(circle at center, rgba(212, 175, 55, 0.2) 0%, rgba(0,0,0,0.95) 100%); padding: 4rem 2rem; border-color: var(--gold-primary);">
          <h2 style="font-family: var(--font-serif); font-size: 2.2rem; color: #fff; margin-bottom: 0.75rem;">
            Back Yourself. We Are Ready to Back You.
          </h2>
          <p style="color: var(--white-muted); max-width: 650px; margin: 0 auto 2rem auto; font-size: 1rem;">
            Step into the arena with zero tuition risk. Claim your diagnostic screening slot now.
          </p>
          <button class="btn btn-gold btn-lg open-enroll-modal" data-course="KLEE 2027 Open Merit Syndicate">
            <i class="fa-solid fa-handshake"></i> Register for Open Merit Syndicate &rarr;
          </button>
        </div>

      </div>

      <footer style="background: #000; border-top: 1px solid var(--white-border); padding: 2.5rem 0; text-align: center; color: var(--white-muted); font-size: 0.88rem;">
        <div class="container">
          <p>© 2026 Indian Law School (ILS). KLEE 2027 Open Merit Syndicate. Taught Exclusively by GLC Ernakulam Top Rank Holders.</p>
        </div>
      </footer>
    </div>
  `;

  container.innerHTML = html;
  bindModalTriggers(container);
}

function bindModalTriggers(container) {
  const modalTriggers = container.querySelectorAll('.open-enroll-modal');
  modalTriggers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const courseName = btn.getAttribute('data-course');
      const modal = document.getElementById('enroll-modal');
      const selectElem = document.getElementById('form-course-select');
      if (selectElem && courseName) {
        let found = false;
        for (let i = 0; i < selectElem.options.length; i++) {
          if (selectElem.options[i].value === courseName || selectElem.options[i].text.includes(courseName)) {
            selectElem.selectedIndex = i;
            found = true;
            break;
          }
        }
        if (!found) {
          selectElem.value = courseName;
        }
      }
      if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
      }
    });
  });
}

function renderKleeLandingPage(data, container) {
  let html = `
    <div class="standalone-landing-wrapper">
      
      <!-- Urgent Top Alert Banner -->
      <div class="container" style="padding-top: 0.5rem;">
        <div class="urgency-top-alert-banner" style="background: linear-gradient(90deg, rgba(185, 28, 28, 0.35) 0%, rgba(10, 18, 42, 0.95) 100%); border: 1px solid rgba(239, 68, 68, 0.5); border-radius: 14px; padding: 0.75rem 1.25rem; margin-bottom: 0.75rem; box-shadow: 0 5px 20px rgba(220, 38, 38, 0.2);">
          <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
              <span class="pulse-dot-red"></span>
              <span style="font-weight: 800; color: #f87171; font-size: 0.9rem; letter-spacing: 0.5px;">
                🔥 KLEE 2027 INTAKE ACTIVE • DIAGNOSTIC SCREENING SLOTS FILLING FAST!
              </span>
            </div>
            <button class="btn btn-gold btn-sm open-enroll-modal" data-course="KLEE 2027 Entrance Syndicate">
              <i class="fa-solid fa-graduation-cap"></i> Apply for Diagnostic Screening
            </button>
          </div>
        </div>
      </div>

      <!-- Sub-Header Breadcrumb Bar -->
      <div class="landing-subhead-bar">
        <div class="container" style="display: flex; justify-content: space-between; align-items: center; padding: 0.85rem 0;">
          <div class="breadcrumb-box">
            <a href="#home" class="breadcrumb-link"><i class="fa-solid fa-house"></i> Home</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#courses" class="breadcrumb-link">Courses</a>
            <span class="breadcrumb-sep">/</span>
            <span class="breadcrumb-active">KLEE 2027 Entrance Syndicate</span>
          </div>
          <a href="#home" class="btn btn-glass btn-sm">
            <i class="fa-solid fa-arrow-left"></i> Back to Main Platform
          </a>
        </div>
      </div>

      <!-- Hero Header Section -->
      <section class="standalone-hero">
        <div class="container">
          <div class="standalone-hero-grid">
            <div class="standalone-hero-main">
              <div class="ticker-badge pulse-badge-glow" style="margin-bottom: 1rem;">
                <span class="pulse-dot"></span>
                <span class="ticker-text">${data.statusBadge}</span>
              </div>

              <p style="color: var(--gold-light); font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; font-size: 0.85rem; margin-bottom: 0.5rem;">
                ${data.tagline}
              </p>

              <h1 class="standalone-hero-title" style="font-size: 2.3rem; line-height: 1.25;">
                ${data.mainHeadline}
              </h1>

              <p class="standalone-hero-subtitle" style="margin-top: 1rem; color: var(--white-bright); font-size: 1.05rem; line-height: 1.6;">
                ${data.subHeadline}
              </p>

              <!-- Social Proof Strip -->
              <div class="social-proof-strip-wrapper">
                ${data.socialProofStrip.map(item => `
                  <span class="social-proof-chip">
                    <i class="fa-solid fa-circle-check" style="color: var(--gold-primary);"></i> ${item}
                  </span>
                `).join('')}
              </div>

              <div class="standalone-cta-group" style="margin-top: 1.75rem; display: flex; gap: 1rem; flex-wrap: wrap;">
                <button class="btn btn-gold btn-lg open-enroll-modal" data-course="KLEE 2027 Entrance Syndicate">
                  <i class="fa-solid fa-bolt"></i> Apply for Diagnostic Screening &rarr;
                </button>
                <a href="#compare-syndicates" class="btn btn-glass btn-lg" style="border-color: var(--gold-border); color: var(--gold-light);">
                  <i class="fa-solid fa-table-columns"></i> Compare Our Two Syndicates &darr;
                </a>
              </div>
            </div>

            <!-- Hero Side Pricing Card -->
            <div class="standalone-hero-side">
              <div class="standalone-pricing-card tri-border-card" style="border-color: var(--gold-primary);">
                <div class="pricing-card-badge"><i class="fa-solid fa-shield-halved"></i> TWO DISTINCT PROTOCOLS</div>
                <h3 class="pricing-summary-text" style="font-size: 1.2rem; color: var(--gold-light); text-align: center; margin-top: 0.5rem;">
                  Choose Your Battleground
                </h3>
                
                <div class="pricing-details-stack" style="margin: 1.25rem 0;">
                  ${data.investmentDetails.map(item => `
                    <div class="pricing-detail-item" style="border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 0.75rem; margin-bottom: 0.75rem;">
                      <div class="detail-item-title" style="color: #fff; font-weight: 700;">${item.title}</div>
                      <div class="detail-item-price" style="color: var(--gold-primary); font-size: 1.35rem; font-weight: 800;">${item.price}</div>
                      <div class="detail-item-note" style="color: var(--white-muted); font-size: 0.8rem;">${item.note}</div>
                    </div>
                  `).join('')}
                </div>

                <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                  <button class="btn btn-gold open-enroll-modal" data-course="KLEE 2027 Super Batch Syndicate" style="width: 100%;">
                    <i class="fa-solid fa-user-plus"></i> Apply for Super Batch (₹1L 100% Refundable)
                  </button>
                  <button class="btn btn-glass open-enroll-modal" data-course="KLEE 2027 Open Merit Syndicate" style="width: 100%; border-color: #ef4444; color: #f87171;">
                    <i class="fa-solid fa-handshake"></i> Register for Open Merit (₹2.5K Pay-On-Result)
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Body Content -->
      <div class="container" style="padding-top: 3rem; padding-bottom: 5rem;">

        <!-- SECTION 1: THE BRUTAL REALITY -->
        <div class="standalone-section-card tri-border-card" style="border-color: rgba(239, 68, 68, 0.4); background: linear-gradient(135deg, rgba(220, 38, 38, 0.08) 0%, rgba(5, 10, 25, 0.95) 100%); margin-bottom: 2.5rem;">
          <div style="display: flex; align-items: center; gap: 0.75rem; color: #ef4444; font-weight: 800; text-transform: uppercase; font-size: 0.85rem; margin-bottom: 0.5rem;">
            <i class="fa-solid fa-triangle-exclamation"></i> THE PROBLEM WE SOLVED
          </div>
          <h2 class="standalone-section-heading" style="color: #ffffff; margin-bottom: 0.5rem;">
            ${data.brutalReality.headline}
          </h2>
          <p style="color: var(--white-muted); font-size: 1rem; margin-bottom: 1.75rem;">
            ${data.brutalReality.subtitle}
          </p>

          <div class="detail-grid-3">
            ${data.brutalReality.points.map(pt => `
              <div class="glass-panel" style="border-color: rgba(239, 68, 68, 0.3); background: rgba(0, 0, 0, 0.5); padding: 1.5rem;">
                <h3 style="color: #f87171; font-size: 1.05rem; margin-bottom: 0.6rem; font-family: var(--font-serif);">
                  ❌ ${pt.title}
                </h3>
                <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">
                  ${pt.desc}
                </p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- SECTION 2: THE SYNDICATE BLUEPRINT -->
        <div class="standalone-section-card tri-border-card" style="border-color: var(--gold-primary); margin-bottom: 2.5rem;">
          <div style="display: flex; align-items: center; gap: 0.75rem; color: var(--gold-primary); font-weight: 800; text-transform: uppercase; font-size: 0.85rem; margin-bottom: 0.5rem;">
            <i class="fa-solid fa-wand-magic-sparkles"></i> THE SOLUTION
          </div>
          <h2 class="standalone-section-heading">
            ${data.syndicateBlueprint.headline}
          </h2>
          <p style="color: var(--gold-light); font-size: 1rem; margin-bottom: 1.75rem;">
            ${data.syndicateBlueprint.subtitle}
          </p>

          <div class="detail-grid-3">
            ${data.syndicateBlueprint.points.map(pt => `
              <div class="glass-panel" style="border-color: var(--gold-border); background: rgba(0, 0, 0, 0.5); padding: 1.5rem;">
                <h3 style="color: var(--gold-light); font-size: 1.05rem; margin-bottom: 0.6rem; font-family: var(--font-serif);">
                  ⚖️ ${pt.title}
                </h3>
                <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">
                  ${pt.desc}
                </p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- SECTION 3: CORE CURRICULUM ARCHITECTURE -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;" id="curriculum-architecture">
          <h2 class="standalone-section-heading">
            <i class="fa-solid fa-layer-group"></i> Core Curriculum Architecture
          </h2>
          <p style="color: var(--white-muted); margin-bottom: 1.5rem;">
            Engineered by state rank-holders to deconstruct all 120 questions (360 marks) of the CEE Kerala computer-based entrance examination.
          </p>

          <div class="detail-grid-2">
            ${data.curriculumArchitecture.map(curr => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--white-border); background: rgba(0, 0, 0, 0.6);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                  <h3 style="color: var(--gold-light); font-size: 1.1rem; margin: 0; font-family: var(--font-serif);">
                    <i class="fa-solid ${curr.icon}" style="color: var(--gold-primary); margin-right: 0.4rem;"></i> ${curr.title}
                  </h3>
                  <span class="subject-badge" style="background: rgba(212, 175, 55, 0.15); color: var(--gold-light); border: 1px solid var(--gold-border); padding: 0.25rem 0.6rem; border-radius: 6px; font-weight: 700; font-size: 0.8rem;">
                    ${curr.marks}
                  </span>
                </div>
                <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">
                  ${curr.desc}
                </p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- SECTION 4: THE TWO TRAINING PROTOCOLS (COMPARISON MATRIX) -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;" id="compare-syndicates">
          <div style="text-align: center; margin-bottom: 1.5rem;">
            <span style="color: var(--gold-primary); font-weight: 800; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px;">
              SIDE-BY-SIDE PROTOCOL COMPARISON
            </span>
            <h2 style="font-family: var(--font-serif); font-size: 2rem; color: #ffffff; margin-top: 0.25rem;">
              ${data.comparisonTable.headline}
            </h2>
            <p style="color: var(--white-muted); font-size: 1rem;">
              ${data.comparisonTable.subHeadline}
            </p>
          </div>

          <div class="syndicate-table-container">
            <table class="syndicate-comparison-table">
              <thead>
                <tr>
                  <th style="width: 22%;">Parameters</th>
                  <th class="col-superbatch" style="width: 39%;">
                    🏆 Super Batch Syndicate<br>
                    <small style="font-weight: normal; font-size: 0.8rem; color: var(--gold-light);">Strictly 15 Students • 100% Refund Guarantee</small>
                  </th>
                  <th class="col-openmerit" style="width: 39%;">
                    ⚡ Open Merit Syndicate<br>
                    <small style="font-weight: normal; font-size: 0.8rem; color: #f87171;">Pay-On-Result • ₹2.5K Deposit + ₹20K Success Fee</small>
                  </th>
                </tr>
              </thead>
              <tbody>
                ${data.comparisonTable.rows.map(row => `
                  <tr>
                    <td class="param-name">${row.param}</td>
                    <td class="val-superbatch">${row.superBatch}</td>
                    <td class="val-openmerit">${row.openMerit}</td>
                  </tr>
                `).join('')}
                <tr>
                  <td class="param-name" style="vertical-align: middle;">Action</td>
                  <td class="val-superbatch" style="text-align: center;">
                    <button class="btn btn-gold btn-sm open-enroll-modal" data-course="KLEE 2027 Super Batch Syndicate" style="width: 100%;">
                      [ Apply for Super Batch ]
                    </button>
                  </td>
                  <td class="val-openmerit" style="text-align: center;">
                    <button class="btn btn-glass btn-sm open-enroll-modal" data-course="KLEE 2027 Open Merit Syndicate" style="width: 100%; border-color: #ef4444; color: #f87171;">
                      [ Register for Open Merit ]
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- SECTION 5: DEEP DIVE TRACK BREAKDOWNS -->
        <div style="margin-bottom: 2.5rem;">
          <!-- Track 01 -->
          <div class="track-breakdown-card track-super">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem;">
              <div>
                <span style="background: rgba(212, 175, 55, 0.2); color: var(--gold-light); padding: 0.25rem 0.75rem; border-radius: 20px; font-weight: 800; font-size: 0.75rem; letter-spacing: 0.5px;">
                  ${data.trackSuperBatch.badge}
                </span>
                <h3 style="font-family: var(--font-serif); font-size: 1.8rem; color: #ffffff; margin-top: 0.5rem; margin-bottom: 0.25rem;">
                  ${data.trackSuperBatch.title}
                </h3>
                <span style="color: var(--white-muted); font-size: 0.9rem;">
                  <i class="fa-solid fa-users"></i> ${data.trackSuperBatch.capacity}
                </span>
              </div>
              <div style="text-align: right;">
                <div style="font-size: 1.4rem; font-weight: 800; color: var(--gold-primary);">
                  ${data.trackSuperBatch.tuition}
                </div>
                <button class="btn btn-gold btn-sm open-enroll-modal" data-course="KLEE 2027 Super Batch Syndicate" style="margin-top: 0.5rem;">
                  Apply for Super Batch &rarr;
                </button>
              </div>
            </div>

            <ul class="filter-list" style="margin-top: 1rem;">
              ${data.trackSuperBatch.features.map(f => `
                <li style="color: #ffffff;">
                  <span style="color: var(--gold-primary); font-weight: 800;">✓</span>
                  <span>${f}</span>
                </li>
              `).join('')}
            </ul>
          </div>

          <!-- Track 02 -->
          <div class="track-breakdown-card track-open" id="pay-on-result">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem;">
              <div>
                <span style="background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 0.25rem 0.75rem; border-radius: 20px; font-weight: 800; font-size: 0.75rem; letter-spacing: 0.5px;">
                  ${data.trackOpenMerit.badge}
                </span>
                <h3 style="font-family: var(--font-serif); font-size: 1.8rem; color: #ffffff; margin-top: 0.5rem; margin-bottom: 0.25rem;">
                  ${data.trackOpenMerit.title}
                </h3>
                <span style="color: var(--white-muted); font-size: 0.9rem;">
                  <i class="fa-solid fa-handshake"></i> ${data.trackOpenMerit.capacity}
                </span>
              </div>
              <div style="text-align: right;">
                <div style="font-size: 1.25rem; font-weight: 800; color: #f87171;">
                  ${data.trackOpenMerit.tuition}
                </div>
                <button class="btn btn-glass btn-sm open-enroll-modal" data-course="KLEE 2027 Open Merit Syndicate" style="margin-top: 0.5rem; border-color: #ef4444; color: #f87171;">
                  Register for Open Merit &rarr;
                </button>
              </div>
            </div>

            <ul class="filter-list" style="margin-top: 1rem;">
              ${data.trackOpenMerit.features.map(f => `
                <li style="color: #ffffff;">
                  <span style="color: #4ade80; font-weight: 800;">✓</span>
                  <span>${f}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        </div>

        <!-- SECTION 6: THE PAY-ON-RESULT INITIATIVE SPECIFICS -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem; border-color: var(--gold-primary);">
          <h2 class="standalone-section-heading">
            <i class="fa-solid fa-hand-holding-dollar"></i> ${data.payOnResultDetails.headline}
          </h2>

          <!-- 3 Steps Grid -->
          <div class="detail-grid-3" style="margin: 1.5rem 0;">
            ${data.payOnResultDetails.steps.map(s => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--gold-border); background: rgba(0, 0, 0, 0.6);">
                <span style="background: var(--gold-primary); color: #000; font-weight: 800; font-size: 0.75rem; padding: 0.2rem 0.6rem; border-radius: 4px; text-transform: uppercase;">
                  ${s.step}
                </span>
                <h3 style="color: var(--gold-light); font-size: 1.1rem; margin: 0.75rem 0 0.4rem 0; font-family: var(--font-serif);">
                  ${s.title}
                </h3>
                <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">
                  ${s.desc}
                </p>
              </div>
            `).join('')}
          </div>

          <!-- Zero Risk Rule Box -->
          <div class="zero-risk-rule-box">
            <span class="zero-risk-badge"><i class="fa-solid fa-shield-halved"></i> ABSOLUTE GUARANTEE</span>
            <p class="zero-risk-rule-text">
              ${data.payOnResultDetails.zeroRiskRule}
            </p>
          </div>

          <!-- Faculty Difference & Speed Methods -->
          <h3 style="font-family: var(--font-serif); color: var(--gold-light); font-size: 1.3rem; margin: 2rem 0 1rem 0;">
            The Faculty Difference: Learn From Those Who Cracked It
          </h3>
          <div class="detail-grid-3">
            ${data.payOnResultDetails.facultyMethods.map(fm => `
              <div class="glass-panel" style="padding: 1.25rem;">
                <h4 style="color: #ffffff; font-size: 1rem; margin-bottom: 0.4rem; font-family: var(--font-serif);">
                  ⚡ ${fm.title}
                </h4>
                <p style="color: var(--white-muted); font-size: 0.85rem; line-height: 1.5; margin: 0;">
                  ${fm.desc}
                </p>
              </div>
            `).join('')}
          </div>

          <!-- What You Get Inside -->
          <h3 style="font-family: var(--font-serif); color: var(--gold-light); font-size: 1.3rem; margin: 2.5rem 0 1rem 0;">
            What You Get Inside The Syndicate
          </h3>
          <div class="access-points-grid-2">
            ${data.payOnResultDetails.whatYouGet.map(wyg => `
              <div class="access-point-card">
                <span style="color: var(--gold-primary); font-weight: 800; font-size: 1.1rem;">✓</span>
                <span style="color: #fff; font-size: 0.9rem; line-height: 1.5;">${wyg}</span>
              </div>
            `).join('')}
          </div>

          <!-- Hard Selection Filter -->
          <div style="margin-top: 2.5rem;">
            <h3 style="font-family: var(--font-serif); color: #ffffff; font-size: 1.5rem; margin-bottom: 0.3rem;">
              ${data.payOnResultDetails.hardFilter.headline}
            </h3>
            <p style="color: var(--white-muted); font-size: 0.95rem; margin-bottom: 1.5rem;">
              ${data.payOnResultDetails.hardFilter.subHeadline}
            </p>

            <div class="selection-filter-grid">
              <div class="filter-card who-for">
                <div class="filter-card-title">
                  <i class="fa-solid fa-circle-check"></i> Who This Is For:
                </div>
                <ul class="filter-list">
                  ${data.payOnResultDetails.hardFilter.whoFor.map(wf => `
                    <li>
                      <span style="color: #4ade80;">✓</span>
                      <span>${wf}</span>
                    </li>
                  `).join('')}
                </ul>
              </div>

              <div class="filter-card who-not-for">
                <div class="filter-card-title">
                  <i class="fa-solid fa-circle-xmark"></i> Who This Is NOT For:
                </div>
                <ul class="filter-list">
                  ${data.payOnResultDetails.hardFilter.whoNotFor.map(wnf => `
                    <li>
                      <span style="color: #f87171;">✕</span>
                      <span>${wnf}</span>
                    </li>
                  `).join('')}
                </ul>
              </div>
            </div>
          </div>

          <!-- Numbers Matrix -->
          <div style="margin-top: 2.5rem;">
            <h3 style="font-family: var(--font-serif); color: var(--gold-light); font-size: 1.3rem; margin-bottom: 1rem;">
              The Numbers (Why This Is A No-Brainer)
            </h3>
            <div class="syndicate-table-container">
              <table class="syndicate-comparison-table">
                <thead>
                  <tr>
                    <th style="width: 25%;">Metric</th>
                    <th style="width: 37.5%; color: #f87171;">Private Law College Management Route</th>
                    <th style="width: 37.5%; color: #4ade80;">Open Merit Syndicate Route</th>
                  </tr>
                </thead>
                <tbody>
                  ${data.payOnResultDetails.numbersTable.map(num => `
                    <tr>
                      <td class="param-name">${num.metric}</td>
                      <td style="color: var(--white-muted); font-size: 0.9rem;">${num.privateRoute}</td>
                      <td style="color: #ffffff; font-weight: 700; font-size: 0.95rem;">${num.syndicateRoute}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- SECTION 7: THE 4-STEP ADMISSION PROCESS -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;" id="admission-process">
          <div style="text-align: center; margin-bottom: 1.5rem;">
            <span style="color: var(--gold-primary); font-weight: 800; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px;">
              HOW TO ENTER THE ARENA
            </span>
            <h2 style="font-family: var(--font-serif); font-size: 2rem; color: #ffffff; margin-top: 0.25rem;">
              ${data.admissionProcess.headline}
            </h2>
          </div>

          <div class="admission-process-grid">
            ${data.admissionProcess.steps.map(step => `
              <div class="step-card">
                <span class="step-num-badge">${step.num}</span>
                <div class="step-title">${step.title}</div>
                <p class="step-desc">${step.desc}</p>
              </div>
            `).join('')}
          </div>

          <div style="text-align: center; margin-top: 2rem;">
            <button class="btn btn-gold btn-lg open-enroll-modal" data-course="KLEE 2027 Entrance Syndicate">
              <i class="fa-solid fa-bolt"></i> Claim Your Screening Slot Now &rarr;
            </button>
          </div>
        </div>

        <!-- SECTION 8: FREQUENTLY ASKED QUESTIONS -->
        <div class="standalone-section-card tri-border-card" style="margin-bottom: 2.5rem;">
          <h2 class="standalone-section-heading">
            <i class="fa-solid fa-circle-question"></i> Frequently Asked Questions
          </h2>

          <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1.5rem;">
            ${data.faqs.map(faq => `
              <div class="glass-panel" style="padding: 1.5rem; border-color: var(--white-border); background: rgba(0, 0, 0, 0.6);">
                <h3 style="color: var(--gold-light); font-size: 1.05rem; margin-bottom: 0.5rem; font-family: var(--font-serif);">
                  ❓ ${faq.q}
                </h3>
                <p style="color: var(--white-muted); font-size: 0.9rem; line-height: 1.6; margin: 0;">
                  ${faq.a}
                </p>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- SECTION 9: FINAL CALL TO ACTION -->
        <div class="standalone-section-card tri-border-card" style="text-align: center; background: radial-gradient(circle at center, rgba(212, 175, 55, 0.2) 0%, rgba(0,0,0,0.95) 100%); padding: 4rem 2rem; border-color: var(--gold-primary);">
          <span style="color: #f87171; font-weight: 800; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 0.5rem;">
            🔥 ADMISSIONS CLOSING ONCE COHORT CAPACITY IS REACHED
          </span>
          <h2 style="font-family: var(--font-serif); font-size: 2.2rem; color: #fff; margin-bottom: 0.75rem; max-width: 800px; margin-left: auto; margin-right: auto;">
            ${data.finalCta.headline}
          </h2>
          <h3 style="color: var(--gold-light); font-family: var(--font-serif); font-size: 1.3rem; margin-bottom: 1rem;">
            ${data.finalCta.subHeadline}
          </h3>
          <p style="color: var(--white-muted); max-width: 700px; margin: 0 auto 2rem auto; font-size: 1rem; line-height: 1.6;">
            ${data.finalCta.text}
          </p>

          <div style="display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap;">
            <button class="btn btn-gold btn-lg open-enroll-modal" data-course="KLEE 2027 Super Batch Syndicate">
              <i class="fa-solid fa-bolt"></i> ${data.finalCta.primaryBtn} &rarr;
            </button>
            <button class="btn btn-glass btn-lg open-enroll-modal" data-course="KLEE 2027 Open Merit Syndicate" style="border-color: #ef4444; color: #f87171;">
              <i class="fa-solid fa-handshake"></i> ${data.finalCta.secondaryBtn} &rarr;
            </button>
          </div>
        </div>

      </div>

      <!-- Standalone Footer -->
      <footer style="background: #000; border-top: 1px solid var(--white-border); padding: 2.5rem 0; text-align: center; color: var(--white-muted); font-size: 0.88rem;">
        <div class="container">
          <p style="margin-bottom: 0.5rem;">© 2026 Indian Law School (ILS). KLEE 2027 Entrance Syndicate. All Rights Reserved.</p>
          <p style="font-size: 0.8rem; color: rgba(255,255,255,0.4);">In Association with Vakkeel & Associates. Taught Exclusively by Government Law College Top Rank Holders.</p>
        </div>
      </footer>
    </div>
  `;

  container.innerHTML = html;

  // Re-bind enrollment triggers on newly injected content
  const modalTriggers = container.querySelectorAll('.open-enroll-modal');
  modalTriggers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const courseName = btn.getAttribute('data-course');
      const modal = document.getElementById('enroll-modal');
      const selectElem = document.getElementById('form-course-select');
      if (selectElem && courseName) {
        let found = false;
        for (let i = 0; i < selectElem.options.length; i++) {
          if (selectElem.options[i].value === courseName || selectElem.options[i].text.includes(courseName)) {
            selectElem.selectedIndex = i;
            found = true;
            break;
          }
        }
        if (!found) {
          selectElem.value = courseName;
        }
      }
      if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
      }
    });
  });
}

function renderCourseLandingPage(data, container) {
  let html = `
    <div class="standalone-landing-wrapper">
      
      <!-- High Urgency Top Alert Banner Box -->
      <div class="container" style="padding-top: 0.5rem;">
        <div class="urgency-top-alert-banner" style="background: linear-gradient(90deg, rgba(185, 28, 28, 0.35) 0%, rgba(10, 18, 42, 0.95) 100%); border: 1px solid rgba(239, 68, 68, 0.5); border-radius: 14px; padding: 0.75rem 1.25rem; margin-bottom: 0.75rem; box-shadow: 0 5px 20px rgba(220, 38, 38, 0.2);">
          <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
              <span class="pulse-dot-red"></span>
              <span style="font-weight: 800; color: #f87171; font-size: 0.9rem; letter-spacing: 0.5px;">
                🔥 LIMITED SPOTS ONLY • SEATS FILLING FAST!
              </span>
              <span style="color: #cbd5e1; font-size: 0.85rem;" class="desktop-only">
                Strict batch limit enforced — Contact admissions immediately to secure your seat.
              </span>
            </div>
            <button class="btn btn-gold btn-sm open-enroll-modal" data-course="${data.title}">
              <i class="fa-solid fa-phone"></i> Contact Admission Desk Now
            </button>
          </div>
        </div>
      </div>

      <!-- Sub-Header Breadcrumb & Top Bar -->
      <div class="landing-subhead-bar">
        <div class="container" style="display: flex; justify-content: space-between; align-items: center; padding: 0.85rem 0;">
          <div class="breadcrumb-box">
            <a href="#home" class="breadcrumb-link"><i class="fa-solid fa-house"></i> Home</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#courses" class="breadcrumb-link">Courses</a>
            <span class="breadcrumb-sep">/</span>
            <span class="breadcrumb-active">${data.title}</span>
          </div>
          <a href="#home" class="btn btn-glass btn-sm">
            <i class="fa-solid fa-arrow-left"></i> Back to Main Platform
          </a>
        </div>
      </div>

      <!-- Hero Header Banner Section -->
      <section class="standalone-hero">
        <div class="container">
          <div class="standalone-hero-grid">
            
            <div class="standalone-hero-main">
              <div class="ticker-badge pulse-badge-glow" style="margin-bottom: 1rem;">
                <span class="pulse-dot"></span>
                <span class="ticker-text">${data.statusBadge}</span>
              </div>

              <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap;">
                <span class="course-badge">${data.badge}</span>
                ${data.collaboration && !data.badge.toLowerCase().includes('vakkeel') ? `<span class="course-badge" style="background: rgba(255,255,255,0.08); color: var(--gold-light); border-color: var(--white-border);">${data.collaboration}</span>` : ''}
              </div>

              <h1 class="standalone-hero-title">${data.title}</h1>
              <p class="standalone-hero-subtitle">${data.subtitle}</p>
              <p class="standalone-hero-tagline">${data.tagline}</p>

              <!-- Dynamic Urgency Pills Row -->
              <div class="hero-urgency-pills-row" style="display: flex; gap: 0.75rem; margin-top: 1.25rem; flex-wrap: wrap;">
                <span class="urgency-pill red-glow-pill">
                  <i class="fa-solid fa-fire"></i> Limited Spots Remaining
                </span>
                <span class="urgency-pill gold-glow-pill">
                  <i class="fa-solid fa-bolt"></i> Fast Filling Batch
                </span>
                <span class="urgency-pill green-glow-pill">
                  <i class="fa-solid fa-headset"></i> Immediate Counselor Callback
                </span>
              </div>

              ${data.languages ? `
                <div style="display: flex; gap: 0.75rem; align-items: center; margin-top: 1.25rem;">
                  <span style="color: var(--white-muted); font-size: 0.85rem;">Available Languages:</span>
                  ${data.languages.map(l => `<span style="background: rgba(212, 175, 55, 0.15); color: var(--gold-light); padding: 0.25rem 0.75rem; border-radius: 20px; font-weight: 600; font-size: 0.85rem; border: 1px solid var(--gold-border);">${l}</span>`).join('')}
                </div>
              ` : ''}

              <div class="standalone-cta-group" style="margin-top: 2rem;">
                <button class="btn btn-gold btn-lg open-enroll-modal" data-course="${data.title}">
                  <i class="fa-solid fa-bolt"></i> Secure Your Spot Now &rarr;
                </button>
              </div>
            </div>

            <!-- Hero Pricing Card Column -->
            <div class="standalone-hero-side">
              <div class="standalone-pricing-card tri-border-card">
                <div class="pricing-card-badge"><i class="fa-solid fa-shield-halved"></i> OFFICIAL INVESTMENT</div>
                <h3 class="pricing-summary-text">${data.investmentSummary}</h3>
                
                <!-- Fast Filling Batch Notice Box -->
                <div class="pricing-urgency-notice-box" style="background: rgba(220, 38, 38, 0.12); border: 1px dashed rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 0.85rem; margin: 1rem 0; text-align: center;">
                  <div style="color: #f87171; font-weight: 800; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">
                    ⚡ FAST-FILLING BATCH NOTICE
                  </div>
                  <div style="color: #ffffff; font-size: 0.82rem; line-height: 1.4;">
                    Strict mentor capacity limit enforced. Contact admission desk immediately for priority seat reservation.
                  </div>
                </div>

                <div class="pricing-details-stack" style="margin: 1rem 0;">
                  ${data.investmentDetails.map(item => `
                    <div class="pricing-detail-item">
                      <div class="detail-item-title">${item.title}</div>
                      <div class="detail-item-price">${item.price}</div>
                      <div class="detail-item-note">${item.note}</div>
                    </div>
                  `).join('')}
                </div>

                <button class="btn btn-gold open-enroll-modal" data-course="${data.title}" style="width: 100%;">
                  <i class="fa-solid fa-user-plus"></i> Contact Immediately for Admission &rarr;
                </button>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.75rem;">
                  <a href="tel:+919876543210" class="btn btn-glass btn-sm" style="text-align: center; border-color: var(--gold-border); color: var(--gold-light);">
                    <i class="fa-solid fa-phone"></i> Call Desk
                  </a>
                  <a href="https://wa.me/919876543210?text=Hi%2C%20I%20want%20immediate%20admission%20details%20for%20${encodeURIComponent(data.title)}" target="_blank" class="btn btn-glass btn-sm" style="text-align: center; border-color: #22c55e; color: #4ade80;">
                    <i class="fa-brands fa-whatsapp"></i> WhatsApp
                  </a>
                </div>
              </div>
            </div>

          </div>
        </div>
      </section>

      <!-- Main Course Body Container -->
      <div class="container" style="padding-top: 3rem; padding-bottom: 5rem;" id="curriculum-breakdown">
        
        <!-- Urgent Seat Alert Banner -->
        <div class="standalone-section-card tri-border-card" style="background: linear-gradient(135deg, rgba(220, 38, 38, 0.12) 0%, rgba(10, 18, 42, 0.95) 100%); border-color: rgba(239, 68, 68, 0.5); margin-bottom: 2.5rem;">
          <div style="display: flex; gap: 1.5rem; align-items: center; flex-wrap: wrap;">
            <div style="font-size: 2.5rem; color: #f87171; flex-shrink: 0;"><i class="fa-solid fa-bell-concierge"></i></div>
            <div style="flex: 1; min-width: 250px;">
              <div style="display: inline-block; background: #dc2626; color: #fff; font-weight: 800; font-size: 0.75rem; padding: 0.2rem 0.6rem; border-radius: 4px; text-transform: uppercase; margin-bottom: 0.4rem;">
                Urgent Admission Alert
              </div>
              <h3 style="font-family: var(--font-serif); font-size: 1.35rem; color: #ffffff; margin-bottom: 0.4rem;">
                LIMITED SPOTS REMAINING FOR UPCOMING BATCH!
              </h3>
              <p style="color: var(--white-muted); font-size: 0.9rem; margin: 0; line-height: 1.6;">
                To guarantee 1-on-1 mentor access, weekly evaluations & personalized written feedback, batch sizes are strictly capped. Once capacity is reached, applications lock. Contact us immediately to secure your seat.
              </p>
            </div>
            <button class="btn btn-gold open-enroll-modal" data-course="${data.title}" style="flex-shrink: 0;">
              <i class="fa-solid fa-bolt"></i> Claim Immediate Seat Now
            </button>
          </div>
        </div>

        <!-- Section 1: Overview & Ecosystem -->
        <div class="standalone-section-card tri-border-card">
          <h2 class="standalone-section-heading"><i class="fa-solid fa-compass"></i> Ecosystem Overview & Purpose</h2>
          <p class="hero-lead-paragraph"><strong>${data.heroLead}</strong></p>
          <p class="ecosystem-description">${data.ecosystemDescription}</p>

          ${data.whyStruggle ? `
            <div class="struggle-warning-box">
              <h3 class="struggle-title">🎯 Why Do So Many Law Students Struggle?</h3>
              <ul class="struggle-list">
                ${data.whyStruggle.map(s => `<li>${s}</li>`).join('')}
              </ul>
            </div>
          ` : ''}

          ${data.programPurpose ? `
            <div class="purpose-highlight-box">
              <h3>⚖️ This Program Has A Different Purpose</h3>
              <p>${data.programPurpose}</p>
            </div>
          ` : ''}
        </div>

        <!-- Section 2: Small Batch Scarcity (for KLEE) -->
        ${data.whySmallBatch ? `
          <div class="standalone-section-card tri-border-card" style="border-color: var(--gold-primary);">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-users-viewfinder"></i> Why Only 15 Students Per Batch?</h2>
            <p style="color: var(--gold-light); font-size: 1rem; margin-bottom: 1.25rem;">${data.scarcityDetails ? data.scarcityDetails.note : 'Because excellence cannot be mass-produced.'}</p>
            <div class="detail-grid-2">
              ${data.whySmallBatch.map(item => `
                <div class="small-batch-item">
                  <span style="color: var(--gold-primary); font-weight: 800;">✓</span>
                  <span>${item}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Section 3: Faculty / Bench & Bar -->
        ${data.facultyBenchInfo ? `
          <div class="standalone-section-card tri-border-card">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-gavel"></i> Learn Directly from the Bench and the Bar</h2>
            <p style="color: var(--white-muted); margin-bottom: 1.5rem;">Instruction by Retired Judges, Senior Counsel, and Elite Currently Practicing Advocates.</p>
            <div class="detail-grid-3">
              ${data.facultyBenchInfo.map(f => `
                <div class="faculty-box glass-panel">
                  <h3 style="color: var(--gold-primary); font-size: 1.05rem; margin-bottom: 0.5rem; font-family: var(--font-serif);">⚖️ ${f.role}</h3>
                  <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">${f.desc}</p>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Section 4: KLEE Exam Pattern & Colleges -->
        ${data.examPattern ? `
          <div class="standalone-section-card tri-border-card">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-clipboard-list"></i> KLEE Exam Pattern & Subject Weightage</h2>
            <div class="klee-banner-stats">
              <div class="klee-stat-box"><span>Mode</span><strong>${data.examPattern.mode}</strong></div>
              <div class="klee-stat-box"><span>Duration</span><strong>${data.examPattern.duration}</strong></div>
              <div class="klee-stat-box"><span>Questions</span><strong>${data.examPattern.totalQuestions}</strong></div>
              <div class="klee-stat-box"><span>Max Marks</span><strong>${data.examPattern.maxMarks}</strong></div>
            </div>
            <div style="margin: 1rem 0 1.5rem 0; font-size: 0.9rem; color: var(--gold-light); background: rgba(212, 175, 55, 0.1); padding: 0.75rem 1rem; border-radius: 8px;">
              ${data.examPattern.markingScheme}
            </div>

            <div class="detail-grid-2">
              ${data.examPattern.subjects.map(s => `
                <div class="subject-card glass-panel">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <h4 style="color: var(--gold-primary); font-size: 1rem; margin: 0;">${s.name}</h4>
                    <span class="subject-badge">${s.marks}</span>
                  </div>
                  <p style="color: var(--white-muted); font-size: 0.88rem; margin: 0; line-height: 1.5;">${s.details}</p>
                </div>
              `).join('')}
            </div>

            ${data.govColleges ? `
              <div style="margin-top: 2rem;">
                <h3 style="color: var(--gold-light); font-size: 1.1rem; margin-bottom: 1rem;">🏛 Government Law Colleges in Kerala</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem;">
                  ${data.govColleges.map(c => `
                    <div style="background: rgba(0,0,0,0.5); padding: 0.75rem 1rem; border-radius: 8px; border: 1px solid var(--gold-border); font-size: 0.88rem; color: #fff;">📍 ${c}</div>
                  `).join('')}
                </div>
              </div>
            ` : ''}

            ${data.selfFinancingColleges ? `
              <div style="margin-top: 1.5rem;">
                <h3 style="color: var(--white-muted); font-size: 1rem; margin-bottom: 0.75rem;">🏫 Participating Self-Financing Law Colleges</h3>
                <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                  ${data.selfFinancingColleges.map(c => `
                    <span style="background: rgba(255,255,255,0.05); color: var(--white-muted); padding: 0.3rem 0.7rem; border-radius: 6px; font-size: 0.8rem; border: 1px solid var(--white-border);">${c}</span>
                  `).join('')}
                </div>
              </div>
            ` : ''}
          </div>
        ` : ''}

        <!-- Section 5: Why Enroll & Key Pillars -->
        <div class="standalone-section-card tri-border-card">
          <h2 class="standalone-section-heading"><i class="fa-solid fa-star"></i> Why Enroll in ${data.title}?</h2>
          ${data.whyEnroll ? `<p style="color: var(--gold-light); font-size: 1.05rem; margin-bottom: 1.5rem; font-weight: 600;">${data.whyEnroll}</p>` : ''}
          <div class="access-points-grid-2">
            ${data.accessPoints.map(pt => `
              <div class="access-point-card">
                <span style="color: var(--gold-primary); font-weight: 800; font-size: 1.1rem;">✓</span>
                <span style="color: #fff; font-size: 0.9rem; line-height: 1.5;">${pt}</span>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Section 6: Full Subject Library (for Law Mastery) -->
        ${data.fullSubjectList ? `
          <div class="standalone-section-card tri-border-card">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-book-bookmark"></i> Complete LL.B. Subject Library (All Semesters)</h2>
            <p style="color: var(--white-muted); margin-bottom: 1.5rem;">Comprehensive coverage across all core, elective, and practical law subjects.</p>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.85rem;">
              ${data.fullSubjectList.map(subj => `
                <div style="background: rgba(0,0,0,0.5); padding: 0.85rem 1rem; border-radius: 10px; border: 1px solid var(--white-border); color: #fff; font-weight: 500; font-size: 0.9rem;">
                  ${subj}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Section 7: Weekly Model -->
        ${data.weeklyModel ? `
          <div class="standalone-section-card tri-border-card">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-calendar-week"></i> Structured Weekly Online Learning Model</h2>
            <div class="detail-grid-2">
              ${data.weeklyModel.map(wm => `
                <div class="weekly-model-card glass-panel">
                  <div class="model-day-title">📅 ${wm.day}</div>
                  <div class="model-day-desc">${wm.desc}</div>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Section 8: Roadmaps / Strategy / Bootcamps -->
        ${(data.scenarioRoadmaps || data.hearingStrategy || data.examBootcamps) ? `
          <div class="standalone-section-card tri-border-card">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-shield-halved"></i> High-Stakes Strategy & Tactical Roadmaps</h2>
            <div class="detail-grid-2">
              ${(data.scenarioRoadmaps || data.hearingStrategy || data.examBootcamps).map(item => `
                <div class="roadmap-box glass-panel">
                  <h3 style="color: var(--gold-light); font-size: 1.05rem; margin-bottom: 0.4rem;">🎯 ${item.title}</h3>
                  <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">${item.desc}</p>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Section 9: Curriculum Vault -->
        ${data.curriculumVault ? `
          <div class="standalone-section-card tri-border-card">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-box-archive"></i> Comprehensive Vault & Practice Curriculum</h2>
            <div class="detail-grid-2">
              ${data.curriculumVault.map(cv => `
                <div class="vault-box glass-panel">
                  <h4 style="color: var(--gold-primary); font-size: 1rem; margin-bottom: 0.4rem;">📚 ${cv.title}</h4>
                  <p style="color: var(--white-muted); font-size: 0.88rem; line-height: 1.6; margin: 0;">${cv.desc}</p>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Section 10: 4K Visuals & Evaluations -->
        ${data.visualModules ? `
          <div class="standalone-section-card tri-border-card">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-film"></i> Cinema-Grade 4K Visual Modules</h2>
            <p style="color: #fff; font-size: 0.98rem; line-height: 1.7; margin-bottom: 1.25rem;">
              ${data.visualModules}
            </p>
            ${data.evaluations ? `
              <div style="padding: 1.25rem; background: rgba(212, 175, 55, 0.08); border-left: 4px solid var(--gold-primary); border-radius: 8px;">
                <h4 style="color: var(--gold-light); margin-bottom: 0.4rem; font-size: 1rem;">📝 Continuous Written Evaluations & Practitioner Feedback</h4>
                <p style="color: var(--white-muted); font-size: 0.9rem; margin: 0; line-height: 1.6;">${data.evaluations}</p>
              </div>
            ` : ''}
          </div>
        ` : ''}

        <!-- Section 11: Founder's Quote -->
        ${data.founderMessage ? `
          <div class="standalone-section-card tri-border-card" style="border-color: var(--gold-primary); background: rgba(212, 175, 55, 0.05);">
            <h2 class="standalone-section-heading"><i class="fa-solid fa-quote-left"></i> Founder's Message</h2>
            <blockquote style="font-family: var(--font-serif); font-size: 1.15rem; color: #fff; line-height: 1.7; font-style: italic; margin-bottom: 1rem;">
              "${data.founderMessage.quote}"
            </blockquote>
            <div style="color: var(--gold-primary); font-weight: 700;">${data.founderMessage.author}</div>
            <div style="color: var(--white-muted); font-size: 0.85rem;">${data.founderMessage.role}</div>
          </div>
        ` : ''}

        <!-- Section 12: Performance Refund Policy -->
        ${data.commitment ? `
          <div class="standalone-section-card tri-border-card" style="border: 2px solid var(--gold-primary); background: linear-gradient(135deg, rgba(212, 175, 55, 0.12) 0%, rgba(0,0,0,0.85) 100%);">
            <h2 style="font-family: var(--font-serif); color: var(--gold-light); font-size: 1.6rem; margin-bottom: 0.5rem;">
              ${data.commitment.title}
            </h2>
            <p style="color: var(--white-muted); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; font-size: 0.85rem; margin-bottom: 1rem;">
              ${data.commitment.subtitle}
            </p>
            <p style="color: #fff; font-size: 0.98rem; line-height: 1.7; margin-bottom: 1.5rem;">
              ${data.commitment.text}
            </p>
            <h4 style="color: var(--gold-light); font-size: 0.95rem; margin-bottom: 0.75rem;">Mandatory Eligibility Criteria:</h4>
            <div class="detail-grid-2">
              ${data.commitment.criteria.map(c => `
                <div style="display: flex; align-items: center; gap: 0.5rem; color: #fff; font-size: 0.88rem; background: rgba(0,0,0,0.4); padding: 0.65rem 0.85rem; border-radius: 8px; border: 1px solid var(--white-border);">
                  <span style="color: var(--gold-primary);">✓</span> ${c}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Section 13: Who Should Enroll -->
        <div class="standalone-section-card tri-border-card">
          <h2 class="standalone-section-heading"><i class="fa-solid fa-user-check"></i> Who Should Enroll?</h2>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem;">
            ${data.whoShouldEnroll.map(w => `
              <div style="display: flex; gap: 0.75rem; align-items: flex-start; background: rgba(0,0,0,0.4); padding: 1rem; border-radius: 10px; border: 1px solid var(--white-border);">
                <span style="color: var(--gold-primary); font-size: 1.1rem;">🎯</span>
                <span style="color: #fff; font-size: 0.9rem; line-height: 1.5;">${w}</span>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Section 14: Final Call To Action Card -->
        <div class="standalone-section-card tri-border-card" style="text-align: center; background: radial-gradient(circle at center, rgba(212, 175, 55, 0.18) 0%, rgba(0,0,0,0.95) 100%); padding: 4rem 2rem; border-color: var(--gold-primary);">
          <span style="color: #f87171; font-weight: 800; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 0.5rem;">
            🔥 ADMISSIONS FILLING FAST • CONTACT IMMEDIATELY
          </span>
          <h2 style="font-family: var(--font-serif); font-size: 2.2rem; color: #fff; margin-bottom: 0.75rem;">Master the Law. Master Your Future.</h2>
          <p style="color: var(--white-muted); max-width: 650px; margin: 0 auto 2rem auto; font-size: 1rem;">
            Strict batch limits active. Contact our senior academic desk immediately to lock in your priority admission.
          </p>

          <div style="display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap;">
            <button class="btn btn-gold btn-lg open-enroll-modal" data-course="${data.title}">
              <i class="fa-solid fa-bolt"></i> Claim Priority Seat in ${data.title} &rarr;
            </button>
            <a href="https://wa.me/919876543210?text=Hi%2C%20I%20want%20immediate%20admission%20details%20for%20${encodeURIComponent(data.title)}" target="_blank" class="btn btn-glass btn-lg" style="border-color: #22c55e; color: #4ade80;">
              <i class="fa-brands fa-whatsapp"></i> Chat on WhatsApp Immediately
            </a>
            <a href="#home" class="btn btn-glass btn-lg">
              <i class="fa-solid fa-arrow-left"></i> Return to Main Platform
            </a>
          </div>
        </div>

      </div>

      <!-- Standalone Footer -->
      <footer style="background: #000; border-top: 1px solid var(--white-border); padding: 2.5rem 0; text-align: center; color: var(--white-muted); font-size: 0.88rem;">
        <div class="container">
          <p style="margin-bottom: 0.5rem;">© 2026 Indian Law School (ILS). ${data.title}. All Rights Reserved.</p>
          <p style="font-size: 0.8rem; color: rgba(255,255,255,0.4);">In Association with Vakkeel & Associates. Premium Legal Learning & Practice Ecosystem.</p>
        </div>
      </footer>

    </div>
  `;

  container.innerHTML = html;

  // Re-bind enrollment triggers on the newly injected content
  const modalTriggers = container.querySelectorAll('.open-enroll-modal');
  modalTriggers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const courseName = btn.getAttribute('data-course');
      const modal = document.getElementById('enroll-modal');
      const selectElem = document.getElementById('form-course-select');
      if (selectElem && courseName) {
        selectElem.value = courseName;
      }
      if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
      }
    });
  });
}

function renderBlogArticlePage(post, container) {
  let html = `
    <div class="standalone-blog-wrapper">
      
      <!-- Sub-Header Bar -->
      <div class="landing-subhead-bar">
        <div class="container" style="display: flex; justify-content: space-between; align-items: center; padding: 0.85rem 0;">
          <div class="breadcrumb-box">
            <a href="#home" class="breadcrumb-link"><i class="fa-solid fa-house"></i> Home</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#knowledge-hub" class="breadcrumb-link">Protect Yourself Hub</a>
            <span class="breadcrumb-sep">/</span>
            <span class="breadcrumb-active">${post.title}</span>
          </div>
          <a href="#knowledge-hub" class="btn btn-glass btn-sm">
            <i class="fa-solid fa-arrow-left"></i> Back to Hub
          </a>
        </div>
      </div>

      <!-- Article Hero Container -->
      <div class="container" style="max-width: 900px; padding-top: 3rem; padding-bottom: 5rem;">
        
        <article class="standalone-article-card tri-border-card">
          <div class="article-header" style="margin-bottom: 2rem; border-bottom: 1px solid var(--white-border); padding-bottom: 1.5rem;">
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
              <span class="glass-badge glass-badge-gold">${post.category}</span>
              <span class="glass-badge">${post.tag}</span>
            </div>

            <h1 class="article-standalone-title">${post.title}</h1>
            
            <div class="article-meta-row" style="display: flex; gap: 1.5rem; align-items: center; margin-top: 1rem; color: var(--white-muted); font-size: 0.88rem;">
              <span><i class="fa-solid fa-scale-balanced" style="color: var(--gold-primary);"></i> Indian Law School & Vakkeel & Associates</span>
              <span><i class="fa-solid fa-clock" style="color: var(--gold-primary);"></i> ${post.readTime}</span>
            </div>
          </div>

          <div class="article-body-content">
            ${post.content}
          </div>

          <div class="article-bottom-cta">
            <h3>Ready to Build Doctrinal & Practical Legal Mastery?</h3>
            <p>Enroll in Indian Law School programs or request direct consultative guidance from senior legal educators.</p>
            <div style="display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap; margin-top: 1.5rem;">
              <button class="btn btn-gold open-enroll-modal" data-course="General Consultation">
                <i class="fa-solid fa-graduation-cap"></i> Explore Flagship Programs
              </button>
              <a href="#home" class="btn btn-glass">Return to Main Platform</a>
            </div>
          </div>

        </article>

      </div>

      <!-- Article Footer -->
      <footer style="background: #000; border-top: 1px solid var(--white-border); padding: 2rem 0; text-align: center; color: var(--white-muted); font-size: 0.85rem;">
        <div class="container">
          <p>© 2026 Indian Law School (ILS). Legal Awareness & Guidance Hub.</p>
        </div>
      </footer>

    </div>
  `;

  container.innerHTML = html;

  // Re-bind modal triggers
  const modalTriggers = container.querySelectorAll('.open-enroll-modal');
  modalTriggers.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const modal = document.getElementById('enroll-modal');
      if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
      }
    });
  });
}
