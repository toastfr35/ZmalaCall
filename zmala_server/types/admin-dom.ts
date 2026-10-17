/** Static IDs in admin.html. Required-element helpers throw on missing markup. */
export interface AdminElements {
  content: HTMLElement;
  eyebrow: HTMLElement;
  'page-title': HTMLElement;
  'page-description': HTMLElement;
  'page-actions': HTMLElement;
  error: HTMLElement;
  notice: HTMLElement;
  view: HTMLElement;
  'console-dialog': HTMLDialogElement;
  'console-title': HTMLElement;
  'console-state': HTMLElement;
  'console-shell-form': HTMLFormElement;
  'console-shell': HTMLSelectElement;
  'console-shell-error': HTMLElement;
  'console-history': HTMLElement;
  'console-form': HTMLFormElement;
  'console-error': HTMLElement;
  'console-command': HTMLTextAreaElement;
  'console-timeout': HTMLInputElement;
  'wifi-dialog': HTMLDialogElement;
  'wifi-form': HTMLFormElement;
  'wifi-title': HTMLElement;
  'wifi-error': HTMLElement;
  'wifi-ssid': HTMLInputElement;
  'wifi-security': HTMLSelectElement;
  'wifi-password-field': HTMLElement;
  'wifi-password': HTMLInputElement;
  'wifi-hidden': HTMLInputElement;
  'account-dialog': HTMLDialogElement;
  'account-form': HTMLFormElement;
  'account-title': HTMLElement;
  'account-error': HTMLElement;
  'edit-name': HTMLInputElement;
  'edit-id': HTMLInputElement;
  'edit-emails': HTMLInputElement;
  'account-picture-preview': HTMLElement;
  'edit-photo': HTMLInputElement;
  'edit-remove-photo': HTMLInputElement;
  'edit-type': HTMLSelectElement;
  'edit-password': HTMLInputElement;
  'password-help': HTMLElement;
  'rename-help': HTMLElement;
  'account-save': HTMLButtonElement;
  'connection-dialog': HTMLDialogElement;
  'details-title': HTMLElement;
  'details-content': HTMLElement;
  'confirm-dialog': HTMLDialogElement;
  'confirm-title': HTMLElement;
  'confirm-description': HTMLElement;
  'confirm-error': HTMLElement;
  'confirm-action': HTMLButtonElement;
  'group-dialog': HTMLDialogElement;
  'group-form': HTMLFormElement;
  'group-title': HTMLElement;
  'group-error': HTMLElement;
  'group-name': HTMLInputElement;
  'group-description': HTMLInputElement;
  'group-selected-count': HTMLElement;
  'group-members': HTMLElement;
  'group-save': HTMLButtonElement;
}
export type IdElement<I extends string> = I extends keyof AdminElements
  ? AdminElements[I]
  : HTMLElement;
export type SelectedElement<S extends string> = S extends keyof HTMLElementTagNameMap
  ? HTMLElementTagNameMap[S]
  : HTMLElement;
export interface TerminalForm extends HTMLFormElement {
  fields: Record<string, HTMLInputElement | HTMLSelectElement>;
  errorId: string;
}
