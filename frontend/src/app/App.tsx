import { BrowserRouter } from "react-router-dom";
import { ErrorBoundary } from "./ErrorBoundary";
import { HermesProvider } from "./hermes";
import { AppRoutes } from "./routes";

export function App() {
  return (
    <HermesProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ErrorBoundary>
    </HermesProvider>
  );
}
