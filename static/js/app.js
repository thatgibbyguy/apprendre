/**
 * Apprendre — Frontend JavaScript
 * Minimal vanilla JS for UI interactions.
 * No frameworks. fetch for API calls, DOM manipulation for interactivity.
 */

import '../scss/app.scss';

(function () {
  'use strict';

  // ─── Feather Icons ───
  document.addEventListener('DOMContentLoaded', function () {
    if (typeof feather !== 'undefined') {
      feather.replace();
    }
  });

  // ─── Dark Mode Toggle ───
  function toggleTheme() {
    var html = document.documentElement;
    var current = html.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('apprendre-theme', next);

    // Update toggle button icons
    updateThemeIcons(next);
  }

  function updateThemeIcons(theme) {
    var toggles = document.querySelectorAll('#theme-toggle, #theme-toggle-mobile');
    toggles.forEach(function (btn) {
      var icon = btn.querySelector('svg');
      if (icon) {
        // Replace feather icon: moon for light, sun for dark
        var iconName = theme === 'dark' ? 'sun' : 'moon';
        btn.innerHTML = btn.textContent.includes('Dark mode')
          ? '<i data-feather="' + iconName + '"></i> ' + (theme === 'dark' ? 'Light mode' : 'Dark mode')
          : '<i data-feather="' + iconName + '"></i>';
        if (typeof feather !== 'undefined') {
          feather.replace();
        }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Restore saved theme
    var saved = localStorage.getItem('apprendre-theme');
    if (saved) {
      document.documentElement.setAttribute('data-theme', saved);
      updateThemeIcons(saved);
    }

    // Bind toggle buttons
    var toggle = document.getElementById('theme-toggle');
    if (toggle) toggle.addEventListener('click', toggleTheme);

    var toggleMobile = document.getElementById('theme-toggle-mobile');
    if (toggleMobile) toggleMobile.addEventListener('click', toggleTheme);
  });

  // ─── Chat Input Handling ───
  document.addEventListener('DOMContentLoaded', function () {
    var chatInput = document.getElementById('chat-input');
    var sendBtn = document.getElementById('send-btn');

    if (chatInput) {
      chatInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendChatMessage();
        }
      });
    }

    if (sendBtn) {
      sendBtn.addEventListener('click', sendChatMessage);
    }

    // Assessment input
    var assessmentInput = document.getElementById('assessment-input');
    var assessmentSend = document.getElementById('assessment-send');

    if (assessmentInput) {
      assessmentInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendAssessmentResponse();
        }
      });
    }

    if (assessmentSend) {
      assessmentSend.addEventListener('click', sendAssessmentResponse);
    }

    // Assessment start button
    var startBtn = document.getElementById('start-assessment');
    if (startBtn) {
      startBtn.addEventListener('click', startAssessment);
    }
  });

  function sendChatMessage() {
    var input = document.getElementById('chat-input');
    if (!input) return;

    var message = input.value.trim();
    if (!message) return;

    appendChatMessage('learner', message);
    input.value = '';
    input.focus();

    // TODO: POST to /api/conversation endpoint
    // sendToAPI('/api/conversation/message', { text: message });
  }

  function appendChatMessage(sender, text) {
    var thread = document.getElementById('chat-thread') || document.getElementById('assessment-thread');
    if (!thread) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'chat-message chat-message--' + sender;

    var label = document.createElement('span');
    label.className = 'chat-sender text-xs';
    label.setAttribute('aria-hidden', 'true');
    label.textContent = sender === 'learner' ? 'You' : 'Apprendre';

    var bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = text;

    wrapper.appendChild(label);
    wrapper.appendChild(bubble);
    thread.appendChild(wrapper);

    // Scroll to bottom
    var scrollParent = thread.closest('.conversation-layout__body') || thread.closest('.assessment-layout__body') || thread;
    scrollParent.scrollTop = scrollParent.scrollHeight;
  }

  // ─── Assessment Flow ───
  function startAssessment() {
    var welcome = document.getElementById('assessment-welcome');
    var thread = document.getElementById('assessment-thread');
    var inputArea = document.getElementById('assessment-input-area');

    if (welcome) welcome.hidden = true;
    if (thread) thread.hidden = false;
    if (inputArea) inputArea.hidden = false;

    // TODO: POST to /api/assessment/start to get first prompt
    appendChatMessage('ai', 'Parlez-moi de vous en francais. Tell me about yourself in French.');

    var input = document.getElementById('assessment-input');
    if (input) input.focus();
  }

  function sendAssessmentResponse() {
    var input = document.getElementById('assessment-input');
    if (!input) return;

    var message = input.value.trim();
    if (!message) return;

    appendChatMessage('learner', message);
    input.value = '';
    input.focus();

    // TODO: POST to /api/assessment/respond
    // The API will return the next prompt or the final level result
  }

  // ─── Review Flow ───
  document.addEventListener('DOMContentLoaded', function () {
    var revealBtn = document.getElementById('reveal-btn');
    if (revealBtn) {
      revealBtn.addEventListener('click', revealAnswer);
    }

    // Rating buttons
    var ratingBtns = document.querySelectorAll('[data-rating]');
    ratingBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var rating = parseInt(btn.getAttribute('data-rating'), 10);
        submitRating(rating);
      });
    });

    // Review answer input — reveal on Enter
    var reviewAnswer = document.getElementById('review-answer');
    if (reviewAnswer) {
      reviewAnswer.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          revealAnswer();
        }
      });
    }
  });

  function revealAnswer() {
    var answerArea = document.getElementById('review-answer-area');
    var revealed = document.getElementById('review-revealed');

    if (answerArea) answerArea.hidden = true;
    if (revealed) revealed.hidden = false;
  }

  function submitRating(rating) {
    // TODO: POST to /api/review/rate with card ID and rating
    // Then load the next card or show completion
    console.log('Rating submitted:', rating);
  }

  // ─── API Helpers (placeholders) ───

  /**
   * POST JSON to an API endpoint.
   * @param {string} url
   * @param {object} data
   * @returns {Promise<object>}
   */
  function postAPI(url, data) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(function (res) {
      if (!res.ok) throw new Error('API error: ' + res.status);
      return res.json();
    });
  }

  /**
   * GET JSON from an API endpoint.
   * @param {string} url
   * @returns {Promise<object>}
   */
  function getAPI(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('API error: ' + res.status);
      return res.json();
    });
  }

  // Expose for use in inline handlers if needed
  window.apprendre = {
    postAPI: postAPI,
    getAPI: getAPI,
    toggleTheme: toggleTheme
  };

})();
