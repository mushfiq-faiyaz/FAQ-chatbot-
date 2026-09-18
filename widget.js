/**
 * widget.js  —  Embeddable Floating Chat Widget
 * ================================================
 *
 * WHAT THIS FILE DOES:
 * This single JavaScript file is a fully self-contained chat widget. Drop it onto
 * any webpage with one <script> tag and it injects a floating button into the
 * bottom-right corner. Clicking the button opens a chat window where users can
 * type messages and receive responses from an AI backend.
 *
 * HOW IT IS STRUCTURED (AND WHY):
 * Everything — CSS, HTML, and JS logic — lives inside this one file. That is intentional.
 * The goal is "zero-friction embedding": the client pastes one line into their site and it
 * just works. No npm, no build step, no CDN dependencies to go down, no React bundle to
 * ship. This pattern is sometimes called a "bookmarklet-style" or "third-party widget"
 * and is how tools like Intercom, Drift, and HubSpot chat widgets work under the hood.
 *
 * WHY CSS VARIABLES:
 * Instead of hardcoding hex values like #4A90E2 all over the stylesheet, we declare them
 * once at the top as CSS custom properties (--myw-primary, etc.). This means a
 * developer can completely re-skin the widget for a new client in under 30 seconds, by
 * overriding just those variables — without touching any logic or risking breaking anything.
 *
 * WHY SCOPED CLASS NAMES (myw- PREFIX):
 * When this widget is injected into a client website, it shares the page with whatever
 * CSS that site already has. A class named ".header" or ".button" in our widget would
 * likely clash with the client own styles. Prefixing everything with "myw-" (short for
 * "my widget") acts like a poor-man CSS module — it creates a private namespace so our
 * styles only affect our own elements.
 *
 * BACKEND INTEGRATION:
 * The widget sends user messages to the backend API via HTTP POST (configured via API_URL).
 * It shows an animated typing indicator while awaiting the response, parses the JSON answer,
 * and includes graceful error handling if network or server errors occur.
 *
 * USAGE (embed on any page):
 *   <script src="widget.js"></script>
 *
 * PROJECT: RAG Vive FAQ Chatbot  |  widget.js  |  v1.0.0
 */

// IMMEDIATELY INVOKED FUNCTION EXPRESSION (IIFE)
// We wrap EVERYTHING in an IIFE for two reasons:
//  1. SCOPE ISOLATION: Any variable we declare lives only inside this function.
//     It can never accidentally overwrite a variable on the client global scope.
//  2. SELF-EXECUTION: It runs immediately when the browser parses the script tag,
//     so the widget initialises itself automatically — no external setup needed.
(function () {
  "use strict";

  // ==========================================================================
  // API CONFIGURATION
  // ==========================================================================
  // Endpoint URL for the backend chat API.
  // Update this URL when deploying to production (e.g. "https://api.yourdomain.com/chat").
  const API_URL = "http://localhost:8000/chat";

  // ==========================================================================
  // SECTION 1: CSS — Scoped styles injected into <head>
  // ==========================================================================
  // We create a <style> element and append it to <head> programmatically.
  // This is the standard way a third-party script injects its own CSS without
  // requiring the client to link a separate stylesheet.

  var css = `
    /*
      CSS CUSTOM PROPERTIES (DESIGN TOKENS)
      ======================================
      All colours, sizes, and fonts that a client might want to change are
      declared here as CSS variables on the :root pseudo-element.
      :root essentially means "the <html> element", so these variables are
      available globally throughout our injected stylesheet.

      TO RESKIN FOR A NEW CLIENT: override these AFTER widget.js loads:
        :root {
          --myw-primary:     #E8402A;
          --myw-bubble-user: #E8402A;
        }
    */

    :root {
      --myw-primary:          #4F8EF7;
      --myw-primary-dark:     #3a75d4;
      --myw-bubble-user:      #4F8EF7;
      --myw-bubble-user-text: #ffffff;
      --myw-bubble-bot:       #f1f3f6;
      --myw-bubble-bot-text:  #1a1a2e;
      --myw-bg:               #ffffff;
      --myw-header-bg:        #4F8EF7;
      --myw-header-text:      #ffffff;
      --myw-input-border:     #d1d9e6;
      --myw-shadow:           0 8px 32px rgba(0,0,0,0.18);
      --myw-radius:           16px;
      --myw-font:             -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    /*
      BOX-SIZING RESET FOR WIDGET
      ============================
      Ensure all elements inside the widget use border-box sizing so padding
      and borders do not add extra width on top of width calculations.
    */
    .myw-trigger-btn,
    .myw-trigger-btn *,
    .myw-window,
    .myw-window * {
      box-sizing: border-box;
    }

    /*
      FLOATING TRIGGER BUTTON
      ========================
      Fixed in the bottom-right corner.
      position:fixed means it stays anchored to the viewport even on scroll.
      z-index 2147483647 is the maximum possible — ensures it floats above
      everything on any client page, including modals and overlays.
      Max-width and right/bottom offsets respect viewport edges on narrow screens.
    */
    .myw-trigger-btn {
      position:         fixed;
      bottom:           max(16px, 4vw);
      right:            max(16px, 4vw);
      z-index:          2147483647;
      width:            60px;
      height:           60px;
      max-width:        calc(100vw - 32px);
      border-radius:    50%;
      background:       var(--myw-primary);
      border:           none;
      cursor:           pointer;
      display:          flex;
      align-items:      center;
      justify-content:  center;
      box-shadow:       0 4px 20px rgba(79,142,247,0.45);
      transition:       transform 0.2s ease, box-shadow 0.2s ease;
      outline:          none;
    }
    .myw-trigger-btn:hover {
      transform:  scale(1.08);
      box-shadow: 0 6px 28px rgba(79,142,247,0.55);
    }
    .myw-trigger-btn:active { transform: scale(0.95); }
    .myw-trigger-btn svg {
      width:  28px;
      height: 28px;
      fill:   white;
    }

    /*
      CHAT WINDOW
      ============
      Initially hidden (display:none). When toggled open, we switch to flex
      so the three internal regions (header, messages, input) stack vertically
      and fill the available height correctly.
      Width uses min(350px, calc(100vw - 40px)) to prevent overflowing narrow screens.
    */
    .myw-window {
      position:       fixed;
      bottom:         calc(max(16px, 4vw) + 72px);
      right:          max(16px, 4vw);
      z-index:        2147483646;
      width:          min(350px, calc(100vw - 40px));
      max-width:      calc(100vw - 20px);
      height:         min(500px, calc(100vh - 120px));
      background:     var(--myw-bg);
      border-radius:  var(--myw-radius);
      box-shadow:     var(--myw-shadow);
      display:        none;
      flex-direction: column;
      overflow:       hidden;
      font-family:    var(--myw-font);
    }
    .myw-window.myw-open {
      display:   flex;
      animation: myw-slideUp 0.25s ease;
    }
    @keyframes myw-slideUp {
      from { opacity: 0; transform: translateY(20px); }
      to   { opacity: 1; transform: translateY(0);    }
    }

    /* HEADER BAR */
    .myw-header {
      background:      var(--myw-header-bg);
      color:           var(--myw-header-text);
      padding:         14px 16px;
      display:         flex;
      align-items:     center;
      justify-content: space-between;
      flex-shrink:     0;
    }
    .myw-header-title {
      font-size:   15px;
      font-weight: 600;
      margin:      0;
      display:     flex;
      align-items: center;
      gap:         8px;
    }
    /* Pulsing green "online" dot */
    .myw-online-dot {
      width:         9px;
      height:        9px;
      border-radius: 50%;
      background:    #4ade80;
      display:       inline-block;
      animation:     myw-pulse 2s infinite;
    }
    @keyframes myw-pulse {
      0%, 100% { opacity: 1;   transform: scale(1);    }
      50%      { opacity: 0.6; transform: scale(0.85); }
    }
    .myw-close-btn {
      background:    transparent;
      border:        none;
      cursor:        pointer;
      color:         var(--myw-header-text);
      font-size:     20px;
      line-height:   1;
      padding:       2px 6px;
      border-radius: 6px;
      opacity:       0.85;
      transition:    opacity 0.15s, background 0.15s;
    }
    .myw-close-btn:hover { opacity: 1; background: rgba(255,255,255,0.18); }

    /*
      MESSAGES AREA
      ==============
      flex:1 means "take up all remaining vertical space after the header
      and input bar claim their natural height". overflow-y:auto adds a
      scrollbar only when messages overflow.
    */
    .myw-messages {
      flex:           1;
      overflow-y:     auto;
      padding:        16px 14px;
      display:        flex;
      flex-direction: column;
      gap:            10px;
      scrollbar-width: thin;
      scrollbar-color: #ccd6f0 transparent;
    }
    .myw-messages::-webkit-scrollbar       { width: 5px; }
    .myw-messages::-webkit-scrollbar-track { background: transparent; }
    .myw-messages::-webkit-scrollbar-thumb { background: #ccd6f0; border-radius: 10px; }

    /*
      MESSAGE BUBBLES
      ================
      Each message is a row containing a bubble.
      User messages align right, bot messages align left.
    */
    .myw-msg-row { display: flex; max-width: 100%; }
    .myw-msg-row.myw-user { justify-content: flex-end;   }
    .myw-msg-row.myw-bot  { justify-content: flex-start; }
    .myw-bubble {
      max-width:     78%;
      padding:       10px 14px;
      border-radius: 18px;
      font-size:     14px;
      line-height:   1.5;
      word-wrap:     break-word;
    }
    .myw-msg-row.myw-user .myw-bubble {
      background:                var(--myw-bubble-user);
      color:                     var(--myw-bubble-user-text);
      border-bottom-right-radius: 4px;
      white-space:               pre-wrap;
    }
    .myw-msg-row.myw-bot .myw-bubble {
      background:               var(--myw-bubble-bot);
      color:                    var(--myw-bubble-bot-text);
      border-bottom-left-radius: 4px;
    }

    /*
      FORMATTED CONTENT INSIDE BUBBLES
      =================================
      Scoped styling for paragraphs, lists, and bold text inside bubbles.
      - Zeroed margins on first/last children ensure the bubble's 10px 14px
        internal padding remains intact without unwanted extra whitespace.
      - Scoped to .myw-bubble to avoid any style leakage to client page.
    */
    .myw-bubble p {
      margin: 0 0 8px 0;
    }
    .myw-bubble p:last-child {
      margin-bottom: 0;
    }
    .myw-bubble ul {
      margin: 6px 0 8px 0;
      padding-left: 20px;
    }
    .myw-bubble ul:first-child {
      margin-top: 0;
    }
    .myw-bubble ul:last-child {
      margin-bottom: 0;
    }
    .myw-bubble li {
      margin-bottom: 4px;
    }
    .myw-bubble li:last-child {
      margin-bottom: 0;
    }
    .myw-bubble strong {
      font-weight: 600;
    }
    .myw-bubble em {
      font-style: italic;
    }
    .myw-bubble code {
      background: rgba(0, 0, 0, 0.06);
      padding: 2px 5px;
      border-radius: 4px;
      font-family: monospace;
      font-size: 12px;
    }

    /*
      TABLE & STACKED CARD PRESENTATION
      ===================================
      Allows bot bubbles displaying structured tabular data to expand
      comfortably up to 95% width so content is clear and never cramped.
    */
    .myw-msg-row.myw-bot .myw-bubble:has(.myw-table-wrapper),
    .myw-msg-row.myw-bot .myw-bubble:has(.myw-card-list),
    .myw-msg-row.myw-bot .myw-bubble.myw-has-table {
      max-width: 95%;
      width: 95%;
    }

    /*
      1. COMPACT VISUAL TABLE (used for <= 2 columns that fit comfortably)
      ===================================================================
      Polished, modern table design matching widget color palette,
      fonts, and rounded border corners with no horizontal scroll required.
    */
    .myw-table-wrapper {
      width: 100%;
      overflow-x: auto;
      margin: 8px 0;
      border-radius: 10px;
      border: 1px solid #dbe4f0;
      background: #ffffff;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
    }
    .myw-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      line-height: 1.4;
      text-align: left;
    }
    .myw-table th {
      background: #eef4ff;
      color: var(--myw-primary-dark);
      font-weight: 600;
      padding: 8px 10px;
      border-bottom: 1px solid #dbe4f0;
      white-space: normal;
    }
    .myw-table td {
      padding: 8px 10px;
      border-bottom: 1px solid #edf2f7;
      color: var(--myw-bubble-bot-text);
      word-break: break-word;
    }
    .myw-table tr:last-child td {
      border-bottom: none;
    }
    .myw-table tbody tr:nth-child(even) {
      background: #f8fafd;
    }
    .myw-table tbody tr:hover {
      background: #f1f6ff;
    }

    /*
      2. STACKED CARD LAYOUT (used for multi-column tables > 2 columns)
      ================================================================
      In a compact ~350px widget, multi-column tables (e.g. 3, 4, 5+ columns like
      pricing comparisons) would either force horizontal scrolling or unreadable
      column squishing. Instead, each row becomes an elegant, self-contained card
      with details stacked vertically — clean, scannable, and zero horizontal scroll.
    */
    .myw-card-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 8px 0;
      width: 100%;
    }
    .myw-card {
      background: #ffffff;
      border: 1px solid #dbe4f0;
      border-left: 3.5px solid var(--myw-primary);
      border-radius: 10px;
      padding: 9px 12px;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .myw-card:hover {
      box-shadow: 0 2px 8px rgba(79, 142, 247, 0.12);
    }
    .myw-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding-bottom: 6px;
      margin-bottom: 6px;
      border-bottom: 1px solid #edf2f7;
    }
    .myw-card-title {
      font-size: 13.5px;
      font-weight: 700;
      color: var(--myw-primary-dark);
      letter-spacing: -0.2px;
      word-break: break-word;
    }
    .myw-card-badge {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--myw-primary);
      background: #eef4ff;
      padding: 2px 7px;
      border-radius: 12px;
      flex-shrink: 0;
    }
    .myw-card-body {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .myw-card-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      font-size: 12px;
      padding: 2px 0;
      line-height: 1.35;
    }
    .myw-card-row:not(:last-child) {
      border-bottom: 1px dashed #f0f4f9;
      padding-bottom: 4px;
    }
    .myw-card-label {
      color: #64748b;
      font-weight: 500;
      flex-shrink: 0;
      max-width: 48%;
      word-break: break-word;
    }
    .myw-card-value {
      color: #1e293b;
      font-weight: 600;
      text-align: right;
      word-break: break-word;
      flex-grow: 1;
    }

    /*
      3. FALLBACK LIST (Safety Net)
      =============================
      Used when a table is missing a proper identifying first column (e.g. only
      contains bare price numbers). Instead of guessing and mislabeling cards,
      it renders as a clean, structured bullet list with clear attribute labels.
    */
    .myw-fallback-list {
      margin: 6px 0;
      width: 100%;
    }
    .myw-fallback-list .myw-fallback-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--myw-primary-dark);
      margin-bottom: 4px;
    }
    .myw-fallback-list ul {
      margin: 4px 0;
      padding-left: 18px;
    }
    .myw-fallback-list li {
      font-size: 12.5px;
      line-height: 1.45;
      margin-bottom: 4px;
      color: var(--myw-bubble-bot-text);
    }

    /*
      TYPING INDICATOR (three bouncing dots)
      ========================================
      Pure CSS animation — no GIF needed.
      The three dots stagger their bounce using animation-delay.
    */
    .myw-typing {
      display:     flex;
      align-items: center;
      gap:         5px;
      padding:     12px 14px;
    }
    .myw-typing span {
      width:         8px;
      height:        8px;
      border-radius: 50%;
      background:    #aab4c8;
      display:       inline-block;
      animation:     myw-bounce 1.2s infinite ease-in-out;
    }
    .myw-typing span:nth-child(1) { animation-delay: 0s;   }
    .myw-typing span:nth-child(2) { animation-delay: 0.2s; }
    .myw-typing span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes myw-bounce {
      0%, 80%, 100% { transform: translateY(0);    opacity: 0.5; }
      40%           { transform: translateY(-8px); opacity: 1;   }
    }

    /* TIMESTAMP under each bubble */
    .myw-timestamp {
      font-size:  10px;
      color:      #aab4c8;
      margin-top: 2px;
      padding:    0 4px;
      text-align: right;
    }
    .myw-msg-row.myw-bot ~ .myw-timestamp { text-align: left; }

    /*
      INPUT BAR
      ==========
      Pinned at the bottom. flex-shrink:0 prevents it from being compressed
      by a very full message area. border-top visually separates it.
    */
    .myw-input-bar {
      display:     flex;
      align-items: center;
      gap:         8px;
      padding:     10px 12px;
      border-top:  1px solid var(--myw-input-border);
      background:  var(--myw-bg);
      flex-shrink: 0;
    }
    .myw-input {
      flex:          1;
      border:        1px solid var(--myw-input-border);
      border-radius: 24px;
      padding:       9px 16px;
      font-size:     14px;
      font-family:   var(--myw-font);
      outline:       none;
      color:         #1a1a2e;
      background:    #f8faff;
      transition:    border-color 0.2s;
      resize:        none;
      overflow:      hidden;
    }
    .myw-input:focus    { border-color: var(--myw-primary); }
    .myw-input:disabled { opacity: 0.6; cursor: not-allowed; }

    .myw-send-btn {
      width:           40px;
      height:          40px;
      border-radius:   50%;
      background:      var(--myw-primary);
      border:          none;
      cursor:          pointer;
      display:         flex;
      align-items:     center;
      justify-content: center;
      flex-shrink:     0;
      transition:      background 0.2s, transform 0.15s;
    }
    .myw-send-btn:hover:not(:disabled)  { background: var(--myw-primary-dark); }
    .myw-send-btn:active:not(:disabled) { transform: scale(0.92); }
    .myw-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .myw-send-btn svg { width: 18px; height: 18px; fill: white; }

    /* WELCOME / EMPTY STATE — visible before first message */
    .myw-welcome {
      text-align:  center;
      color:       #8a94a8;
      font-size:   13px;
      margin:      auto;
      padding:     20px;
      line-height: 1.7;
    }
    .myw-welcome-icon  { font-size: 36px; margin-bottom: 10px; display: block; }
    .myw-welcome strong { display: block; color: #3a4560; font-size: 15px; margin-bottom: 4px; }

    /*
      MOBILE RESPONSIVENESS (<= 480px)
      ================================
      On small mobile screens:
      1. The chat window takes up almost full width (calc(100vw - 20px)).
      2. It is centered horizontally using left: 10px, right: 10px, and margin: 0 auto.
      3. Bottom offset accommodates mobile browser bars and the floating trigger button.
      4. The floating trigger button stays strictly within viewport edges.
    */
    @media (max-width: 480px) {
      .myw-window {
        width:        calc(100vw - 20px);
        max-width:    calc(100vw - 20px);
        left:         10px;
        right:        10px;
        margin:       0 auto;
        bottom:       84px;
        height:       calc(100dvh - 100px);
        max-height:   520px;
      }
      .myw-trigger-btn {
        bottom:       16px;
        right:        16px;
      }
    }
  `;

  var styleEl    = document.createElement("style");
  styleEl.id     = "myw-widget-styles";
  styleEl.textContent = css;
  document.head.appendChild(styleEl);


  // ==========================================================================
  // SECTION 2: HTML — Build the widget DOM tree
  // ==========================================================================

  // FLOATING TRIGGER BUTTON
  // We use an inline SVG for the icon so there is no external image request.
  // Two SVG icons live in the button: one for "open" state, one for "close" state.
  // We show/hide them with display:none/block rather than swapping innerHTML,
  // which is slightly faster and avoids re-parsing HTML on every click.
  var triggerBtn = document.createElement("button");
  triggerBtn.className = "myw-trigger-btn";
  triggerBtn.setAttribute("aria-label", "Open chat");
  triggerBtn.setAttribute("title", "Chat with us");
  triggerBtn.innerHTML = `
    <svg class="myw-icon-chat" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2z"/>
    </svg>
    <svg class="myw-icon-close" style="display:none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M18 6L6 18M6 6l12 12" stroke="white" stroke-width="2.5" stroke-linecap="round" fill="none"/>
    </svg>
  `;

  // CHAT WINDOW
  var chatWindow = document.createElement("div");
  chatWindow.className = "myw-window";
  chatWindow.setAttribute("role", "dialog");
  chatWindow.setAttribute("aria-label", "Chat window");
  // We use innerHTML here for the static structural HTML — it is safe because
  // none of this content comes from user input. User-supplied text goes through
  // textContent only, while bot messages are HTML-escaped before markdown rendering (see appendMessage below).
  chatWindow.innerHTML = `
    <div class="myw-header">
      <p class="myw-header-title">
        <span class="myw-online-dot" title="Online"></span>
        Chat with us
      </p>
      <button class="myw-close-btn" aria-label="Close chat" title="Close">&#x2715;</button>
    </div>
    <div class="myw-messages" id="myw-messages-container">
      <div class="myw-welcome" id="myw-welcome">
        <span class="myw-welcome-icon">&#x1F44B;</span>
        <strong>Hi there! How can we help?</strong>
        Ask us anything — we are here to help you find answers fast.
      </div>
    </div>
    <div class="myw-input-bar">
      <textarea
        class="myw-input"
        id="myw-text-input"
        placeholder="Type a message..."
        rows="1"
        maxlength="1000"
        aria-label="Chat message input"
      ></textarea>
      <button class="myw-send-btn" id="myw-send-btn" aria-label="Send message" title="Send">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
        </svg>
      </button>
    </div>
  `;

  document.body.appendChild(triggerBtn);
  document.body.appendChild(chatWindow);


  // ==========================================================================
  // SECTION 3: STATE and DOM REFERENCES
  // ==========================================================================

  // Widget state flags
  var isOpen    = false;  // Is the chat window currently visible?
  var isWaiting = false;  // Are we waiting for a bot response? (prevents double-sends)
  var msgCount  = 0;      // How many messages added (used to hide the welcome card)
  var conversationHistory = []; // Bounded conversation history buffer [{role, content}]
  var MAX_WIDGET_HISTORY  = 6;  // Keep only the most recent exchanges to prevent payload bloat

  // Cache frequently accessed DOM nodes to avoid querying the DOM repeatedly
  var msgContainer = document.getElementById("myw-messages-container");
  var textInput    = document.getElementById("myw-text-input");
  var sendBtn      = document.getElementById("myw-send-btn");
  var welcomeEl    = document.getElementById("myw-welcome");
  var closeBtn     = chatWindow.querySelector(".myw-close-btn");
  var iconChat     = triggerBtn.querySelector(".myw-icon-chat");
  var iconClose    = triggerBtn.querySelector(".myw-icon-close");


  // ==========================================================================
  // SECTION 4: API INTEGRATION
  // ==========================================================================
  //
  // WHAT THIS DOES:
  // Connects the chat widget directly to the FastAPI backend RAG service.
  // Sends the user's message as JSON via a POST request to API_URL, and extracts
  // the "answer" field from the JSON response.
  //
  // ERROR HANDLING:
  // If the server returns a non-200 HTTP status (e.g. 500 internal error) or
  // if network connectivity fails, this function throws an error which handleSend()
  // catches to display a friendly message in the chat UI.

  /**
   * fetchApiResponse(userMessage)
   * ──────────────────────────────
   * Sends a POST request to API_URL with { message: userMessage, history: [...] } and extracts
   * the "answer" field from the JSON response.
   *
   * @param {string} userMessage - The question typed by the user.
   * @returns {Promise<string>} - Resolves with the "answer" text from the backend JSON.
   */
  async function fetchApiResponse(userMessage) {
    var response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: userMessage,
        history: conversationHistory.slice(-MAX_WIDGET_HISTORY)
      })
    });


    // Treat non-200 / non-ok HTTP responses as errors
    if (!response.ok) {
      throw new Error("HTTP error " + response.status + ": " + response.statusText);
    }

    var data = await response.json();

    // Verify response structure
    if (!data || typeof data.answer !== "string") {
      throw new Error("Invalid response format: missing 'answer' property");
    }

    return data.answer;
  }


  // ==========================================================================
  // SECTION 5: HELPER FUNCTIONS
  // ==========================================================================

  /**
   * getTimestamp() — Returns current time as "HH:MM" string.
   */
  function getTimestamp() {
    var now = new Date();
    return String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");
  }

  /**
   * scrollToBottom()
   * ─────────────────
   * Smoothly scrolls the messages area to the very bottom.
   * Called after every new message or typing indicator so the latest content
   * is always visible without the user needing to scroll manually.
   *
   * WHY scrollTop = scrollHeight:
   * scrollHeight is the total height of all content including the overflow
   * that is not visible. Setting scrollTop equal to it jumps to the bottom.
   */
  function scrollToBottom() {
    msgContainer.scrollTo({ top: msgContainer.scrollHeight, behavior: "smooth" });
  }

  /**
   * markdownToHtml(text)
   * ────────────────────
   * Lightweight, dependency-free converter for bot responses.
   * Handles:
   *   - Markdown tables: detected and converted to visual tables (<= 2 cols)
   *     or responsive stacked cards (> 2 cols) so users never need to scroll sideways.
   *   - **bold** text -> <strong>bold</strong>
   *   - *italic* text -> <em>italic</em>
   *   - `inline code` -> <code>inline code</code>
   *   - Bullet lines starting with "- " -> <ul><li>...</li></ul>
   *   - Double newlines -> separate <p> paragraph blocks
   *   - Single newlines -> <br> line breaks within paragraphs
   *
   * Security:
   * First escapes HTML special characters (&, <, >, ", ') to protect against
   * XSS, ensuring any raw HTML in LLM output is rendered safely as plain text.
   *
   * @param {string} text - Raw bot answer text.
   * @returns {string} Formatted HTML string.
   */
  function markdownToHtml(text) {
    if (!text) return "";

    // 1. Escape HTML special characters for XSS prevention
    var escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

    // Helper to format inline markdown (e.g. **bold**, *italic*, `code`)
    function formatInline(str) {
      if (!str) return "";
      return str
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*\n]+?)\*/g, "<em>$1</em>")
        .replace(/`([^`\n]+?)`/g, "<code>$1</code>");
    }

    // Helper: checks if a line is a markdown table delimiter row (e.g. |---|---| or |---|)
    function isTableSeparator(line) {
      if (!line || line.indexOf("|") === -1) return false;
      var cells = line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|");
      if (cells.length < 1) return false;
      for (var s = 0; s < cells.length; s++) {
        if (!/^\s*:?-{2,}:?\s*$/.test(cells[s])) return false;
      }
      return true;
    }

    // Helper: splits a table row line into trimmed cell strings
    function parseRowCells(line) {
      return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function(c) {
        return c.trim();
      });
    }

    // Helper: renders a clean, modern HTML table for compact 1-2 column tables
    function renderTableHtml(headers, alignments, rows) {
      var tHtml = ['<div class="myw-table-wrapper"><table class="myw-table">'];
      
      tHtml.push('<thead><tr>');
      for (var h = 0; h < headers.length; h++) {
        var alignStyle = alignments[h] && alignments[h] !== "left" ? ' style="text-align:' + alignments[h] + '"' : "";
        tHtml.push('<th' + alignStyle + '>' + formatInline(headers[h]) + '</th>');
      }
      tHtml.push('</tr></thead>');
      
      tHtml.push('<tbody>');
      for (var r = 0; r < rows.length; r++) {
        tHtml.push('<tr>');
        var row = rows[r];
        for (var c = 0; c < headers.length; c++) {
          var cellVal = row[c] !== undefined && row[c] !== "" ? row[c] : "—";
          var alignStyle = alignments[c] && alignments[c] !== "left" ? ' style="text-align:' + alignments[c] + '"' : "";
          tHtml.push('<td' + alignStyle + '>' + formatInline(cellVal) + '</td>');
        }
        tHtml.push('</tr>');
      }
      tHtml.push('</tbody></table></div>');
      return tHtml.join("");
    }

    // Helper: renders multi-column tables as stacked cards to eliminate horizontal scrolling
    function renderCardLayoutHtml(headers, rows) {
      var cHtml = ['<div class="myw-card-list">'];
      
      for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        cHtml.push('<div class="myw-card">');
        
        // Use first column as primary card title (e.g. Plan / Tier name)
        var primaryTitle = row[0] ? formatInline(row[0]) : ("Item " + (r + 1));
        var primaryHeader = headers[0] ? formatInline(headers[0]) : "";
        
        cHtml.push('<div class="myw-card-header">');
        cHtml.push('<span class="myw-card-title">' + primaryTitle + '</span>');
        if (primaryHeader && !/^(plan|tier|name|item)$/i.test(primaryHeader)) {
          cHtml.push('<span class="myw-card-badge">' + primaryHeader + '</span>');
        }
        cHtml.push('</div>');
        
        // Stack remaining columns vertically as clean label/value pairs
        cHtml.push('<div class="myw-card-body">');
        for (var c = 1; c < headers.length; c++) {
          var label = headers[c] ? formatInline(headers[c]) : "";
          var value = row[c] !== undefined && row[c] !== "" ? formatInline(row[c]) : "—";
          cHtml.push('<div class="myw-card-row">');
          cHtml.push('<span class="myw-card-label">' + label + '</span>');
          cHtml.push('<span class="myw-card-value">' + value + '</span>');
          cHtml.push('</div>');
        }
        cHtml.push('</div>');
        cHtml.push('</div>');
      }
      
      cHtml.push('</div>');
      return cHtml.join("");
    }

    // Safety Net Helper: determines whether column 0 represents an identifying entity/name
    // (e.g. Plan, Tier, Feature, Package, Name) vs. a raw numeric/price metric.
    function isIdentifyingFirstColumn(headers, rows) {
      if (!headers || headers.length === 0) return false;
      if (headers.length === 1) return false; // 1-column tables have no entity+detail relationship

      var firstHeader = headers[0].trim().toLowerCase();

      // Explicit entity/name keywords
      var entityKeywords = /^(plan|tier|name|item|product|package|feature|category|edition|role|service|type|user\s*type)/i;
      if (entityKeywords.test(firstHeader)) return true;

      // Explicit metric/price keywords
      var metricKeywords = /^(price|cost|fee|rate|amount|annual|monthly|total|subtotal|discount|\$|per\s*user|per\s*month)/i;
      if (metricKeywords.test(firstHeader)) return false;

      // Inspect column 0 values: if every value looks like a price or bare number, it's not an identifying name
      if (rows && rows.length > 0) {
        var allNumericOrPrices = true;
        for (var r = 0; r < rows.length; r++) {
          var val = (rows[r][0] || "").trim();
          var cleanVal = val.replace(/[*_`]/g, "").trim();
          var isPriceLike = /^[\$€£¥]?\s*\d+(\.\d+)?(\s*(\/|per|mo|yr|month|year))?$/i.test(cleanVal);
          if (!isPriceLike) {
            allNumericOrPrices = false;
            break;
          }
        }
        if (allNumericOrPrices) return false;
      }

      return true;
    }

    // Safety Net Helper: renders a clean list when a table lacks an identifying column,
    // ensuring no attribute is mistakenly promoted to a card title.
    function renderFallbackListHtml(headers, rows) {
      var fHtml = ['<div class="myw-fallback-list">'];
      if (headers.length === 1) {
        fHtml.push('<p class="myw-fallback-title"><strong>' + formatInline(headers[0]) + ':</strong></p><ul>');
        for (var i = 0; i < rows.length; i++) {
          var val = rows[i][0] ? formatInline(rows[i][0]) : "—";
          fHtml.push('<li>' + val + '</li>');
        }
        fHtml.push('</ul>');
      } else {
        fHtml.push('<ul>');
        for (var r = 0; r < rows.length; r++) {
          var parts = [];
          for (var c = 0; c < headers.length; c++) {
            var h = headers[c] ? formatInline(headers[c]) : "";
            var v = rows[r][c] !== undefined && rows[r][c] !== "" ? formatInline(rows[r][c]) : "—";
            parts.push('<strong>' + h + ':</strong> ' + v);
          }
          fHtml.push('<li>' + parts.join(' &bull; ') + '</li>');
        }
        fHtml.push('</ul>');
      }
      fHtml.push('</div>');
      return fHtml.join("");
    }

    // 2. Parse lines into paragraphs, lists, and tables/cards
    var lines = escaped.split(/\r?\n/);
    var html = [];
    var inList = false;
    var currentParagraph = [];

    function flushParagraph() {
      if (currentParagraph.length > 0) {
        html.push("<p>" + currentParagraph.map(formatInline).join("<br>") + "</p>");
        currentParagraph = [];
      }
    }

    function flushList() {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var trimmed = line.trim();

      // Check for start of markdown table: line has '|' and next line is table separator
      if (i + 1 < lines.length && line.indexOf("|") !== -1 && isTableSeparator(lines[i + 1])) {
        flushParagraph();
        flushList();

        var headers = parseRowCells(line);
        var sepLine = lines[i + 1];
        var sepCells = parseRowCells(sepLine);
        
        var alignments = sepCells.map(function(cell) {
          var c = cell.trim();
          if (c.startsWith(":") && c.endsWith(":")) return "center";
          if (c.endsWith(":")) return "right";
          return "left";
        });

        var rows = [];
        var j = i + 2;
        while (j < lines.length && lines[j].trim() !== "" && lines[j].indexOf("|") !== -1) {
          if (isTableSeparator(lines[j])) break;
          rows.push(parseRowCells(lines[j]));
          j++;
        }

        var hasIdentifier = isIdentifyingFirstColumn(headers, rows);

        if (!hasIdentifier) {
          // Safety Net: Missing proper identifying first column.
          // Fall back to clean list (or standard 2-col table where headers prevent confusion)
          if (headers.length === 1 || headers.length > 2) {
            html.push(renderFallbackListHtml(headers, rows));
          } else {
            html.push(renderTableHtml(headers, alignments, rows));
          }
        } else if (headers.length > 2) {
          // Multi-column table with proper identifier: stacked card layout
          html.push(renderCardLayoutHtml(headers, rows));
        } else {
          // 2-column table with proper identifier: clean visual table
          html.push(renderTableHtml(headers, alignments, rows));
        }

        i = j - 1; // Advance loop to end of table
        continue;
      }

      // Check for bullet lines starting with "- "
      var bulletMatch = line.match(/^\s*-\s+(.+)$/);

      if (bulletMatch) {
        flushParagraph();
        if (!inList) {
          html.push("<ul>");
          inList = true;
        }
        html.push("<li>" + formatInline(bulletMatch[1].trim()) + "</li>");
      } else if (trimmed === "") {
        // Blank line ends current paragraph or list block
        flushParagraph();
        flushList();
      } else {
        // Regular text line: close list if one was active, add to current paragraph
        flushList();
        currentParagraph.push(trimmed);
      }
    }

    flushParagraph();
    flushList();

    return html.join("");
  }

  /**
   * appendMessage(text, sender)
   * ────────────────────────────
   * Creates and inserts a message bubble.
   *
   * SECURITY & FORMATTING:
   * - User messages: always inserted using .textContent to prevent XSS attacks.
   *   User input is strictly treated as plain text and never interpreted as HTML.
   * - Bot messages: converted via markdownToHtml() (which escapes raw HTML, converts
   *   tables to visual tables or cards, and formats inline markdown) and inserted
   *   using .innerHTML.
   *
   * @param {string} text   - Message text to display.
   * @param {string} sender - 'user' or 'bot'.
   */
  function appendMessage(text, sender) {
    if (msgCount === 0 && welcomeEl) {
      welcomeEl.style.display = "none"; // Hide welcome card on first message
    }
    msgCount++;

    var row    = document.createElement("div");
    row.className = "myw-msg-row myw-" + sender;

    var bubble = document.createElement("div");
    bubble.className  = "myw-bubble";

    if (sender === "bot") {
      var rendered = markdownToHtml(text);
      bubble.innerHTML = rendered;
      // If table, card layout, or fallback list is present, expand bubble width for spacious readability
      if (rendered.indexOf("myw-table-wrapper") !== -1 || rendered.indexOf("myw-card-list") !== -1 || rendered.indexOf("myw-fallback-list") !== -1) {
        bubble.classList.add("myw-has-table");
      }
    } else {
      bubble.textContent = text; // SAFE: plain textContent for user messages
    }

    row.appendChild(bubble);
    msgContainer.appendChild(row);

    var ts = document.createElement("div");
    ts.className   = "myw-timestamp";
    ts.textContent = getTimestamp();
    msgContainer.appendChild(ts);

    scrollToBottom();
  }

  /**
   * showTypingIndicator()
   * ──────────────────────
   * Inserts the animated three-dot typing bubble.
   * Returns its DOM element so removeTypingIndicator() can target it directly
   * (faster and safer than re-querying the DOM).
   *
   * @returns {HTMLElement}
   */
  function showTypingIndicator() {
    var row    = document.createElement("div");
    row.className = "myw-msg-row myw-bot";
    var bubble = document.createElement("div");
    bubble.className = "myw-bubble myw-typing";
    bubble.innerHTML = "<span></span><span></span><span></span>";
    row.appendChild(bubble);
    msgContainer.appendChild(row);
    scrollToBottom();
    return row;
  }

  /**
   * removeTypingIndicator(el) — Removes the typing indicator from the DOM.
   * Null-checks first in case the user closed the window mid-response.
   */
  function removeTypingIndicator(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  /**
   * setInputEnabled(enabled)
   * ─────────────────────────
   * Locks or unlocks the text input and send button while awaiting a response.
   * Prevents double-sends: if the user fires two messages before the first
   * response arrives, the responses could arrive out of order and scramble
   * the conversation. Disabling input prevents this entirely.
   */
  function setInputEnabled(enabled) {
    textInput.disabled = !enabled;
    sendBtn.disabled   = !enabled;
    isWaiting          = !enabled;
  }


  // ==========================================================================
  // SECTION 6: CORE SEND LOGIC
  // ==========================================================================

  /**
   * handleSend()
   * ─────────────
   * Orchestrates the full send → typing indicator → real fetch → display cycle.
   *
   * WHY ASYNC/AWAIT:
   * fetchApiResponse returns a Promise. async/await lets us pause execution
   * while the backend runs RAG retrieval + LLM inference, keeping the typing
   * indicator visible without blocking the browser UI thread.
   */
  async function handleSend() {
    var text = textInput.value.trim();
    if (!text || isWaiting) return; // Guard: empty input or request already in flight

    textInput.value        = "";
    textInput.style.height = "auto"; // Reset auto-grown height

    appendMessage(text, "user"); // 1. Show user message immediately

    setInputEnabled(false);                    // 2. Lock input
    var typingEl = showTypingIndicator();      // 3. Show "bot is typing" dots (stays active during fetch)

    try {
      var reply = await fetchApiResponse(text); // 4. Real fetch POST request to backend API
      removeTypingIndicator(typingEl);          // 5. Remove dots once answer arrives
      appendMessage(reply, "bot");              // 6. Show response

      // Record exchange into bounded conversation history buffer
      conversationHistory.push({ role: "user", content: text });
      conversationHistory.push({ role: "assistant", content: reply });
      if (conversationHistory.length > MAX_WIDGET_HISTORY) {
        conversationHistory = conversationHistory.slice(-MAX_WIDGET_HISTORY);
      }
    } catch (err) {
      // If the fetch fails (server down, network error, non-200 response),
      // remove typing dots and display a friendly message instead of breaking silently.
      removeTypingIndicator(typingEl);
      appendMessage("Sorry, something went wrong — please try again.", "bot");
      console.error("[ChatWidget] Error fetching response:", err);
    } finally {
      // 'finally' runs regardless of success or failure — perfect for cleanup.
      // Always re-enable the input so the user is never permanently locked out.
      setInputEnabled(true);
      textInput.focus();
    }
  }


  // ==========================================================================
  // SECTION 7: OPEN / CLOSE TOGGLE
  // ==========================================================================

  // We keep openChat and closeChat as separate functions (rather than one
  // toggle) because different event listeners need different behaviours:
  // the X button always closes, the floating button always toggles.

  function openChat() {
    isOpen = true;
    chatWindow.classList.add("myw-open");
    iconChat.style.display  = "none";
    iconClose.style.display = "block";
    triggerBtn.setAttribute("aria-label", "Close chat");
    // Brief delay before focusing so the CSS slide-up animation has started
    setTimeout(function () { textInput.focus(); }, 50);
  }

  function closeChat() {
    isOpen = false;
    chatWindow.classList.remove("myw-open");
    iconChat.style.display  = "block";
    iconClose.style.display = "none";
    triggerBtn.setAttribute("aria-label", "Open chat");
  }

  function toggleChat() {
    if (isOpen) { closeChat(); } else { openChat(); }
  }


  // ==========================================================================
  // SECTION 8: EVENT LISTENERS
  // ==========================================================================

  // Floating button: toggle open/closed
  triggerBtn.addEventListener("click", toggleChat);

  // Header X button: always close
  closeBtn.addEventListener("click", closeChat);

  // Send button: submit the message
  sendBtn.addEventListener("click", handleSend);

  // Keyboard: Enter submits, Shift+Enter inserts a newline.
  // This matches the UX convention of every major chat app (Slack, WhatsApp, etc.)
  textInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault(); // Prevent the default textarea newline on plain Enter
      handleSend();
    }
  });

  // Auto-grow textarea: we reset height to 'auto' first (to shrink on deletion),
  // then set it to exactly the scroll height so all typed content is visible.
  textInput.addEventListener("input", function () {
    this.style.height = "auto";
    var max = 120; // Cap at roughly 5 lines of text
    this.style.height = Math.min(this.scrollHeight, max) + "px";
  });

  // Click-outside-to-close: close the chat window if the user clicks anywhere
  // on the page that is not the widget. A common and expected UX behaviour.
  document.addEventListener("click", function (e) {
    if (isOpen && !chatWindow.contains(e.target) && !triggerBtn.contains(e.target)) {
      closeChat();
    }
  });


  // ==========================================================================
  // SECTION 9: INITIALISATION
  // ==========================================================================

  // Log a breadcrumb so developers can confirm the widget loaded cleanly.
  console.log("[ChatWidget] Widget loaded and ready. v1.0.0 — Connected to API: " + API_URL);

})(); // End of IIFE
