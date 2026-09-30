/* ==========================================================================
   MODULE: Admission Commitment Policy (100% Fee Refund) Checklist Tracker
   ========================================================================== */

export function initRefundChecklist() {
  const checkboxes = document.querySelectorAll('.refund-checkbox');
  const statusBadge = document.getElementById('refund-status-badge');
  const progressText = document.getElementById('refund-progress-text');

  checkboxes.forEach(cb => {
    cb.addEventListener('change', () => {
      const checkedCount = document.querySelectorAll('.refund-checkbox:checked').length;
      const total = checkboxes.length;

      if (progressText) {
        progressText.textContent = `${checkedCount} of ${total} Criteria Satisfied`;
      }

      if (checkedCount === total) {
        statusBadge.innerHTML = `🏆 100% TUITION FEE REFUND COMMITMENT ACTIVATED`;
        statusBadge.style.background = 'rgba(16, 185, 129, 0.25)';
        statusBadge.style.color = '#34d399';
        statusBadge.style.borderColor = '#10b981';
      } else {
        statusBadge.innerHTML = `⚠️ COMPLETE ALL CRITERIA TO LOCK COMMITMENT`;
        statusBadge.style.background = 'rgba(212, 175, 55, 0.15)';
        statusBadge.style.color = '#f3c649';
        statusBadge.style.borderColor = 'var(--gold-primary)';
      }
    });
  });
}
