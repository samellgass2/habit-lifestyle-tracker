# habit-lifestyle-tracker

A personal habit, reflection and rewards tracker. **Hosted by adamOS since
2026-10-12.**

## Where it runs now

| Piece | Lives in | Notes |
|---|---|---|
| **UI** (`UI/`, React + Vite + Grommet) | this repo; served by the adamOS gateway at **`/apps/habits/`** on the Experiences surface | Built by adamOS's generic L3 deploy target from the `MVP-BRANCH` branch: `npm install && npm run build -- --base=/apps/habits/`, publishing `UI/dist`. |
| **API** | adamOS `closedclaw-controlplane/api-server/habit_tracker/` (the `/habit-tracker` blueprint; the browser calls `/api/habit-tracker/*`) | The Flask routes were ported route for route, so the points economy is unchanged. adamOS is the `habits` database's sole writer. |
| **Data** | the `habits` database in the adamOS cluster MySQL | Unchanged tables, plus the week planner's plan columns and `adamos_user_links` (habits migration 001). |
| **Identity** | adamOS sign-in | No habit login any more. Your adamOS account is linked to a habits profile (`adamos_user_links`); an unlinked account sees "ask Sam to link it". |
| **AI jobs** (summaries, gratitude cloud, motivation, weekly focus) | moving to the adamOS scheduler | Still in `Processes/` until the scheduler jobs land; they already call adamOS compute under project `habits`. |

Design and rationale: adamOS `docs/specs/WEEK_PLANNER_CALENDAR_2026_10_12.md` §7.
The habit tracker is the **recurring-intent authority** for the week planner:
habits with a plan (`plan_mode` slot/opportunistic, `weekly_target`,
`slot_minutes`, …) are what Adam places on Sam's calendar.

## Pages

- **Home** (`/dashboard`): today's summary, AI motivation and focus, charts.
- **Reflect** (`/reflect`): the daily log (summary, highs, lows, buffalos, mood, gratitude).
- **Track** (`/track`): check habits off, create habits (by hand or AI-assisted), history.
- **Rewards** (`/rewards`): spend points on rewards.
- **Me** (`/account`): profile and accent.

The social layer (friends, feed, reactions, gifts, inbox) has been unused since
spring 2026. Its API and data are kept, but the UI is hidden unless the build sets
`VITE_SOCIAL=1`.

## Developing the UI

```bash
cd UI
npm install
ADAMOS_GATEWAY=http://127.0.0.1:5001 npm run dev   # proxies /api to a local adamOS gateway
npm run build -- --base=/apps/habits/
```

## Legacy (retiring at cutover)

`Server/` (the old Flask API, gunicorn on the Intel host behind the `dev-hab`
tunnel) and `Processes/` (OS-cron AI jobs) are the pre-adamOS stack. They keep
running until the hosted app is verified and the Intel stack is switched off.
Then they are removed from this repo.
