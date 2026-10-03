import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";

import Layout from "../components/Layout";
import {
  RedirectIfAuthenticated,
  RequireAuth,
  RequireRole,
} from "../components/RouteGuards";
import { Skeleton } from "../components/ui";

/**
 * Route tree.
 *
 * Everything below the shell is **lazily loaded**, so the initial bundle stays small
 * (the landing page does not ship the quiz engine or the admin tables) while the
 * shared shell renders immediately.
 *
 * Guard placement encodes the intended audience:
 *
 * * public          — Home, Courses, CourseDetails
 * * auth-only       — Dashboard, Watch, Quiz, Leaderboard, Subscription, Profile
 * * staff-only      — the whole /admin branch (instructor + admin)
 *
 * These guards are UX only. The API enforces the same rules independently, so a
 * student who bypasses the router still receives 401/403 responses.
 */

const Home = lazy(() => import("../pages/Home/Home"));
const Courses = lazy(() => import("../pages/Courses/Courses"));
const CourseDetails = lazy(
  () => import("../pages/CourseDetails/CourseDetails"),
);
const VideoPlayerPage = lazy(
  () => import("../pages/VideoPlayer/VideoPlayerPage"),
);
const Dashboard = lazy(() => import("../pages/Dashboard/Dashboard"));
const Quiz = lazy(() => import("../pages/Quiz/Quiz"));
const QuizResult = lazy(() => import("../pages/Quiz/QuizResult"));
const Leaderboard = lazy(() => import("../pages/Leaderboard/Leaderboard"));
const Subscription = lazy(() => import("../pages/Subscription/Subscription"));
const Profile = lazy(() => import("../pages/Profile/Profile"));
const Progress = lazy(() => import("../pages/Profile/Progress"));
const Notifications = lazy(() =>
  import("../pages/Profile/Progress").then((m) => ({
    default: m.Notifications,
  })),
);

const Login = lazy(() => import("../pages/Auth/Login"));
const Register = lazy(() => import("../pages/Auth/Register"));
const ForgotPassword = lazy(() => import("../pages/Auth/ForgotPassword"));
const VerifyEmail = lazy(() =>
  import("../pages/Auth/ForgotPassword").then((m) => ({
    default: m.VerifyEmail,
  })),
);
const NotFound = lazy(() =>
  import("../pages/Auth/ForgotPassword").then((m) => ({ default: m.NotFound })),
);

const AdminDashboard = lazy(() => import("../pages/Admin/AdminPages"));
const AdminUsers = lazy(() =>
  import("../pages/Admin/AdminPages").then((m) => ({ default: m.AdminUsers })),
);
const AdminCourses = lazy(() =>
  import("../pages/Admin/AdminPages").then((m) => ({
    default: m.AdminCourses,
  })),
);
const AdminSubscriptions = lazy(() =>
  import("../pages/Admin/AdminPages").then((m) => ({
    default: m.AdminSubscriptions,
  })),
);
const AdminPayments = lazy(() =>
  import("../pages/Admin/AdminPages").then((m) => ({
    default: m.AdminPayments,
  })),
);
const AdminVideos = lazy(() =>
  import("../pages/Admin/AdminPages").then((m) => ({ default: m.AdminVideos })),
);
const AdminQuizzes = lazy(() =>
  import("../pages/Admin/AdminPages").then((m) => ({
    default: m.AdminQuizzes,
  })),
);
const AdminLeaderboard = lazy(() =>
  import("../pages/Admin/AdminPages").then((m) => ({
    default: m.AdminLeaderboard,
  })),
);

/** Route-level fallback: matches the page rhythm so nothing jumps on load. */
function RouteFallback() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10" aria-busy="true">
      <Skeleton className="h-9 w-64" />
      <Skeleton className="mt-6 h-40 w-full" />
      <span className="sr-only">Loading page…</span>
    </div>
  );
}

const STAFF_ROLES = ["instructor", "admin"];

export default function AppRoutes() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route element={<Layout />}>
          {/* ------------------------------------------------------ Public */}
          <Route index element={<Home />} />
          <Route path="courses" element={<Courses />} />
          <Route path="courses/:slug" element={<CourseDetails />} />

          {/* -------------------------------- Auth pages (anonymous only) */}
          <Route element={<RedirectIfAuthenticated />}>
            <Route path="login" element={<Login />} />
            <Route path="register" element={<Register />} />
          </Route>

          {/* Always reachable: a signed-in student may still need these. */}
          <Route path="forgot-password" element={<ForgotPassword />} />
          <Route path="reset-password" element={<ForgotPassword />} />
          <Route path="verify-email" element={<VerifyEmail />} />

          {/* ------------------------------------------- Authenticated only */}
          <Route element={<RequireAuth />}>
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="watch/:lessonId" element={<VideoPlayerPage />} />
            <Route path="quiz/:quizId" element={<Quiz />} />
            <Route path="quiz/:quizId/result" element={<QuizResult />} />
            <Route path="leaderboard" element={<Leaderboard />} />
            <Route path="subscription" element={<Subscription />} />
            <Route path="profile" element={<Profile />} />
            <Route path="progress" element={<Progress />} />
            <Route path="notifications" element={<Notifications />} />
          </Route>

          {/* -------------------------------------------------- Staff only */}
          <Route element={<RequireRole roles={STAFF_ROLES} />}>
            <Route path="admin" element={<AdminDashboard />} />
            <Route path="admin/courses" element={<AdminCourses />} />
            <Route path="admin/courses/:id" element={<AdminCourses />} />
            <Route
              path="admin/subscriptions"
              element={<AdminSubscriptions />}
            />
            <Route path="admin/payments" element={<AdminPayments />} />
            <Route path="admin/videos" element={<AdminVideos />} />
            <Route path="admin/quizzes" element={<AdminQuizzes />} />
            <Route path="admin/leaderboard" element={<AdminLeaderboard />} />
          </Route>

          {/* -------------------------------------------------- Admin only */}
          <Route element={<RequireRole roles={["admin"]} />}>
            <Route path="admin/users" element={<AdminUsers />} />
          </Route>

          {/* --------------------------------------------------------- 404 */}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
