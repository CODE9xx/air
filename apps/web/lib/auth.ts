// In-memory access token store. Refresh-токен живёт в httpOnly cookie code9_refresh
// и автоматически отправляется браузером с credentials: 'include'.
// Никогда не используем localStorage для токенов (см. docs/security/AUTH.md).

type Listener = (token: string | null) => void;

class TokenStore {
  private token: string | null = null;
  private listeners = new Set<Listener>();

  get(): string | null {
    return this.token;
  }

  set(token: string | null): void {
    this.token = token;
    this.listeners.forEach((l) => l(token));
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  clear(): void {
    this.set(null);
  }
}

// User access store.
export const userTokenStore = new TokenStore();

// Admin access store — отдельный, с другим JWT-секретом на бэке.
export const adminTokenStore = new TokenStore();
