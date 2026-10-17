type Store = InstanceType<typeof import('../store').Store>;
import type { CallbackView, JsonObject, TerminalStatus, SipStatus } from './contracts';

/** Only the service operations used at the HTTP boundary are exposed here.
 * Callback/command services validate their own unknown request fields. */
export interface CallbackApi {
  flush(): Promise<void>;
  list(account?: string): CallbackView[];
  create(from: string, to: unknown): CallbackView;
  cancel(id: string, account?: string): void;
  rename(oldId: string, newId: string): void;
  reconcile(): void;
  updateSettings(update: JsonObject): void;
  deliver(account?: string): void;
  email: { mailer: { verify(): Promise<unknown> } };
}
export interface ConsoleApi {
  flush(): Promise<void>;
  list(id: string): unknown[];
  create(id: string, update: JsonObject): { id: string };
  cancel(id: string, jobId: string): void;
  claim(id: string): unknown;
  finish(id: string, jobId: string, result: JsonObject): unknown;
  swapTerminals(first: string, second: string): void;
  rename(oldId: string, newId: string): void;
}
export interface Registration {
  expires: number;
  reachable?: boolean;
}
export interface SipApi {
  registrations: Map<string, Registration>;
  dialogs: Map<string, { peers: { user: string }[] }>;
  cancelProbe?(id: string): void;
  status(): SipStatus;
}
export interface HttpContext {
  persistenceReady?(): boolean;
  adminSessions: InstanceType<typeof import('../admin-sessions').AdminSessions>;
  requireSecureAdmin?: boolean;
  store: Store;
  sipServer: SipApi;
  callbacks: CallbackApi;
  consoleJobs: ConsoleApi;
  terminalStatuses: Record<string, TerminalStatus>;
  writeBootstrap(): Promise<void>;
}
export interface DeviceContext extends HttpContext {
  deviceId?: string;
}
