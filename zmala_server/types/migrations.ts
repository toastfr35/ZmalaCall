import type { ServerState, AccountDetails, TerminalAccount, TerminalProfile } from './contracts';
export interface LegacyContact {
  id: string;
  name?: string;
  photo?: string;
  auto_answer?: boolean;
  can_call?: boolean;
  can_receive?: boolean;
}
/** Writable staging shapes for schemas 1–5, before required defaults exist.
 * Only migrations use these optional legacy fields; runtime contracts remain strict. */
export type MigrationState = Omit<ServerState, 'users' | 'profiles' | 'callback_settings'> & {
  users: Record<
    string,
    AccountDetails &
      Partial<Omit<TerminalAccount, keyof AccountDetails | 'type'>> & {
        type?: 'terminal' | 'linphone' | 'app';
      }
  >;
  profiles: Record<
    string,
    Partial<Omit<TerminalProfile, 'contacts' | 'video_resolution'>> & {
      video_resolution?: TerminalProfile['video_resolution'] | '360p';
      auto_answer_seconds?: number;
      contacts?: LegacyContact[];
    }
  >;
  permissions?: Record<string, Record<string, boolean | undefined>>;
  contacts?: LegacyContact[];
  device_id?: string;
  device_token?: string;
  display_name?: string;
  auto_answer_seconds?: number;
  terminal_settings?: TerminalProfile['terminal_settings'];
  callback_settings: ServerState['callback_settings'] & {
    email_after_minutes?: number;
    remove_after_minutes?: number;
  };
};
