/**
 * review.js — Spaced-repetition review session for Apprendre.
 *
 * Reads learner_id from localStorage (key: apprendre_learner_id).
 * Fetches due cards from GET /api/drills/due?learner_id=X.
 * If no cards exist at all, seeds them via POST /api/drills/seed?learner_id=X first.
 * Drives the reveal-and-rate flow, then shows a completion screen.
 */

(function () {
  'use strict';

  var LEARNER_ID_KEY = 'apprendre_learner_id';
  var DEFAULT_LEARNER_ID = 1; // fallback for dev when localStorage is empty

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  var state = {
    learnerId: null,
    cards: [],          // due cards fetched from the API
    currentIndex: 0,    // index into state.cards
    completedCount: 0,  // how many cards have been rated this session
    totalDue: 0,        // how many were due at session start
    startTime: null,    // Date for session duration
  };

  // ---------------------------------------------------------------------------
  // DOM references (resolved once on DOMContentLoaded)
  // ---------------------------------------------------------------------------

  var el = {};

  function resolveElements() {
    el.progressText   = document.getElementById('review-progress-text');
    el.progressFill   = document.getElementById('review-progress-fill');
    el.progressBar    = el.progressFill && el.progressFill.parentElement;
    el.reviewCard     = document.getElementById('review-card');
    el.reviewPrompt   = document.getElementById('review-prompt');
    el.reviewContext  = document.getElementById('review-context');
    el.answerArea     = document.getElementById('review-answer-area');
    el.answerInput    = document.getElementById('review-answer');
    el.revealBtn      = document.getElementById('reveal-btn');
    el.revealed       = document.getElementById('review-revealed');
    el.correctAnswer  = document.getElementById('review-correct-answer');
    el.ratingButtons     = document.querySelectorAll('[data-rating]');
    el.reviewSection     = document.querySelector('section[aria-label="Review card"]');
    el.progressWrapper   = document.getElementById('review-progress-wrapper');
    el.completeSection   = document.getElementById('review-complete');
    el.completeSummary   = document.getElementById('review-complete-summary');
    el.errorBanner       = document.getElementById('review-error');
    el.loadingState      = document.getElementById('review-loading');
    el.emptyState        = document.getElementById('review-empty');
  }

  // ---------------------------------------------------------------------------
  // API helpers
  // ---------------------------------------------------------------------------

  function apiGet(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) {
        return res.json().then(function (body) {
          throw new Error(body.detail || ('API error ' + res.status));
        });
      }
      return res.json();
    });
  }

  function apiPost(url, data) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: data !== undefined ? JSON.stringify(data) : undefined,
    }).then(function (res) {
      if (!res.ok) {
        return res.json().then(function (body) {
          throw new Error(body.detail || ('API error ' + res.status));
        });
      }
      return res.json();
    });
  }

  // ---------------------------------------------------------------------------
  // Visibility helpers
  // ---------------------------------------------------------------------------

  function show(element) {
    if (element) element.hidden = false;
  }

  function hide(element) {
    if (element) element.hidden = true;
  }

  function setText(element, text) {
    if (element) element.textContent = text;
  }

  // ---------------------------------------------------------------------------
  // Progress bar
  // ---------------------------------------------------------------------------

  function updateProgress() {
    var total = state.totalDue;
    var done = state.completedCount;
    var pct = total > 0 ? Math.round((done / total) * 100) : 0;

    setText(el.progressText, done + ' of ' + total);
    if (el.progressFill) {
      el.progressFill.style.width = pct + '%';
    }
    if (el.progressBar) {
      el.progressBar.setAttribute('aria-valuenow', pct);
    }
  }

  // ---------------------------------------------------------------------------
  // Card content extraction
  // ---------------------------------------------------------------------------

  /**
   * Extract the French prompt and English answer from a card's content_item.
   *
   * A1 chunks store their data inside content_item.content (parsed content_json).
   * Fields used: chunk (French), translation (English), example_sentence, example_translation.
   */
  function extractCardContent(card) {
    var ci = card.content_item || {};
    var content = ci.content || {};

    var french = content.chunk || content.french || '(no French text)';
    var english = content.translation || content.english || '(no translation)';
    var exampleFr = content.example_sentence || '';
    var exampleEn = content.example_translation || '';
    var situation = ci.situation || content.situation || '';
    var notes = content.notes || '';

    return {
      french: french,
      english: english,
      exampleFr: exampleFr,
      exampleEn: exampleEn,
      situation: situation,
      notes: notes,
    };
  }

  // ---------------------------------------------------------------------------
  // Render current card
  // ---------------------------------------------------------------------------

  function renderCard(card) {
    var data = extractCardContent(card);

    // Prompt: show the English translation — learner recalls French
    setText(el.reviewPrompt, 'How do you say: "' + data.english + '"');

    // Context sentence (situation label if no example)
    if (data.exampleEn) {
      setText(el.reviewContext, 'Example: ' + data.exampleEn);
      show(el.reviewContext);
    } else if (data.situation) {
      setText(el.reviewContext, 'Situation: ' + data.situation);
      show(el.reviewContext);
    } else {
      hide(el.reviewContext);
    }

    // Correct answer panel
    var answerHtml = '<strong>' + escapeHtml(data.french) + '</strong>';
    if (data.exampleFr) {
      answerHtml += '<p class="text-sm" style="margin-top: var(--ply-space-xs);">'
        + escapeHtml(data.exampleFr) + '</p>';
    }
    if (data.notes) {
      answerHtml += '<p class="text-sm" style="margin-top: var(--ply-space-xs); color: var(--ply-color-secondary);">'
        + escapeHtml(data.notes) + '</p>';
    }
    if (el.correctAnswer) {
      el.correctAnswer.innerHTML = answerHtml;
    }

    // Reset to pre-reveal state
    if (el.answerInput) el.answerInput.value = '';
    show(el.answerArea);
    hide(el.revealed);

    // Disable rating buttons until answer is revealed
    el.ratingButtons.forEach(function (btn) {
      btn.disabled = true;
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ---------------------------------------------------------------------------
  // Reveal answer
  // ---------------------------------------------------------------------------

  function revealAnswer() {
    hide(el.answerArea);
    show(el.revealed);

    // Enable rating buttons
    el.ratingButtons.forEach(function (btn) {
      btn.disabled = false;
    });

    // Focus the first rating button for keyboard users
    var firstBtn = document.querySelector('[data-rating="1"]');
    if (firstBtn) firstBtn.focus();
  }

  // ---------------------------------------------------------------------------
  // Submit rating
  // ---------------------------------------------------------------------------

  function submitRating(ratingLabel) {
    var card = state.cards[state.currentIndex];
    if (!card) return;

    // Disable all rating buttons while the request is in flight
    el.ratingButtons.forEach(function (btn) {
      btn.disabled = true;
    });

    apiPost('/api/drills/' + card.id + '/rate', { rating: ratingLabel })
      .then(function () {
        state.completedCount += 1;
        state.currentIndex += 1;
        advanceSession();
      })
      .catch(function (err) {
        showError('Could not save rating: ' + err.message);
        // Re-enable buttons so the user can retry
        el.ratingButtons.forEach(function (btn) {
          btn.disabled = false;
        });
      });
  }

  // ---------------------------------------------------------------------------
  // Advance session
  // ---------------------------------------------------------------------------

  function advanceSession() {
    updateProgress();

    if (state.currentIndex >= state.cards.length) {
      showComplete();
      return;
    }

    renderCard(state.cards[state.currentIndex]);
    if (el.answerInput) el.answerInput.focus();
  }

  // ---------------------------------------------------------------------------
  // Completion screen
  // ---------------------------------------------------------------------------

  function showComplete() {
    hide(el.reviewSection);
    hide(el.loadingState);
    hide(el.emptyState);
    hide(el.progressWrapper);
    show(el.completeSection);

    var elapsed = state.startTime
      ? Math.round((Date.now() - state.startTime) / 60000)
      : 0;
    var timeText = elapsed >= 1 ? 'about ' + elapsed + ' minute' + (elapsed !== 1 ? 's' : '') : 'less than a minute';

    if (el.completeSummary) {
      el.completeSummary.textContent =
        'You reviewed ' + state.completedCount + ' card' +
        (state.completedCount !== 1 ? 's' : '') +
        ' in ' + timeText + '.';
    }
  }

  // ---------------------------------------------------------------------------
  // Empty state (no cards due)
  // ---------------------------------------------------------------------------

  function showEmptyState() {
    hide(el.reviewSection);
    hide(el.loadingState);
    hide(el.completeSection);
    show(el.emptyState);
  }

  // ---------------------------------------------------------------------------
  // Error banner
  // ---------------------------------------------------------------------------

  function showError(message) {
    if (!el.errorBanner) return;
    el.errorBanner.textContent = message;
    show(el.errorBanner);
  }

  function hideError() {
    hide(el.errorBanner);
  }

  // ---------------------------------------------------------------------------
  // Session bootstrap
  // ---------------------------------------------------------------------------

  function startSession(learnerId) {
    state.learnerId = learnerId;
    state.startTime = Date.now();

    show(el.loadingState);
    hide(el.reviewSection);
    hide(el.completeSection);
    hide(el.emptyState);
    hideError();

    apiGet('/api/drills/due?learner_id=' + learnerId)
      .then(function (data) {
        var cards = data.cards || [];
        var stats = data.stats || {};

        if (cards.length === 0 && stats.total === 0) {
          // No cards at all — seed first, then re-fetch
          return seedAndStart(learnerId);
        }

        if (cards.length === 0) {
          // Cards exist but none are due today
          hide(el.loadingState);
          showEmptyState();
          return;
        }

        loadCards(cards);
      })
      .catch(function (err) {
        hide(el.loadingState);
        showError('Could not load review cards: ' + err.message);
      });
  }

  function seedAndStart(learnerId) {
    return apiPost('/api/drills/seed?learner_id=' + learnerId)
      .then(function () {
        return apiGet('/api/drills/due?learner_id=' + learnerId);
      })
      .then(function (data) {
        var cards = data.cards || [];

        if (cards.length === 0) {
          hide(el.loadingState);
          showEmptyState();
          return;
        }

        loadCards(cards);
      });
  }

  function loadCards(cards) {
    state.cards = cards;
    state.currentIndex = 0;
    state.completedCount = 0;
    state.totalDue = cards.length;

    updateProgress();

    hide(el.loadingState);
    hide(el.completeSection);
    hide(el.emptyState);
    show(el.progressWrapper);
    show(el.reviewSection);

    renderCard(state.cards[0]);
    if (el.answerInput) el.answerInput.focus();
  }

  // ---------------------------------------------------------------------------
  // Event binding
  // ---------------------------------------------------------------------------

  function bindEvents() {
    if (el.revealBtn) {
      el.revealBtn.addEventListener('click', revealAnswer);
    }

    if (el.answerInput) {
      el.answerInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          revealAnswer();
        }
      });
    }

    el.ratingButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var ratingInt = parseInt(btn.getAttribute('data-rating'), 10);
        var labelMap = { 1: 'again', 2: 'hard', 3: 'good', 4: 'easy' };
        var label = labelMap[ratingInt];
        if (label) submitRating(label);
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', function () {
    resolveElements();
    bindEvents();

    var storedId = localStorage.getItem(LEARNER_ID_KEY);
    var learnerId = storedId ? parseInt(storedId, 10) : DEFAULT_LEARNER_ID;

    startSession(learnerId);
  });

})();
