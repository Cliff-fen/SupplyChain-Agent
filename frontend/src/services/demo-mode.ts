/** Demo data is an explicit preview-only opt-in. Production never falls back silently. */
export const isDemoMode = import.meta.env.VITE_DEMO_MODE === "true";

export function withDemoFallback<T>(request: () => Promise<T>, demo: () => T): Promise<T> {
  return request().catch((error) => {
    if (!isDemoMode) throw error;
    return demo();
  });
}
