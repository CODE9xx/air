// Реэкспорт shared-типов + локальные UI-расширения.
// При желании можно сменить на путь '@code9/shared' через workspace-резолв.
export * from '../../../packages/shared/typescript';

export interface ToastMessage {
  id: string;
  kind: 'success' | 'error' | 'info' | 'warning';
  title: string;
  description?: string;
}
