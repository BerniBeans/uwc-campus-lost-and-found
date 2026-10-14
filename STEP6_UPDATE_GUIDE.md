# Program Pirates — runnable Step 6 application (corrected 14 October 2026)

This ZIP contains the full Flask source, templates, migrations, and tests from the
latest supplied **Group project.zip**, with focused bug fixes. The site's original
CSS, colours, navigation, page layout, and mascot image are unchanged.

## What was fixed

1. Account creation: separately check the email and UWC identifier to avoid a
   server error when they belong to two different accounts.
2. Possible matches: do not show a found report created by the current user.
   Require at least one identifying characteristic (colour, brand, or shared
   descriptive keyword) alongside the existing rule-based match score. Display
   the score as **points out of 100**, not a statistical percentage.
3. Item photographs: new files are stored in the private `instance/uploads`
   directory. The site displays them through a login-protected route rather
   than an unrestricted static URL. Existing local photographs in
   `static/uploads` are moved there on startup. ID-document, student-card and
   wallet photos are not accepted for new reports and older photos in these
   categories are available only to the reporter/finder or an administrator.
   File extension and basic image signature bytes are checked.
4. Sessions: no hard-coded development secret key. A random key is generated
   for local development if `SECRET_KEY` is unset, but hosted configurations
   using `DATABASE_URL` must supply `SECRET_KEY` explicitly.
5. Added integration/regression tests covering the workflows above. All
   original migrations were retained, including the student/staff identifier
   revision `c92410bfc0d1`.

The account-type selector records what users choose; it does **not** verify
that an account actually belongs to a UWC student or staff member.

## Important: do not lose your work

When updating the existing VS Code/GitHub project, copy the contents of this
ZIP into the existing project directory (the one containing `app.py`). Replace
matching source files and **merge** the migrations directory; do not delete
prior migration scripts. **Keep your existing `.git` folder, `.venv` folder,
`.env` file, and `instance` directory**. They are not included in this ZIP.

Your existing SQLite test database is normally `instance/lost_found.db`. It
will still need the migration below if its current revision is older. Back up
important data before any real deployment changes.

## First run on Windows using PowerShell

Open the project folder in VS Code and launch **Terminal > New Terminal**.
Run commands from the directory containing `app.py`:

```powershell
# Only if you do not already have a working .venv:
py -m venv .venv

# Activate your existing/new virtual environment:
.\.venv\Scripts\Activate.ps1

# Install required packages:
python -m pip install -r requirements.txt

# Check the migration chain and update the local database:
python -m flask --app app db heads
python -m flask --app app db upgrade
python -m flask --app app db current

# Start the website:
python -m flask --app app run --debug
```

Open **http://127.0.0.1:5000**. The expected migration revision after the
upgrade is **`c92410bfc0d1 (head)`**. If your shell blocks activation, you
can run `py -m flask --app app db upgrade` after installing the dependencies
for that Python interpreter, or use `.\.venv\Scripts\python.exe` directly.

**Do not run `flask db init`, `flask db migrate`, or delete your database**
for this update. The new migration is already in `migrations/versions`.

## Optional regression tests

```powershell
python -m unittest discover -s tests -v
```

The tests run with a **temporary SQLite database** and create disposable test
accounts. They do not intentionally connect to Render or change the normal
local database. They cover registration conflicts, CSRF, student/staff login,
reporting, images, match filtering, claims, administration, notifications and
existing migration consistency.

## Push to GitHub (after checking the site locally)

```powershell
git status
git add app.py forms.py models.py extensions.py templates migrations tests static .gitignore RUN_ME_FIRST.md STEP6_UPDATE_GUIDE.md
# Check that only intended source files are staged:
git diff --cached --stat
git commit -m "Fix registration, matching and protected item images"
git push origin main
```

Never commit `.env`, passwords, the SQLite database or user-uploaded pictures.
The `.gitignore` excludes your local `instance/` and `static/uploads` files.

## Render (hosted deployment)

- Configure a secure **`SECRET_KEY`** environment variable (a long random
  secret) and your existing **`DATABASE_URL`** in Render before deployment.
- Use your existing build/start setup (for example `pip install -r
  requirements.txt`, then `gunicorn app:app`).
- The **hosted PostgreSQL database also needs the migration**. Run
  `python -m flask --app app db upgrade` against that hosted database in a
  safe deploy/migration step. Running the command locally against SQLite only
  updates the local database.
- `instance/uploads` is local disk storage: on hosting platforms with
  **ephemeral storage**, uploaded images are **not durable across restarts or
  redeployments**. Use persistent storage or an object store for real users.
- If you run a local HTTP development server and had manually enabled
  `SESSION_COOKIE_SECURE=true`, unset it for local testing. HTTPS production
  should use secure cookies.
- Email notifications remain optional and depend on correct SMTP environment
  variables. The live mail and Render deployments were **not** tested here.

## What to check after starting

Register one student and one staff account; verify duplicate accounts show
validation messages. Log in and report lost/found items, open Search and
Possible Matches, submit a claim, review it with an existing admin account,
and confirm the claimant sees an in-app notification. Confirm uploaded pictures
still render and that the styling looks the same.

**Scope:** This is a course-project build. Image header checks do not replace
full image-content inspection; users should never submit unnecessary private
identifying data. Automated tests do not establish full production readiness.
