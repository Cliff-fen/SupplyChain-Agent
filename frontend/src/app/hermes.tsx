import { createContext, useContext, type ReactNode } from "react";

type HermesCapability = {
  id: string;
  label: string;
};

type HermesFramework = {
  name: "Hermes";
  version: string;
  capabilities: HermesCapability[];
};

const framework: HermesFramework = {
  name: "Hermes",
  version: "2026.08",
  capabilities: [
    { id: "session-orchestration", label: "会话编排" },
    { id: "guarded-evolution", label: "安全自进化" },
    { id: "human-gated-tools", label: "人审工具" },
  ],
};

const HermesContext = createContext<HermesFramework>(framework);

export function HermesProvider({ children }: { children: ReactNode }) {
  return (
    <HermesContext.Provider value={framework}>
      <div className="hermes-root-frame" data-framework={framework.name.toLowerCase()}>
        {children}
      </div>
    </HermesContext.Provider>
  );
}

export function useHermes() {
  return useContext(HermesContext);
}
