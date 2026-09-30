/* ==========================================================================
   INDIAN LAW SCHOOL (ILS) - MASTER ES MODULE ENTRY POINT
   Theme: Pure Dark Black Base + Gold, Navy Blue & White Highlights
   ========================================================================== */

import { initParticleCanvas } from './modules/canvas.js?v=6.0';
import { initSeatTicker } from './modules/ticker.js?v=6.0';
import { initCourseTabs } from './modules/courses.js?v=6.0';
import { initAIWeakAreaWidget } from './modules/ai-widget.js?v=6.0';
import { initRefundChecklist } from './modules/refund-tracker.js?v=6.0';
import { initBlogHub } from './modules/blog-hub.js?v=6.0';
import { initEnrollmentModal, initNavbarScroll } from './modules/modal.js?v=6.0';
import { initScrollAnimations } from './modules/scroll-anim.js?v=6.0';
import { initRouter } from './modules/router.js?v=6.0';

document.addEventListener('DOMContentLoaded', () => {
  // Initialize all modular components cleanly
  initParticleCanvas();
  initSeatTicker();
  initCourseTabs();
  initAIWeakAreaWidget();
  initRefundChecklist();
  initBlogHub();
  initNavbarScroll();
  initEnrollmentModal();
  initScrollAnimations();
  initRouter();
});
