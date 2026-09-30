/* ==========================================================================
   MODULE: AI Weak Area Alert System Widget Simulator
   ========================================================================== */

const SUBJECT_DATA = {
  "admin-law": {
    name: "Administrative Law & Judicial Review",
    score: "58%",
    alertText: "URGENT REVISION REQUIRED",
    alertClass: "alert-urgent",
    fillWidth: "58%",
    action: "Review 15 Landmark Writ Jurisdiction Cases & Attempt 30 MCQ Diagnostic Set."
  },
  "const-law": {
    name: "Constitutional Fundamental Rights",
    score: "88%",
    alertText: "OPTIMAL ACCURACY",
    alertClass: "alert-warning",
    fillWidth: "88%",
    action: "Maintain streak with daily 10-minute speed revision quizzes."
  },
  "legal-reasoning": {
    name: "Legal Aptitude & Principle-Fact Qs",
    score: "64%",
    alertText: "ACCURACY DROPPING UNDER TIME PRESSURE",
    alertClass: "alert-urgent",
    fillWidth: "64%",
    action: "Execute 25 Timed Principle-Fact Sets to improve time-per-question ratio."
  },
  "criminal-law": {
    name: "Bharatiya Nyaya Sanhita (BNS) Defences",
    score: "72%",
    alertText: "PRACTICE ADVISED",
    alertClass: "alert-warning",
    fillWidth: "72%",
    action: "Review General Exceptions under BNS 2023 and solve previous 10 yrs solved papers."
  }
};

export function initAIWeakAreaWidget() {
  const subjectBtns = document.querySelectorAll('.subject-select-btn');
  const subjNameElem = document.getElementById('ai-subj-name');
  const subjScoreElem = document.getElementById('ai-subj-score');
  const alertBadgeElem = document.getElementById('ai-alert-badge');
  const progressFill = document.getElementById('ai-progress-fill');
  const actionTextElem = document.getElementById('ai-action-text');

  subjectBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      subjectBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const key = btn.getAttribute('data-subject');
      const data = SUBJECT_DATA[key];

      if (data && subjNameElem) {
        subjNameElem.textContent = data.name;
        subjScoreElem.textContent = data.score;
        alertBadgeElem.textContent = data.alertText;
        alertBadgeElem.className = `alert-badge ${data.alertClass}`;
        progressFill.style.width = data.fillWidth;
        actionTextElem.textContent = data.action;
      }
    });
  });
}
