import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { appliquerLangue } from "../i18n";
import "../shared/styles/global.css";
import { appliquerTheme, themeEnregistre } from "../shared/theme";
import { creerRouteur } from "./routes";
import { brancherSessionPerdue } from "./sessionPerdue";

const requetes = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 } },
});
const routeur = creerRouteur({ queryClient: requetes });

brancherSessionPerdue(requetes, routeur);

appliquerTheme(themeEnregistre());
const demandee = new URLSearchParams(window.location.search).get("langue") ?? navigator.language.slice(0, 2);
void appliquerLangue(demandee).then(() => {
  createRoot(document.getElementById("racine") as HTMLElement).render(
    <StrictMode>
      <QueryClientProvider client={requetes}>
        <RouterProvider router={routeur} />
      </QueryClientProvider>
    </StrictMode>,
  );
});
