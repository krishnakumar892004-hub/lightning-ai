// ==========================================================
// Lightning AI — Frontend logic
// ==========================================================

const chatArea = document.getElementById('chatArea');
const welcomeScreen = document.getElementById('welcomeScreen');
const composerForm = document.getElementById('composerForm');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const attachBtn = document.getElementById('attachBtn');
const imageInput = document.getElementById('imageInput');
const imagePreviewWrap = document.getElementById('imagePreviewWrap');
const imagePreview = document.getElementById('imagePreview');
const removeImageBtn = document.getElementById('removeImage');
const modeSwitch = document.getElementById('modeSwitch');
const historyList = document.getElementById('historyList');
const newChatBtn = document.getElementById('newChatBtn');
const menuToggle = document.getElementById('menuToggle');
const sidebar = document.querySelector('.sidebar');

let currentMode = 'chat'; // 'chat' | 'image'
let pendingFile = null;

// ---------- Mode switch ----------
modeSwitch.addEventListener('click', (e) => {
  const btn = e.target.closest('.mode-btn');
  if (!btn) return;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentMode = btn.dataset.mode;
  messageInput.placeholder = currentMode === 'image'
    ? 'Describe the image you want Lightning AI to create...'
    : 'Ask Lightning AI anything...';
});

// ---------- Sidebar toggle (mobile) ----------
menuToggle.addEventListener('click', () => sidebar.classList.toggle('open'));

// ---------- Auto-grow textarea ----------
messageInput.addEventListener('input', () => {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + 'px';
});
messageInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    composerForm.requestSubmit();
  }
});

// ---------- Image attach ----------
attachBtn.addEventListener('click', () => imageInput.click());
imageInput.addEventListener('change', () => {
  const file = imageInput.files[0];
  if (!file) return;
  pendingFile = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    imagePreview.src = e.target.result;
    imagePreviewWrap.hidden = false;
  };
  reader.readAsDataURL(file);
});
removeImageBtn.addEventListener('click', () => {
  pendingFile = null;
  imageInput.value = '';
  imagePreviewWrap.hidden = true;
});

// ---------- New chat ----------
newChatBtn.addEventListener('click', () => {
  chatArea.innerHTML = '';
  chatArea.appendChild(welcomeScreen);
  welcomeScreen.style.display = 'block';
});

// ---------- Helpers ----------
function hideWelcome() {
  if (welcomeScreen && welcomeScreen.parentNode) welcomeScreen.style.display = 'none';
}

function addUserMessage(text, imageUrl) {
  hideWelcome();
  const msg = document.createElement('div');
  msg.className = 'msg user';
  msg.innerHTML = `
    <div class="msg-avatar">🧑</div>
    <div class="msg-bubble">
      ${text ? escapeHtml(text) : ''}
      ${imageUrl ? `<img src="${imageUrl}" class="msg-image" alt="uploaded image">` : ''}
    </div>`;
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function addAiTyping() {
  hideWelcome();
  const msg = document.createElement('div');
  msg.className = 'msg ai';
  msg.id = 'typingMsg';
  msg.innerHTML = `
    <div class="msg-avatar">⚡</div>
    <div class="msg-bubble typing-dots"><span></span><span></span><span></span></div>`;
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typingMsg');
  if (el) el.remove();
}

function addAiMessage({ text, imageUrl, isError }) {
  removeTyping();
  const msg = document.createElement('div');
  msg.className = 'msg ai';
  msg.innerHTML = `
    <div class="msg-avatar">⚡</div>
    <div class="msg-bubble ${isError ? 'error' : ''}">
      ${text ? escapeHtml(text) : ''}
      ${imageUrl ? `<img src="${imageUrl}" class="msg-image" alt="generated image">` : ''}
    </div>`;
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------- Submit handler ----------
composerForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text && !pendingFile) return;

  sendBtn.disabled = true;

  try {
    if (pendingFile) {
      // Image upload + question (vision)
      const previewSrc = imagePreview.src;
      addUserMessage(text || 'What is in this image?', previewSrc);
      addAiTyping();

      const formData = new FormData();
      formData.append('image', pendingFile);
      formData.append('question', text || 'Describe this image in detail.');

      const res = await fetch('/api/upload-image', { method: 'POST', body: formData });
      const data = await res.json();

      if (!res.ok) addAiMessage({ text: data.error || 'Something went wrong.', isError: true });
      else addAiMessage({ text: data.answer });

      pendingFile = null;
      imageInput.value = '';
      imagePreviewWrap.hidden = true;

    } else if (currentMode === 'image') {
      // Image generation
      addUserMessage(text);
      addAiTyping();

      const res = await fetch('/api/generate-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text }),
      });
      const data = await res.json();

      if (!res.ok) addAiMessage({ text: data.error || 'Image generation failed.', isError: true });
      else addAiMessage({ text: 'Here you go ⚡', imageUrl: data.image_url });

    } else {
      // Normal chat
      addUserMessage(text);
      addAiTyping();

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();

      if (!res.ok) addAiMessage({ text: data.error || 'Something went wrong.', isError: true });
      else addAiMessage({ text: data.answer });
    }

    loadHistory();
  } catch (err) {
    removeTyping();
    addAiMessage({ text: 'Network error. Please try again.', isError: true });
  } finally {
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = false;
  }
});

// ---------- Load history sidebar ----------
async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    const items = await res.json();
    historyList.innerHTML = '';
    items.slice().reverse().forEach(item => {
      const div = document.createElement('div');
      div.className = 'history-item';
      const icon = item.type === 'image_gen' ? '🎨' : item.type === 'image_qa' ? '🖼️' : '💬';
      div.innerHTML = `<span class="tag">${icon}</span><span>${escapeHtml(item.question || '')}</span>`;
      historyList.appendChild(div);
    });
  } catch (err) {
    console.error('Failed to load history', err);
  }
}

loadHistory();
