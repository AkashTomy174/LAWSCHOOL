/* ==========================================================================
   MODULE: Seat Ticker & Scarcity Tracker
   ========================================================================== */

export function initSeatTicker() {
  const seatsLeftElem = document.getElementById('seats-remaining-count');
  if (seatsLeftElem) {
    setInterval(() => {
      seatsLeftElem.style.transform = 'scale(1.25)';
      seatsLeftElem.style.color = '#f6d365';
      setTimeout(() => {
        seatsLeftElem.style.transform = 'scale(1)';
        seatsLeftElem.style.color = 'var(--gold-primary)';
      }, 450);
    }, 10000);
  }
}
