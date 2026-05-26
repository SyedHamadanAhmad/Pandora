import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { StorybookShell } from "../features/storybook/StorybookShell";
import { LoginPage } from "../pages/LoginPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { StorybookComponentPage } from "../pages/StorybookComponentPage";
import { StorybookOverviewPage } from "../pages/StorybookOverviewPage";
import { ProtectedRoute } from "./ProtectedRoute";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <Navigate to="/projects" replace /> },
          { path: "/projects", element: <ProjectsPage /> },
          {
            path: "/projects/:projectId/storybook",
            element: <StorybookShell />,
            children: [
              { index: true, element: <StorybookOverviewPage /> },
              {
                path: "components/:componentId",
                element: <StorybookComponentPage />,
              },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/login" replace /> },
]);
