document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-modal]').forEach(button => button.addEventListener('click', () => {
    const modal = document.getElementById(button.dataset.modal);
    if (modal) { modal.classList.add('open'); const input = modal.querySelector('input,select'); if (input) input.focus(); }
  }));
  document.querySelectorAll('[data-close-modal], .modal-close').forEach(button => button.addEventListener('click', () => button.closest('.modal-backdrop')?.classList.remove('open')));
  document.querySelectorAll('.modal-backdrop').forEach(modal => modal.addEventListener('click', e => { if (e.target === modal) modal.classList.remove('open'); }));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open')); });
  document.querySelectorAll('.flash-close').forEach(button => button.addEventListener('click', () => button.parentElement.remove()));
  document.querySelectorAll('[data-table-search]').forEach(input => input.addEventListener('input', () => {
    const table = input.closest('.panel').querySelector('[data-search-table]');
    const query = input.value.toLowerCase();
    table.querySelectorAll('tbody tr').forEach(row => row.hidden = !row.textContent.toLowerCase().includes(query));
  }));
  const supplier = document.getElementById('supplier-select');
  const product = document.getElementById('product-select');
  const price = document.getElementById('order-price');
  if (supplier && product) {
    supplier.addEventListener('change', () => {
      [...product.options].forEach(option => { option.hidden = !!option.value && option.dataset.supplier && option.dataset.supplier !== supplier.value; });
      if (product.selectedOptions[0]?.hidden) product.value = '';
    });
    product.addEventListener('change', () => { const selected = product.selectedOptions[0]; if (selected?.dataset.price) price.value = Number(selected.dataset.price).toFixed(2); if (selected?.dataset.supplier) supplier.value = selected.dataset.supplier; supplier.dispatchEvent(new Event('change')); });
  }
  document.getElementById('menu-toggle')?.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('sidebar-open'));
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const chatMessages = document.getElementById('chat-messages');
  const chatSend = document.getElementById('chat-send');
  const addMessage = (text, kind) => {
    const row = document.createElement('div'); row.className = `chat-message ${kind}-message`;
    const avatar = document.createElement('span'); avatar.className = 'message-avatar'; avatar.textContent = kind === 'assistant' ? '✳' : 'JD';
    const bubble = document.createElement('div'); bubble.className = 'message-bubble';
    if (kind === 'assistant') { const name = document.createElement('strong'); name.textContent = 'SmartSupply AI'; bubble.appendChild(name); }
    const paragraph = document.createElement('p'); paragraph.textContent = text; bubble.appendChild(paragraph);
    row.append(avatar, bubble); chatMessages.appendChild(row); chatMessages.scrollTop = chatMessages.scrollHeight; return row;
  };
  document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => { chatInput.value = button.dataset.prompt; chatInput.focus(); }));
  chatInput?.addEventListener('input', () => { chatInput.style.height = 'auto'; chatInput.style.height = `${Math.min(chatInput.scrollHeight, 100)}px`; });
  chatForm?.addEventListener('submit', async event => {
    event.preventDefault(); const message = chatInput.value.trim(); if (!message) return;
    addMessage(message, 'user'); chatInput.value = ''; chatInput.style.height = 'auto'; chatSend.disabled = true;
    const thinking = addMessage('Reviewing the latest supply chain data…', 'assistant'); thinking.classList.add('thinking-message');
    try {
      const response = await fetch('/api/assistant', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message})});
      const result = await response.json(); thinking.remove(); addMessage(result.answer || result.error || 'Something went wrong. Please try again.', 'assistant');
    } catch (_) { thinking.remove(); addMessage('Could not connect to SmartSupply. Check that the app is running and try again.', 'assistant'); }
    finally { chatSend.disabled = false; chatInput.focus(); }
  });
});
