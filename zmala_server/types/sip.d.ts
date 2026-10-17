/** Narrow declarations for the untyped, pinned SIP dependency. Protocol input
 * remains untrusted and is checked by sip-guards before dialog processing. */
export interface Uri {
  user?: string;
  host: string;
  port?: number;
}
export interface Address {
  uri: string;
  params?: Record<string, string | number>;
}
export interface Digest {
  scheme: string;
  username?: string;
  nonce?: string;
  uri?: string;
  cnonce?: string;
  nc?: string;
  realm?: string;
  qop?: string;
  algorithm?: string;
  response?: string;
}
export interface Remote {
  address: string;
  port: number;
  protocol: string;
  local?: { address: string; port: number };
}
export interface Via {
  params?: Record<string, string | number>;
}
export interface Headers {
  via?: Via[];
  route?: Address[];
  'record-route'?: Address[];
  'content-type'?: string;
  'x-family-auth'?: string;
  'x-zmala-message-id'?: string;
  to?: Address;
  from?: Address;
  contact?: Address[];
  expires?: string | number;
  cseq?: { seq: number; method: string };
  'call-id'?: string;
  'max-forwards'?: string | number;
  authorization?: Digest[];
  'proxy-authorization'?: Digest[];
  'www-authenticate'?: Digest[];
  'proxy-authenticate'?: Digest[];
}
export interface Message {
  method?: string;
  status?: number;
  uri?: string;
  headers: Headers;
  content?: string;
}
export interface ValidRequest extends Message {
  method: string;
  uri: string;
  headers: Headers & {
    from: Address;
    to: Address;
    cseq: { seq: number; method: string };
    'call-id': string;
  };
}
export interface Response extends Message {
  status: number;
}
export interface Options {
  address: string;
  publicAddress?: string;
  port: number;
  tcp?: boolean;
  udp?: boolean;
  requestGuard?(message: Message, remote: Remote): number;
  logger?: {
    error(error: Error): void;
    recv(message: Message, remote: Remote): void;
    send(message: Message, remote: Remote): void;
  };
}
export function makeResponse(request: Message, status: number, reason?: string): Response;
export function copyMessage<T extends Message>(message: T, deep?: boolean): T;
export function encodeFlowUri(remote: Remote): string;
export let send: (message: Message, callback?: (response: Response) => void) => void;
export function stop(): void;
export function stringifyUri(uri: string | Uri): string;
export function parseUri(uri: string): Uri | undefined;
