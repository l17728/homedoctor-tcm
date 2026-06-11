import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

interface ElderlyModeContextType {
  isElderlyMode: boolean;
  toggle: () => void;
  setElderly: (value: boolean) => void;
}

const ElderlyModeContext = createContext<ElderlyModeContextType>({
  isElderlyMode: false,
  toggle: () => {},
  setElderly: () => {},
});

const STORAGE_KEY = 'family_doctor_elderly_mode';

export function ElderlyModeProvider({ children }: { children: ReactNode }) {
  const [isElderlyMode, setIsElderlyMode] = useState<boolean>(() => {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(isElderlyMode));
    if (isElderlyMode) {
      document.body.classList.add('elderly-mode');
    } else {
      document.body.classList.remove('elderly-mode');
    }
  }, [isElderlyMode]);

  const toggle = () => setIsElderlyMode((prev) => !prev);
  const setElderly = (value: boolean) => setIsElderlyMode(value);

  return (
    <ElderlyModeContext.Provider value={{ isElderlyMode, toggle, setElderly }}>
      {children}
    </ElderlyModeContext.Provider>
  );
}

export function useElderlyMode() {
  return useContext(ElderlyModeContext);
}
