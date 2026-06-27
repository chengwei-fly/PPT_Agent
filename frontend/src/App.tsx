import { AppLayout } from "@/components/layout/AppLayout";
import { AppRouter } from "@/router";

/** Root component — wires layout around the router. */
export default function App() {
  return (
    <AppLayout>
      <AppRouter />
    </AppLayout>
  );
}
