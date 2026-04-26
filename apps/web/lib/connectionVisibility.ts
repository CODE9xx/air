import type { CrmConnection } from './types';

export function isCustomerVisibleCrmConnection(connection: CrmConnection): boolean {
  if (connection.status === 'deleted') return false;
  if (connection.metadata?.mock === true) return false;
  if (connection.external_domain === 'mock-amo.local') return false;
  if (connection.name === 'amoCRM (mock)') return false;
  return true;
}
