import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { SessionClient, sessionClient } from "./session";

const Context = createContext<SessionClient | null>(null);
export function AuthProvider({
  children,
  client = sessionClient,
}: {
  children: ReactNode;
  client?: SessionClient;
}) {
  useEffect(() => {
    const close = client.connect();
    void client.initialize();
    return close;
  }, [client]);
  return <Context.Provider value={client}>{children}</Context.Provider>;
}
export function useAuth() {
  const client = useContext(Context);
  if (!client) throw new Error("AuthProvider is required");
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot);
  return { ...state, client };
}
