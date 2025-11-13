# habit-lifestyle-tracker
Personal Habit, Diary, Goals and Rewards Tracker

# UI
React based front end compiled by npm hosting recharts and grommet components
### Five key pages:
- Dashboard (/dashboard)
    * High level habit tracking summary (derived)
    * High level synthesized daily summary (AI)
    * Focus / random inspiration (AI)
    * Some nice quotes / motivation / graphics
    * Eventual friend feed (derived)
- Reflection (/reflect)
    * Daily gratefulness exercises 
    * DAILY ENTRY: dump your day! do voice to text, give your morning, afternoon and evening a rating. Give a high low buffalo
    * Eventual additional, more interactive AI-powered reflective exercises
- Data Intake (/track)
    * STARTUP: add goals, correlate with points, create activity groups and metrics for each
    * TRACKING: check off habits, update values, earn points
    * Historical calendar view and list of accomplishments view
- Rewards (/rewards)
    * Create or receive rewards from friends that can be purchased with points
    * Spend points
- User (/account)
    * Update user profile and aesthetic
    * Manage friendships and send gifts / create shared habits

# API
Backend Flask server to access DB and return data

## API Groups
**Derived**
These API endpoints run processes on the server itself to get/transform/remove data. May interact with user-specific data when authenticated
- *login / user*: create / authenticate account 
- *daylogs*: create / update reflection + gratitude for user
- *calendar, calendar/progress*: get overview of daylog usage or overall habit completion for user
- *habits*: create / edit / delete / complete habits for user
- *points*: get / update points for user
- *rewards*: get / edit / delete rewards for user
- [WIP] *social*: add friends / send gifts/habits from user to other users


**API-Dependent**
These API endpoints run processes that interface with OpenAI API endpoints using few-shot prompting or templated prompting depending on use case
- *ai/motivation*: get (rate-limited) new motivation for user
- *habits/ai/*: get (rate-limited) habit suggestions for user
- [WIP] *social/ai/*: generate shared goals for user and another friended user

# PROCESSES:
**Summarizer.py**: Cron process to use openAI API to create daily/weekly/monthly/yearly summaries of HIGHS and gratefulness categories. Maybe also give the user some compliments

**Focus_picker.py**: Cron process to generate a weekly 'focus area' worth bonus points

**Gratitude_cloud.py**: Cron process to generate a word cloud structure from gratefulness exercise responses

**Daily_motivation.py**: On-demand or cron process to generate motivation based on user profile and accomplishments

# TESTING
Set Browser to Iphone aspect ratio mode 
UTs for APIs, coverage / leakage for data interity

# ARCHITECTURE
- A **flask** api server served by gunicorn on localhost will provide data
- a **React** Front End server served by (? not actually sure - apache ?) will provide UI on localhost
- A **Cloudflare** reverse tunnel will allow the site to be shown securely on the web under my suubdomain after I register habits.samellgass.com securely
- A **MySQL** DB will be our persistent data store for user, submitmted and derived data 