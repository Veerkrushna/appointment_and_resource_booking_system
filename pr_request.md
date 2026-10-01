# Pull Request: Authentication, Photo Uploads & Dashboard Consolidation

## Description
This pull request introduces several core feature enhancements focused on user profile management (including photo uploads), user authentication, and streamlining the provider dashboard experience by consolidating the calendar page.

## Changes Included in this PR

### 1. Dashboard Consolidation (Commit `156b287b`)
- **Fix:** Removed the standalone Calendar page for providers.
- **Enhancement:** Integrated the `ProviderCalendarWidget` directly into the `ProviderDashboardPage` for a unified and more efficient view of appointments.
- **Routing:** Cleaned up `AppRoutes.tsx` and `Navbar.tsx` to reflect the removal of the separate calendar route.

### 2. Authentication, User Management, and Photo Uploads (Commit `a727dccf`)
- **Database:** Added a new migration (`c223c51abc8a`) to include a `photo` column in the `user` table.
- **Photo Upload Functionality:**
  - Implemented the `POST /api/upload/image` endpoint in `uploads.py` for handling `.jpg` and `.jpeg` image files.
  - Added frontend support for photo uploads in the Profile section of the `Navbar.tsx`, including preview support and file size validation (max 1.5MB).
  - Configured vite proxy to serve `/uploads` directory properly during development.
- **Authentication & User Profiles:**
  - Expanded the `auth.py` and schemas to handle the new photo field during profile updates.
  - Updated `AuthContext.tsx` and `useAuth.ts` to reflect the new photo property in the user's session state.
- **Admin Features:**
  - Enhanced `AdminProvidersPage.tsx` to support the new features and better manage provider information.
- **Security & Fixes:**
  - Updated `.gitignore` to prevent uploaded files (`/uploads`) from being tracked in version control.

## Testing Instructions
1. **Photo Uploads:** Click on the profile avatar in the Navbar, click "Edit Profile", and use the "+" button to upload a `.jpg` or `.jpeg` file under 1.5MB. Save changes and verify the avatar updates across the app.
2. **Dashboard Calendar:** Log in as a provider and verify that the calendar widget is now fully functional directly on the dashboard page.
3. **Database:** Ensure migrations are run to add the `photo` column to the database successfully.

## Related Issues
- Resolves user requests regarding photo upload restrictions and dashboard consolidation.
