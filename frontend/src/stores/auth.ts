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

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      apiKey: null,
      userEmail: null,
      setCredentials: (apiKey, email) => {
        set({ apiKey, userEmail: email });
        localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey, email }));
      },
      clear: () => {
        set({ apiKey: null, userEmail: null });
        localStorage.removeItem("pptagent.auth");
      },
    }),
    { name: "pptagent-auth" },
  ),
);
