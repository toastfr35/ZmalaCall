export function start(
  options: import('sip').Options,
  route: (message: import('sip').Message, remote: import('sip').Remote) => void,
): void;
export function clearContexts(): void;
export function send(
  message: import('sip').Message,
  callback?: (response: import('sip').Response) => void,
): void;
