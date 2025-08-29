# habit-lifestyle-tracker
Personal Habit, Diary, Goals and Rewards Tracker

# UI
React based front end compiled by npm hosting recharts and grommet components
### Five key pages:
- Dashboard
    * High level habit tracking summary
    * High level synthesized daily summary
    * Some nice quotes / motivation / graphics
    * etc.
- Data Intake
    * STARTUP: add goals, correlate with points, create activity groups and metrics for each
    * DAILY HABIT: 
    * DAILY ENTRY: dump your day! do voice to text, give your morning, afternoon and evening a rating. Give a high low buffalo

# API
Backend Flask server to access DB and return data
### Tables:
- Users
    * username
    * password HASH
    * point total (earned)
    * point total (spent)
- Goals
    * What
    * Category
    * Point value
    * Metric (enum): minutes / times done / events / other?
    * emoji
    * details
- Rewards
    * What
    * Cateory
    * Point value
    * emoji (image png link?)
    * Repeatable (bool) -> can show user available count
- Goals_entries
    * What
    * Category
    * Count of 'metrics'
    * Points earned (calculated / derived)
- Hi_lo_Buffalo
    * High (str)
    * Low (str)
    * Day Summary (text -> as large as possible dump)
    * Rating (or mood? AM/PM/evening)
- Hi_lo_Buffalo_Summarized --> derived from chatGPT
    * TODO
- CACHE / other derived tables
    * TODO

# PROCESSES:
**Summarizer.py**: Daemon process to use openAI API to create daily/weekly/monthly/yearly summaries of HIGHS and gratefulness categories. Maybe also give the user some compliments

# TESTING
Set Browser to Iphone aspect ratio mode 
UTs for APIs, coverage / leakage for data interity

# ARCHITECTURE
- A **flask** api server served by gunicorn on localhost will provide data
- a **React** Front End server served by (? not actually sure - apache ?) will provide UI on localhost
- A **Cloudflare** reverse tunnel will allow the site to be shown securely on the web under my suubdomain after I register habits.samellgass.com securely
- A **MySQL** DB will be our persistent data store for user, submitmted and derived data 