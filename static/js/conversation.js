/* ==========================================================================
   conversation.js
   Manages the conversation page: session init, message exchange, feedback
   popovers, scenario sidebar, and session end flow.
   ========================================================================== */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let sessionId = null;
  let isWaiting = false;

  // ---------------------------------------------------------------------------
  // DOM refs — resolved after DOMContentLoaded
  // ---------------------------------------------------------------------------

  let chatThread;
  let chatInput;
  let sendBtn;
  let chatArea;

  // ---------------------------------------------------------------------------
  // URL params
  // ---------------------------------------------------------------------------

  function getParams() {
    const params = new URLSearchParams(window.location.search);
    return {
      scenarioId: params.get('scenario_id'),
      learnerId: params.get('learner_id') || '1',
      resumeSessionId: params.get('session_id'),
    };
  }

  // ---------------------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------------------

  /**
   * Build a chat message element.
   * For learner messages, the wrapper has position:relative to anchor feedback.
   * @param {'ai'|'learner'} role
   * @param {string} text
   * @param {string} [senderLabel]
   * @returns {HTMLElement}
   */
  function buildMessage(role, text, senderLabel) {
    const wrapper = document.createElement('div');
    wrapper.className = `chat-message chat-message--${role}`;

    if (senderLabel) {
      const sender = document.createElement('span');
      sender.className = 'chat-sender text-xs';
      sender.textContent = senderLabel;
      wrapper.appendChild(sender);
    }

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = text;
    wrapper.appendChild(bubble);

    return wrapper;
  }

  /**
   * Attach a feedback indicator (emoji-react style) to a learner message.
   * Shows a small colored dot; on hover/click a popover with details appears.
   * @param {HTMLElement} messageEl — the .chat-message--learner wrapper
   * @param {{ feedback_type: string, corrected_form: string, error_detail: string }} feedback
   */
  function attachFeedback(messageEl, feedback) {
    const bubble = messageEl.querySelector('.chat-bubble');
    if (!bubble) return;

    // Determine type and text
    const type = feedback.feedback_type || 'recast';
    let feedbackText = '';
    switch (type) {
      case 'recast':
        feedbackText = feedback.corrected_form || '';
        break;
      case 'prompt':
      case 'metalinguistic_cue':
        feedbackText = feedback.error_detail || '';
        break;
      default:
        feedbackText = feedback.corrected_form || feedback.error_detail || '';
    }

    if (!feedbackText) return;

    // Create indicator dot
    const indicator = document.createElement('button');
    indicator.className = `feedback-indicator feedback-indicator--${type}`;
    indicator.setAttribute('aria-label', 'View feedback');
    indicator.setAttribute('aria-expanded', 'false');
    indicator.type = 'button';

    // Create popover
    const popover = document.createElement('div');
    popover.className = `feedback-popover feedback-popover--${type}`;
    popover.setAttribute('role', 'tooltip');
    popover.textContent = feedbackText;

    // Toggle on click/tap
    indicator.addEventListener('click', function (e) {
      e.stopPropagation();
      const isOpen = popover.classList.contains('feedback-popover--visible');
      closeAllPopovers();
      if (!isOpen) {
        popover.classList.add('feedback-popover--visible');
        indicator.setAttribute('aria-expanded', 'true');
      }
    });

    // Show on hover (desktop)
    indicator.addEventListener('mouseenter', function () {
      popover.classList.add('feedback-popover--visible');
      indicator.setAttribute('aria-expanded', 'true');
    });
    indicator.addEventListener('mouseleave', function () {
      popover.classList.remove('feedback-popover--visible');
      indicator.setAttribute('aria-expanded', 'false');
    });

    bubble.style.position = 'relative';
    bubble.appendChild(indicator);
    bubble.appendChild(popover);
  }

  /**
   * Attach a positive "correct" indicator to a learner message.
   * Shows a green checkmark dot and a brief flash animation on the bubble.
   * @param {HTMLElement} messageEl — the .chat-message--learner wrapper
   */
  function attachCorrect(messageEl) {
    var bubble = messageEl.querySelector('.chat-bubble');
    if (!bubble) return;

    // Green checkmark indicator
    var indicator = document.createElement('span');
    indicator.className = 'feedback-indicator feedback-indicator--correct';
    indicator.setAttribute('aria-label', 'Good response');

    bubble.style.position = 'relative';
    bubble.appendChild(indicator);

    // Flash animation on the bubble
    bubble.classList.add('chat-bubble--correct-flash');
  }

  /**
   * Highlight above-level vocabulary in an AI message bubble.
   * Wraps matching words in clickable <mark> tags with tooltips
   * showing the base form (lemma).
   * @param {HTMLElement} messageEl — the .chat-message--ai wrapper
   * @param {string[]} vocabHelp — items like "dérouler (dérouler)"
   */
  function highlightVocab(messageEl, vocabHelp) {
    var bubble = messageEl.querySelector('.chat-bubble');
    if (!bubble) return;

    // Build a map of surface form → lemma from "surface (lemma)" entries
    var wordMap = {};
    vocabHelp.forEach(function (entry) {
      var parts = entry.match(/^(.+?) \((.+?)\)$/);
      if (parts) {
        wordMap[parts[1].toLowerCase()] = parts[2];
      }
    });

    var words = Object.keys(wordMap);
    if (!words.length) return;

    // Escape for regex and build a pattern
    var escaped = words.map(function (w) {
      return w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    });
    var pattern = new RegExp('\\b(' + escaped.join('|') + ')\\b', 'gi');

    bubble.innerHTML = bubble.textContent.replace(pattern, function (match) {
      var lemma = wordMap[match.toLowerCase()] || match;
      return '<mark class="vocab-highlight" data-lemma="' + lemma + '">' + match + '</mark>';
    });

    // Attach hover tooltips to each highlight
    bubble.querySelectorAll('.vocab-highlight').forEach(function (mark) {
      var tooltip = document.createElement('span');
      tooltip.className = 'vocab-tooltip';
      tooltip.textContent = mark.dataset.lemma;
      mark.appendChild(tooltip);
    });
  }

  /** Close all open feedback popovers */
  function closeAllPopovers() {
    document.querySelectorAll('.feedback-popover--visible').forEach(function (el) {
      el.classList.remove('feedback-popover--visible');
    });
    document.querySelectorAll('.feedback-indicator[aria-expanded="true"]').forEach(function (el) {
      el.setAttribute('aria-expanded', 'false');
    });
  }

  /**
   * Build the typing indicator element.
   * @returns {HTMLElement}
   */
  function buildTypingIndicator() {
    const wrapper = document.createElement('div');
    wrapper.className = 'chat-message chat-message--ai';
    wrapper.id = 'typing-indicator';

    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';

    for (let i = 0; i < 3; i++) {
      const dot = document.createElement('span');
      dot.className = 'typing-indicator__dot';
      indicator.appendChild(dot);
    }

    wrapper.appendChild(indicator);
    return wrapper;
  }

  /**
   * Build an error message bubble.
   * @param {string} text
   * @returns {HTMLElement}
   */
  function buildErrorMessage(text) {
    return buildMessage('ai', text, 'Error');
  }

  /**
   * Append an element to the chat thread and scroll to the bottom.
   * @param {HTMLElement} el
   */
  function appendToChat(el) {
    chatThread.appendChild(el);
    scrollToBottom();
  }

  function scrollToBottom() {
    if (chatThread) {
      chatThread.scrollTop = chatThread.scrollHeight;
    }
  }

  // ---------------------------------------------------------------------------
  // Level badge helper
  // ---------------------------------------------------------------------------

  function levelBadgeClass(level) {
    const normalised = (level || '').toLowerCase().replace(/\s/g, '');
    const allowed = ['a1', 'a2', 'b1', 'b2'];
    return allowed.includes(normalised) ? `level-badge--${normalised}` : 'level-badge--a1';
  }

  // ---------------------------------------------------------------------------
  // Sidebar / mobile scenario panel
  // ---------------------------------------------------------------------------

  /**
   * Populate both the desktop sidebar and mobile scenario panel.
   * @param {object} scenario — from the start-session API response
   */
  function populateScenario(scenario) {
    const role = scenario.ai_role || 'Partner';
    const desc = scenario.description || '';
    const level = (scenario.cefr_level || 'A1').toUpperCase();
    const cls = levelBadgeClass(level);
    const situation = scenario.situation || '';

    // Desktop sidebar
    const sidebarRole = document.getElementById('sidebar-role');
    const sidebarDesc = document.getElementById('sidebar-desc');
    const sidebarLevel = document.getElementById('sidebar-level');
    const sidebarSituation = document.getElementById('sidebar-situation');
    const sidebarChips = document.getElementById('sidebar-topic-chips');

    if (sidebarRole) sidebarRole.textContent = role;
    if (sidebarDesc) sidebarDesc.textContent = desc;
    if (sidebarLevel) {
      sidebarLevel.textContent = level;
      sidebarLevel.className = `level-badge text-xs ${cls}`;
    }
    if (sidebarSituation) {
      sidebarSituation.textContent = situation.charAt(0).toUpperCase() + situation.slice(1);
    }

    // Mobile panel
    const mobileRole = document.getElementById('mobile-scenario-role');
    const mobileLevel = document.getElementById('mobile-scenario-level');
    const mobileDesc = document.getElementById('mobile-scenario-desc');
    const mobileChips = document.getElementById('mobile-topic-chips');

    if (mobileRole) mobileRole.textContent = role;
    if (mobileLevel) {
      mobileLevel.textContent = level;
      mobileLevel.className = `level-badge text-xs ${cls}`;
    }
    if (mobileDesc) mobileDesc.textContent = desc;

    // Topic suggestion chips — prefer topic_suggestions, fall back to target_structures
    const suggestions = scenario.topic_suggestions || scenario.target_structures;
    let topics = [];
    if (Array.isArray(suggestions)) {
      topics = suggestions;
    } else if (typeof suggestions === 'string' && suggestions) {
      topics = suggestions.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    }

    [sidebarChips, mobileChips].forEach(function (container) {
      if (!container) return;
      container.innerHTML = '';
      topics.forEach(function (topic) {
        const chip = document.createElement('span');
        chip.className = 'label';
        chip.textContent = topic;
        container.appendChild(chip);
      });
    });

    // Store role for message labels
    window.__aiRole = role;
  }

  // ---------------------------------------------------------------------------
  // Input state
  // ---------------------------------------------------------------------------

  function disableInput() {
    isWaiting = true;
    chatInput.disabled = true;
    sendBtn.disabled = true;
  }

  function enableInput() {
    isWaiting = false;
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }

  // ---------------------------------------------------------------------------
  // API calls
  // ---------------------------------------------------------------------------

  async function startSession(learnerId, scenarioId) {
    const response = await fetch('/api/conversation/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        learner_id: Number(learnerId),
        scenario_id: Number(scenarioId),
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to start session (${response.status})`);
    }

    return response.json();
  }

  async function sendMessage(message) {
    const response = await fetch(`/api/conversation/${sessionId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error(`Message failed (${response.status})`);
    }

    return response.json();
  }

  async function endSession() {
    const response = await fetch(`/api/conversation/${sessionId}/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Could not end session (${response.status})`);
    }

    return response.json();
  }

  // ---------------------------------------------------------------------------
  // Session summary
  // ---------------------------------------------------------------------------

  /**
   * Count learner messages and tally error types from the chat thread DOM.
   * We read from the DOM (feedback indicators) rather than re-parsing the
   * transcript, which the server already processed.
   * @returns {{ messageCount: number, errors: Record<string, number> }}
   */
  function collectSessionStats() {
    const learnerMessages = chatThread
      ? chatThread.querySelectorAll('.chat-message--learner').length
      : 0;

    const errors = {};
    if (chatThread) {
      chatThread.querySelectorAll('.feedback-indicator').forEach(function (el) {
        const classes = Array.from(el.classList);
        const typeClass = classes.find(function (c) {
          return c.startsWith('feedback-indicator--') && c !== 'feedback-indicator--correct';
        });
        if (typeClass) {
          const type = typeClass.replace('feedback-indicator--', '');
          errors[type] = (errors[type] || 0) + 1;
        }
      });
    }

    return { messageCount: learnerMessages, errors };
  }

  /**
   * Render an error type name as a readable label.
   * @param {string} type
   * @returns {string}
   */
  function errorTypeLabel(type) {
    const labels = {
      recast: 'Recasts (form correction)',
      prompt: 'Prompts (elicitation)',
      metalinguistic_cue: 'Grammar cues',
    };
    return labels[type] || type;
  }

  function showSummaryPanel(data) {
    const summaryText = data.summary || '';

    const overlay = document.getElementById('session-summary-overlay');
    if (!overlay) return;

    // Populate subtitle
    const subtitle = document.getElementById('summary-subtitle');
    if (subtitle) {
      const { messageCount } = collectSessionStats();
      subtitle.textContent = messageCount === 1
        ? '1 message sent this session'
        : `${messageCount} messages sent this session`;
    }

    // Populate stats
    const statsEl = document.getElementById('summary-stats');
    if (statsEl) {
      const { errors } = collectSessionStats();
      const errorEntries = Object.entries(errors);

      if (errorEntries.length === 0) {
        const noErrors = document.createElement('p');
        noErrors.className = 'session-summary-stats__clean';
        noErrors.textContent = 'No errors detected — great work!';
        statsEl.appendChild(noErrors);
      } else {
        errorEntries.forEach(function (entry) {
          const type = entry[0];
          const count = entry[1];
          const row = document.createElement('div');
          row.className = 'session-summary-stats__row';

          const label = document.createElement('span');
          label.className = 'session-summary-stats__label';
          label.textContent = errorTypeLabel(type);

          const value = document.createElement('span');
          value.className = 'session-summary-stats__value';
          value.textContent = count;

          row.appendChild(label);
          row.appendChild(value);
          statsEl.appendChild(row);
        });
      }
    }

    // Populate AI narrative feedback
    const feedbackEl = document.getElementById('summary-feedback');
    if (feedbackEl && summaryText) {
      feedbackEl.textContent = summaryText;
    } else if (feedbackEl) {
      feedbackEl.hidden = true;
    }

    // Preserve learner_id on "New conversation" link
    const newConvBtn = document.getElementById('new-conversation-btn');
    if (newConvBtn) {
      const { learnerId } = getParams();
      if (learnerId) {
        newConvBtn.href = `play.html?learner_id=${learnerId}`;
      }
    }

    // Show modal
    overlay.hidden = false;
    overlay.focus();

    // Re-replace feather icons inside modal
    if (typeof feather !== 'undefined') {
      feather.replace();
    }

    // Disable chat input
    const inputArea = document.querySelector('.chat-input-area');
    if (inputArea) inputArea.classList.add('conversation-ended');
  }

  // ---------------------------------------------------------------------------
  // End conversation
  // ---------------------------------------------------------------------------

  function setEndButtonsDisabled(disabled) {
    ['end-btn', 'end-btn-mobile'].forEach(function (id) {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = disabled;
    });
  }

  async function handleEndConversation() {
    setEndButtonsDisabled(true);
    disableInput();

    try {
      const data = await endSession();
      showSummaryPanel(data);
    } catch (err) {
      appendToChat(buildErrorMessage('Could not end the session. Please try again.'));
      enableInput();
      setEndButtonsDisabled(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Message submission
  // ---------------------------------------------------------------------------

  async function handleSend() {
    if (isWaiting || !sessionId) return;

    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';
    disableInput();

    // Append learner message
    const learnerMsg = buildMessage('learner', text, 'You');
    appendToChat(learnerMsg);

    // Show typing indicator
    const typingEl = buildTypingIndicator();
    appendToChat(typingEl);

    try {
      const data = await sendMessage(text);

      // Remove typing indicator
      const existing = document.getElementById('typing-indicator');
      if (existing) existing.remove();

      // Append AI response — highlight any above-level vocabulary
      const aiName = window.__aiRole || 'Partner';
      const aiMsg = buildMessage('ai', data.message, aiName);
      if (data.vocab_help && data.vocab_help.length > 0) {
        highlightVocab(aiMsg, data.vocab_help);
      }
      appendToChat(aiMsg);

      // Attach feedback indicator — always show, positive or corrective
      if (data.feedback && data.feedback.error_found) {
        attachFeedback(learnerMsg, data.feedback);
      } else {
        attachCorrect(learnerMsg);
      }
    } catch (err) {
      const existing = document.getElementById('typing-indicator');
      if (existing) existing.remove();
      appendToChat(buildErrorMessage('Something went wrong. Please try again.'));
    }

    enableInput();
  }

  // ---------------------------------------------------------------------------
  // Page init
  // ---------------------------------------------------------------------------

  async function init() {
    chatThread = document.getElementById('chat-thread');
    chatInput = document.getElementById('chat-input');
    sendBtn = document.getElementById('send-btn');
    chatArea = document.querySelector('.conversation-layout__chat');

    // Wire up send button and Enter key
    sendBtn.addEventListener('click', handleSend);
    chatInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });

    // End button (desktop sidebar)
    const endBtn = document.getElementById('end-btn');
    if (endBtn) endBtn.addEventListener('click', handleEndConversation);

    // End button (mobile, in chat input row)
    const endBtnMobile = document.getElementById('end-btn-mobile');
    if (endBtnMobile) endBtnMobile.addEventListener('click', handleEndConversation);

    // Close popovers and vocab tooltips when clicking elsewhere
    document.addEventListener('click', function () {
      closeAllPopovers();
      document.querySelectorAll('.vocab-tooltip--visible').forEach(function (el) {
        el.classList.remove('vocab-tooltip--visible');
      });
    });

    // Replace feather icons
    if (typeof feather !== 'undefined') {
      feather.replace();
    }

    // Read URL params
    const { learnerId, scenarioId, resumeSessionId } = getParams();

    // --- Resume path: session_id in URL ---
    if (resumeSessionId && !scenarioId) {
      sessionId = Number(resumeSessionId);
      appendToChat(
        buildMessage('ai', 'Welcome back! Continue the conversation where you left off.', 'Partner')
      );
      enableInput();
      if (typeof feather !== 'undefined') {
        feather.replace();
      }
      return;
    }

    if (!scenarioId) {
      appendToChat(
        buildErrorMessage('No scenario selected. Please return to the dashboard and choose a scenario.')
      );
      disableInput();
      return;
    }

    disableInput();

    const loadingEl = buildTypingIndicator();
    appendToChat(loadingEl);

    try {
      const data = await startSession(learnerId, scenarioId);

      const existingLoading = document.getElementById('typing-indicator');
      if (existingLoading) existingLoading.remove();

      sessionId = data.session_id;

      // Populate scenario sidebar + mobile panel
      if (data.scenario) {
        populateScenario(data.scenario);
      }

      // Append AI opening message
      appendToChat(buildMessage('ai', data.message, window.__aiRole || 'Partner'));

    } catch (err) {
      const existingLoading = document.getElementById('typing-indicator');
      if (existingLoading) existingLoading.remove();
      appendToChat(
        buildErrorMessage('Could not start the conversation. Please check your connection and try again.')
      );
      return;
    }

    enableInput();

    // Re-replace feather icons after sidebar population
    if (typeof feather !== 'undefined') {
      feather.replace();
    }
  }

  // ---------------------------------------------------------------------------
  // Bootstrap
  // ---------------------------------------------------------------------------

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
