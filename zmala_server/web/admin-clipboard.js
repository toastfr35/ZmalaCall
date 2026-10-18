// The installed server is also used over plain LAN HTTP, where Clipboard API
// access is unavailable. Keep the fallback inside the open dialog's focus scope.
// @llr LLR-SRV-UI-009
/** @param {string} value @param {HTMLElement} owner @returns {Promise<boolean>} */
export async function writeClipboard(value, owner) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Permission denial can still allow a copy initiated by the same button.
  }
  const previous = document.activeElement;
  const field = document.createElement('textarea');
  field.value = value;
  field.readOnly = true;
  field.tabIndex = -1;
  field.setAttribute('aria-hidden', 'true');
  field.style.cssText = 'position:fixed;inset:0 auto auto 0;opacity:0;pointer-events:none';
  try {
    (owner.closest('dialog') || document.body).append(field);
    field.focus({ preventScroll: true });
    field.select();
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    field.remove();
    if (previous instanceof HTMLElement && previous.isConnected)
      previous.focus({ preventScroll: true });
  }
}
