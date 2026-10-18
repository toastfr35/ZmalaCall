import type { AdminModel } from './contracts';
export interface AdminState {
  model: AdminModel;
  busy: boolean;
  restoring?: boolean;
  initialized: boolean;
  editingId: string;
  detailsId: string;
  terminalId: string;
  editingGroupId: string;
  groupVersion?: number;
  accountPhoto: string;
  accountPreviewUrl?: string;
  accountSearch: string;
  accountFilter: string;
  photoUrls: Map<HTMLImageElement, string>;
  renderedVersion?: number;
  renderedLive: string;
  consoleId: string;
  consoleSignature: string;
  consoleFetching: boolean;
  terminalCards: Map<string, HTMLElement>;
  refresh(force?: boolean): Promise<void>;
  renderConnection(): void;
}
export type Action = () => unknown | Promise<unknown>;
