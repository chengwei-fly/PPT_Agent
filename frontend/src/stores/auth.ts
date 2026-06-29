import { create } from "zustand";
import { persist } from "zustand/middleware";

/** Auth + dev key store. Persists to localStorage so reloads
 * don't kick the user out of the dev environment. */
export interface AuthState {
  apiKey: string | null;
  userEmail: string | null;
  setCredentials: (apiKey: string, email: string) => void;
  clear: () => void;
}

const DEV_KEY = "dev-key";
const DEV_EMAIL = "dev@pptagent.local";

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      apiKey: DEV_KEY,
      userEmail: DEV_EMAIL,
      setCredentials: (apiKey, email) => {
        set({ apiKey, userEmail: email });
        localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey, email }));
      },
      clear: () => {
        set({ apiKey: DEV_KEY, userEmail: DEV_EMAIL });
        localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey: DEV_KEY, email: DEV_EMAIL }));
      },
    }),
    {
      name: "pptagent-auth",
      onRehydrateStorage: () => {
        return (state) => {
          // Ensure dev key and auth token are always available for development
          if (!state || !state.apiKey) {
            state?.setCredentials(DEV_KEY, DEV_EMAIL);
          }
          // Sync with the key that the api client reads
          const current = state?.apiKey ?? DEV_KEY;
          const email = state?.userEmail ?? DEV_EMAIL;
          localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey: current, email }));
        };
      },
    },
  ),
);
