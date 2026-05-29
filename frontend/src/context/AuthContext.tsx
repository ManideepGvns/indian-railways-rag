import React, {
  createContext, useContext, useState, useCallback, useEffect, useRef,
} from "react";
import api from "../api/client";

const IDLE_MS       = 15 * 60 * 1000;   // 15 minutes
const WARN_BEFORE_MS =  1 * 60 * 1000;  // show warning 1 min before logout

interface User { id: number; username: string; is_admin: boolean }
interface AuthCtx {
  user: User | null;
  idleWarning: boolean;           // true when <1 min remaining
  login:  (username: string, password: string) => Promise<void>;
  logout: () => void;
  resetIdleTimer: () => void;     // can be called by any component on activity
}

const AuthContext = createContext<AuthCtx | null>(null);

const ACTIVITY_EVENTS = [
  "mousemove", "mousedown", "keydown", "scroll", "touchstart", "click",
] as const;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem("ir_user");
    return raw ? JSON.parse(raw) : null;
  });
  const [idleWarning, setIdleWarning] = useState(false);

  const logoutTimer   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warningTimer  = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doLogout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* best-effort */ }
    localStorage.removeItem("ir_token");
    localStorage.removeItem("ir_user");
    setUser(null);
    setIdleWarning(false);
  }, []);

  const resetIdleTimer = useCallback(() => {
    if (logoutTimer.current)  clearTimeout(logoutTimer.current);
    if (warningTimer.current) clearTimeout(warningTimer.current);
    setIdleWarning(false);

    warningTimer.current = setTimeout(
      () => setIdleWarning(true),
      IDLE_MS - WARN_BEFORE_MS,
    );
    logoutTimer.current = setTimeout(doLogout, IDLE_MS);
  }, [doLogout]);

  // Start/stop idle timers whenever auth state changes
  useEffect(() => {
    if (!user) {
      if (logoutTimer.current)  clearTimeout(logoutTimer.current);
      if (warningTimer.current) clearTimeout(warningTimer.current);
      setIdleWarning(false);
      return;
    }

    const handleActivity = () => resetIdleTimer();

    ACTIVITY_EVENTS.forEach((e) =>
      window.addEventListener(e, handleActivity, { passive: true }),
    );
    resetIdleTimer(); // arm immediately on login

    return () => {
      ACTIVITY_EVENTS.forEach((e) =>
        window.removeEventListener(e, handleActivity),
      );
      if (logoutTimer.current)  clearTimeout(logoutTimer.current);
      if (warningTimer.current) clearTimeout(warningTimer.current);
    };
  }, [user, resetIdleTimer]);

  const login = useCallback(async (username: string, password: string) => {
    const { data } = await api.post("/auth/login", { username, password });
    localStorage.setItem("ir_token", data.access_token);
    const me: User = {
      id: data.user_id,
      username: data.username,
      is_admin: data.is_admin ?? false,
    };
    localStorage.setItem("ir_user", JSON.stringify(me));
    setUser(me);
  }, []);

  const logout = useCallback(() => { doLogout(); }, [doLogout]);

  return (
    <AuthContext.Provider value={{ user, idleWarning, login, logout, resetIdleTimer }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
