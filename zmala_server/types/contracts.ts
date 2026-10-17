/** Runtime JSON is still validated on receipt. These contracts catch mistakes
 * inside the server; they do not turn untrusted data into validated objects. */
export type VideoResolution = '480p' | '720p' | '1080p';
export type VideoFrameRate = 10 | 15 | 20 | 25 | 30;
export type AudioProfile = 'normal' | 'speech';
export type CommandShell = 'powershell' | 'pwsh' | 'cmd' | 'sh' | 'bash';
export interface TerminalSettings {
  camera: string;
  microphone: string;
  speaker: string;
}
/** Request bodies stay unknown until their individual fields are validated. */
export type JsonObject = Record<string, unknown>;
export interface AutoAnswerSettings {
  auto_answer?: boolean;
  auto_answer_seconds?: number;
}
export interface AccountFields extends AutoAnswerSettings {
  name: string;
  type: Account['type'];
  emails?: string[];
  photo?: string;
}
export interface AccountDetails {
  name: string;
  password: string;
  emails: string[];
  photo?: string;
}
export interface TerminalAccount extends AccountDetails {
  type: 'terminal';
  device_id: string;
  device_token: string;
  auto_answer: boolean;
  auto_answer_seconds: number;
}
export interface LinphoneAccount extends AccountDetails {
  type: 'linphone';
}
export type Account = TerminalAccount | LinphoneAccount;
export interface TerminalProfile {
  display_name: string;
  language: string;
  command_shell: CommandShell;
  audio_profile: AudioProfile;
  video_resolution: VideoResolution;
  video_fps: VideoFrameRate;
  auto_framing: boolean;
  carousel_portraits: 3 | 5;
  tv_idle_seconds: number;
  c20_speaker_volume: number;
  terminal_settings: TerminalSettings;
  /** Retained in older snapshots; current contacts are derived from accounts. */
  contacts?: { id: string }[];
}
export interface Group {
  name: string;
  description: string;
  members: string[];
}
export interface ServerState {
  schema_version: number;
  configuration_version: number;
  host: string;
  sip_port: number;
  http_port: number;
  admin_token: string;
  /** Legacy migration input only; current credentials use admin-password.json. */
  admin_password_hash?: string;
  local_terminal_id: string | null;
  users: Record<string, Account>;
  profiles: Record<string, TerminalProfile>;
  groups: Record<string, Group>;
  callback_settings: { email_after_hours: number; remove_after_hours: number };
  smtp: {
    enabled: boolean;
    host: string;
    port: number;
    security: string;
    username: string;
    password: string;
    from: string;
  };
}
export interface Enrollment {
  server_url: string;
  device_id: string;
  device_token: string;
}
export interface TerminalContact {
  id: string;
  name: string;
  photo: string;
  can_call: boolean;
  can_receive: boolean;
  auto_answer: boolean;
  sip_uri: string;
  online?: boolean;
}
export interface TerminalConfiguration {
  schema_version: number;
  configuration_version: number;
  device_id: string;
  account_type: 'terminal';
  display_name: string;
  language: string;
  command_shell: CommandShell;
  audio_profile: AudioProfile;
  video_resolution: VideoResolution;
  video_fps: VideoFrameRate;
  auto_framing: boolean;
  carousel_portraits: 3 | 5;
  tv_idle_seconds: number;
  c20_speaker_volume: number;
  server_host: string;
  sip_port: number;
  auto_answer: boolean;
  auto_answer_seconds: number;
  call_auth_key: string;
  sip: { username: string; password: string; domain: string; proxy: string };
  contacts: TerminalContact[];
  terminal_settings: TerminalSettings;
  callbacks?: CallbackView[];
}
export interface CallbackView {
  id: string;
  from: string;
  to: string;
  status: 'pending' | 'completed' | 'cancelled' | 'expired';
  created_at: string;
  email_due_at: string;
  expires_at: string;
  notified_at: string | null;
  emailed_at: string | null;
  finished_at?: string;
  from_name: string;
  to_name: string;
  ready: boolean;
  email_sent_to?: string[];
  email_error?: string | null;
}
export interface MediaSocket {
  socket: import('node:dgram').Socket;
  port: number;
}
export interface MediaTarget {
  address: string;
  port: number;
}
export interface MediaLeg {
  rtp: MediaSocket;
  rtcp: MediaSocket;
  peer?: string;
  rtpTarget?: MediaTarget | null;
  rtcpTarget?: MediaTarget | null;
}
export interface MediaSession {
  streams: MediaLeg[][];
  allocations: Map<number, Promise<MediaLeg[]>>;
  closed: boolean;
  created: number;
  touched?: number;
}
export interface MediaUpdate {
  session: MediaSession;
  changes: Map<
    string,
    { index: number; side: number; state: Pick<MediaLeg, 'peer' | 'rtpTarget' | 'rtcpTarget'> }
  >;
  allocated: Set<number>;
  active: boolean;
}

/** Durable callback state; derived names/readiness are added only for API views. */
export interface CallbackRecord extends Omit<CallbackView, 'from_name' | 'to_name' | 'ready'> {
  email_sent_to: string[];
  email_error: string | null;
  email_retry_at?: string | null;
}
export type JobStatus =
  'queued' | 'running' | 'lost' | 'completed' | 'failed' | 'timed_out' | 'cancelled';
export interface ConsoleJob {
  id: string;
  device_id?: string;
  terminal_id: string;
  command: string;
  shell: CommandShell;
  timeout_seconds: number;
  status: JobStatus;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  lease?: string;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  truncated: boolean;
}
export type ConsoleView = Omit<ConsoleJob, 'lease'>;
export type ConsoleClaim = Pick<ConsoleJob, 'id' | 'command' | 'shell' | 'timeout_seconds'> & {
  lease: string;
};
export interface Mailer {
  enabled(): boolean;
  verify(): Promise<void>;
  sendCallback(request: CallbackRecord, address: string): Promise<boolean>;
}
export type StoreInstance = InstanceType<typeof import('../store').Store>;
export type CallbackInstance = InstanceType<typeof import('../callbacks').Callbacks>;
export type SipInstance = InstanceType<typeof import('../sip-server').SipServer>;
export interface SipRegistration {
  contact: import('sip').Address;
  remote: import('sip').Remote;
  expires: number;
  reachable?: boolean;
}
export interface InviteState {
  branch?: string | number;
  cancelled: boolean;
}
export interface DialogPeer {
  user: string;
  remote: import('sip').Remote;
  contact: import('sip').Address;
  tag?: string | number | null;
}
export interface Dialog {
  ringing_timeout?: number;
  mediaUpdate?: MediaUpdate;
  peers: [DialogPeer, DialogPeer];
  touched: number;
  connected: boolean;
  queue: Promise<void>;
  invites: Map<string, InviteState>;
}
export interface SipStatus {
  registrations: { user: string; address: string; expires_at: string }[];
  active_calls: number;
  relay_sessions: number;
  events: { time: string; message: string }[];
}

export interface TerminalStatus {
  last_seen?: string;
  state?: string;
  registered?: boolean;
  camera?: string;
  microphone?: string;
  speaker?: string;
  ringer?: string;
  audio_profile?: string;
  requested_audio_profile?: string;
  auto_framing_status?: string;
  configuration_version?: number;
  devices?: Partial<Record<keyof TerminalSettings, string[]>>;
}
export type AdminModel = ReturnType<StoreInstance['admin']> & {
  sip_status: SipStatus;
  terminal_statuses: Record<string, TerminalStatus>;
  terminal_status: TerminalStatus;
  callbacks: CallbackView[];
};
export type ApiResult<U extends string> = U extends '/api/auth/status'
  ? { setup_required: boolean; can_setup: boolean }
  : U extends '/api/server/ssh'
    ? { supported: boolean; enabled?: boolean; active?: boolean; interface?: string }
    : U extends '/api/admin'
      ? AdminModel
      : U extends '/api/admin/live'
        ? Pick<
            AdminModel,
            | 'configuration_version'
            | 'sip_status'
            | 'terminal_statuses'
            | 'terminal_status'
            | 'callbacks'
          >
        : U extends '/api/photos'
          ? { photo: string }
          : U extends `/api/terminals/${string}/console`
            ? { jobs: ConsoleView[]; id: string }
            : U extends `/api/terminal-bootstrap${string}`
              ? Enrollment
              : { ok: boolean; id: string; configuration_version?: number };
