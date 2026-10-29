# React → Next.js Migration Plan

> **Status: later.** Start this after the Django rebuild is finished. Until then, the React app
> is the fixed spec the Django API is tested against. If both ends change at once, you can't
> tell which side broke when a page fails.

The target is toskie-web's frontend architecture (`D:\Tech\toskie-web`, Next.js 16, App Router),
with requests flowing through five layers:

**types → zod → services → hooks → BFF route**

1. [Why migrate](#1-why-migrate)
2. [The five layers](#2-the-five-layers)
3. [One feature end to end](#3-one-feature-end-to-end)
4. [The BFF layer](#4-the-bff-layer)
5. [Auth and route protection](#5-auth-and-route-protection)
6. [Public pages and SEO](#6-public-pages-and-seo)
7. [Migration steps](#7-migration-steps)
8. [Gotchas](#8-gotchas)

---

## 1. Why migrate

1. **SEO, the main reason.** Every page is rendered in the browser today, so crawlers and link
   previews see an empty page. Course pages are the app's organic surface. See section 3 of
   [reference/docs/PLATFORM_PLAN_COMPREHENSIVE.md](../reference/docs/PLATFORM_PLAN_COMPREHENSIVE.md).
2. **A BFF layer.** The browser talks only to the Next.js domain. The session cookie becomes
   first-party (`SameSite=Lax`), the Django URL stays private, and Django needs no CORS in
   production.
3. **Learning Next.js App Router**, using conventions already proven in toskie-web.

---

## 2. The five layers

```
Component
  └─ hook      src/hooks/            React Query: query keys, caching, toasts
      └─ service   src/services/     one function per endpoint: axios → /api/..., checks `success`
          └─ BFF route   src/app/api/<group>/<action>/route.ts
              │          reads the cookie, calls Django server-to-server, passes cookies back
              └─ Django  /api/v1/<group>/<action>

types   src/types/             response shapes, used by every layer above
zod     src/zod-validations/   request payload schemas; forms validate with them, and
                               z.infer<> gives services and hooks their payload types
```

Four of the five layers already exist in this frontend, with the same shape as toskie-web:

| Layer | Folder | Job | Today |
|---|---|---|---|
| types | [frontend/src/types/](../frontend/src/types/) | Response shapes per endpoint | Done (auth, course, payment, api envelope) |
| zod | [frontend/src/zod-validations/](../frontend/src/zod-validations/) | Payload schemas, form validation, `z.infer` payload types | Done (auth, contact, course, settings) |
| services | [frontend/src/services/](../frontend/src/services/) | One function per endpoint; throws when `success` is false | Done, but they call Django directly |
| hooks | [frontend/src/hooks/](../frontend/src/hooks/) | `useQuery` / `useMutation` wrappers with key factories (`authKeys`, `courseKeys`) | Done |
| BFF route | `src/app/api/` | Server-side hop to Django | **New** |

So the migration mostly means adding the last layer and moving pages into the App Router. The
other four layers carry over almost unchanged.

---

## 3. One feature end to end

**Reference: toskie-web's address feature**

| Layer | File in `D:\Tech\toskie-web\src` |
|---|---|
| types | `types/address.types.ts` |
| zod | `zod-validations/address.validation.ts` (`createUpdateAddressSchema` and its `z.infer` payload type) |
| service | `services/address.services.ts` (`axiosClient.get('/address/get-addresses')`; the client's `baseURL` is `'/api'`) |
| hook | `hooks/useAddress.ts` (an `addressKeys` factory, `useGetAllAddresses`, mutations with toasts) |
| BFF route | `app/api/address/get-addresses/route.ts` |

**StudySphere: enrolled courses, after the migration**

| Layer | What it holds |
|---|---|
| types | The enrolled-course shape in `src/types/course.types.ts`, unchanged |
| zod | Nothing; a GET has no payload. Mutations such as `updateProfile` use a schema + `z.infer`. |
| service | `fetchEnrolledCourses()` calls `axiosClient.get('/profile/getEnrolledCourses')`, unchanged apart from the client's `baseURL` |
| hook | `useEnrolledCourses()`, a `useQuery` keyed on the profile key factory, unchanged |
| BFF route | `src/app/api/profile/getEnrolledCourses/route.ts`, **new** (see below) |

Because each BFF path mirrors the Django path, services keep their URLs. Only `baseURL` changes,
from `VITE_BASE_URL` to `'/api'`.

---

## 4. The BFF layer

### How it differs from toskie-web

toskie-web has 197 route handlers because its backend speaks GraphQL. Each handler translates a
REST call into a GraphQL query and reshapes the result into the frontend's envelope. Django
already returns the exact `{ success, message, data }` shape, so most StudySphere routes are
plain forwarders. Write the forwarding once, in a shared helper:

```ts
// src/lib/django.ts (server only)
import { NextRequest, NextResponse } from 'next/server';

export async function forwardToDjango(request: NextRequest, path: string) {
  const token = request.cookies.get('token')?.value;
  const clientIp = request.headers.get('x-forwarded-for')?.split(',')[0].trim();

  const res = await fetch(`${process.env.DJANGO_API_URL}${path}${request.nextUrl.search}`, {
    method: request.method,
    headers: {
      'Content-Type': request.headers.get('content-type') ?? 'application/json',
      ...(token ? { Cookie: `token=${token}` } : {}),
      ...(clientIp ? { 'X-Forwarded-For': clientIp } : {}),
    },
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.text(),
    cache: 'no-store',
  });

  const data = await res
    .json()
    .catch(() => ({ success: false, message: 'Unexpected response from the API' }));
  const response = NextResponse.json(data, { status: res.status });

  // Login and logout set or clear the session cookie; re-emit it on the Next.js domain.
  for (const cookie of res.headers.getSetCookie()) {
    response.headers.append('set-cookie', cookie);
  }
  return response;
}
```

Each route file then takes one line:

```ts
// src/app/api/profile/getEnrolledCourses/route.ts
import { NextRequest } from 'next/server';
import { forwardToDjango } from '@/lib/django';

export const GET = (request: NextRequest) =>
  forwardToDjango(request, '/profile/getEnrolledCourses');
```

Write a fuller handler only where the BFF does real work: combining calls, trimming a response,
or adding server-only secrets.

### Environment

| Variable | Where it's read | Notes |
|---|---|---|
| `DJANGO_API_URL` | Server only | e.g. `http://localhost:8000/api/v1`. No `NEXT_PUBLIC_` prefix, so the browser never sees it. |
| `NEXT_PUBLIC_RAZORPAY_KEY` | Browser | Replaces `VITE_RAZORPAY_KEY` |

---

## 5. Auth and route protection

- **The cookie stays Django's.** Django sets `token` on its login response; `forwardToDjango`
  passes the `Set-Cookie` through, so the browser stores it on the Next.js domain. With
  everything same-site, set it `SameSite=Lax; Secure` in production.
- **`proxy.ts` replaces `PrivateRoute` and `OpenRoute`.** Next.js 16 calls middleware
  `proxy.ts`. It runs before a page renders and can redirect based on the `token` cookie, so a
  protected page never flashes before redirecting. See toskie-web's `src/proxy.ts` and
  `src/lib/routePolicy.ts`.
- **Keep the 401 interceptor.** `lib/axiosClient.ts` still clears auth state on a 401 and sends
  the user to `/login` from protected pages, now through `/api`.
- **CORS goes away in production.** Django only receives server-to-server calls from Next.js,
  which carry no `Origin` header. Keep the origin-check middleware anyway, for anyone who calls
  Django directly.

---

## 6. Public pages and SEO

- **Server components for the public routes:** `/`, `/catalog/[category]` and
  `/courses/[courseId]`. They call Django directly from the server, without the BFF hop, and
  return real HTML.
- **Add `generateMetadata`** per page (title, description, Open Graph), **`Course` JSON-LD** on
  course pages, and a database-driven **`sitemap.ts`**. toskie-web has all three to copy from.
- **Keep the dashboard client-side.** It sits behind login and gains nothing from server
  rendering. Mark it `'use client'` and let React Query work as it does today.
- **API improvement to consider:** `getCourseDetails` and `getCategoryPageDetails` are POSTs in
  the current contract. GET versions in Django would be easier to cache for public pages.

---

## 7. Migration steps

1. **Scaffold** a Next.js app in `frontend-next/` beside `frontend/`, with TypeScript, Tailwind
   and the `@/` alias. The old app keeps running until the new one replaces it.
2. **Copy the unchanged layers:** `types/`, `zod-validations/`, `data/`, `assets/`, `styles/`.
3. **Port `lib/axiosClient.ts`** with `baseURL: '/api'`, keeping the 401 interceptor.
4. **Add `lib/django.ts`** and the BFF routes, one endpoint group at a time: auth (the cookie
   pass-through) first, then profile, course, payment and contact.
5. **Copy `services/` and `hooks/`.** They should need little or no change.
6. **Providers:** put React Query, Redux (the cart, course and view-course slices) and the
   Zustand auth store in a `'use client'` providers component in the root layout.
7. **Routes:** move React Router routes (37 files import `react-router`) to App Router folders,
   and replace `PrivateRoute` / `OpenRoute` with `proxy.ts`.
8. **Public pages:** convert home, catalog and course details to server components with
   metadata, JSON-LD and the sitemap.
9. **Switch over:** deploy `frontend-next/`, check every page against Django, then delete
   `frontend/` and rename the folder.

---

## 8. Gotchas

1. **Don't send uploads through the BFF.** Serverless hosts cap request body size (Vercel's limit
   is 4.5 MB) and time out long requests, so thumbnails and lecture videos would fail. Upload
   from the browser straight to Cloudinary with a signed upload that Django signs, then send
   Django the resulting URL. toskie-web does the same with S3 presigned URLs and a separate
   axios instance outside `/api` (`src/services/video-upload.service.ts`).
2. **Rate limiting sees one IP.** Every request reaches Django from the Next.js server. Forward
   the browser's IP (`forwardToDjango` sets `X-Forwarded-For`; toskie-web's
   `lib/apollo-server-client.ts` does the same) and configure Django to trust exactly that one
   hop. Otherwise all users share one rate-limit bucket.
3. **Browser-only code.** About 10 files use `window`, `document` or `localStorage`, and
   libraries like `react-player`, `swiper` and `chart.js` need the browser. Keep them in
   `'use client'` components, and load the heaviest with `next/dynamic` and `ssr: false`.
4. **Hydration mismatches.** Anything that differs between server and browser (dates, random
   values, `localStorage` reads during render) causes React hydration warnings. Read browser
   state in `useEffect`.
5. **`params` is a Promise.** In current Next.js, page and route `params` must be awaited:
   `const { courseId } = await params;`.
