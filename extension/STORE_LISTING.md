# Chrome Web Store submission pack: Riseply Autofill

Everything to paste into the Chrome Web Store developer dashboard.
Written against `extension/manifest.json` as it stands (permissions: `storage`; host: `riseply.onrender.com`; content script on all sites).

## Before you submit (you do these)

1. Register at https://chrome.google.com/webstore/devconsole (one-time $5 fee; Google asks you to verify your email and may ask for identity verification).
2. Merge the privacy policy update (it now has a "Riseply Autofill browser extension" section) so `https://riseply.com/privacy` is live **before** you submit. The privacy URL is required and reviewers open it.
3. Zip the contents of the `extension/` folder (the files, not the folder itself). In PowerShell, from `C:\Users\emmli\riseply\extension`:
   `tar -a -c -f "$env:USERPROFILE\Downloads\riseply-autofill.zip" manifest.json background.js content.js jobinfo.js profilefill.js popup.html popup.js icons` (use `tar`, not `Compress-Archive`: older PowerShell writes backslashes into the zip, which the store can reject; leave out `README.md`, `STORE_LISTING.md` and the `tests` folder)
4. Take 3 to 5 screenshots, 1280x800, on a real job posting: (a) the sidebar showing a match score, (b) autofill filling a real form, (c) a suggested answer or cover letter, (d) the popup after login. Use a posting you are comfortable showing; blur any personal details.
5. Make a test account for the reviewers (see "Reviewer instructions") with a resume saved and the Autofill profile filled in (use "Fill from my resume"), and put its login in the dashboard's "Test instructions" box. Do not paste it anywhere else.

## Store listing

**Name:** Riseply Autofill

**Summary (max 132 characters):**
See how your resume matches a job posting and autofill application forms, powered by your Riseply account.

**Category:** Productivity

**Detailed description:**

Riseply Autofill adds a small sidebar to job postings so you can decide faster and apply with less typing.

When you open a job posting, the sidebar shows:
- Score my resume: how well your resume matches this job, with a one-sentence reason.
- Autofill this page: fills your name, email, phone, location and profile links, plus your work history, education and common answers from your Riseply Autofill profile. It only fills answers you chose yourself, never overwrites a field you already filled, and leaves anything you left blank for you. Filling never submits the form; you review it, and a separate Submit button in the sidebar asks you to confirm before it clicks the site's own submit button.
- Generate cover letter: a first draft from your resume and the posting, ready to edit.
- Suggested answers: help with custom application questions, based on your resume.

Nothing is sent from a page until you click one of those buttons. You need a free Riseply account (riseply.com). Free accounts have a monthly limit on scores and drafts; Pro raises it.

When a form has a resume upload field, Autofill attaches your resume: the original PDF or Word file you keep with your Riseply resume, or a plain PDF made from your resume text. It never submits anything without your explicit confirmation; that is deliberate.

Privacy: https://riseply.com/privacy

**Support URL:** https://riseply.com/ (or your support page)
**Homepage URL:** https://riseply.com/

## Single purpose (dashboard field)

Help a job seeker evaluate a job posting against their Riseply resume and fill in the application form for it.

## Permission justifications (dashboard fields)

**storage**
Stores the user's Riseply sign-in token in the browser so they stay logged in. Removed on logout.

**Host permission: https://riseply.onrender.com/\***
The extension's only server. All requests (sign-in, resume scoring, cover letters, answers, profile fetch) go to the Riseply API at this address, made from the extension's background service worker.

**Content script on all sites (`<all_urls>`)**
Job postings and application forms live on thousands of different company career sites and applicant-tracking systems, so the sidebar has to be able to appear on any of them. On each page the script only checks locally whether the page looks like a job posting; if not, it does nothing. It reads page text and fills form fields only after the user clicks a button in the sidebar, and sends data to Riseply only for the actions the user clicked (score, cover letter, suggested answer). It does not collect browsing history.

**Remote code:** No. All code is in the package; nothing is loaded or evaluated from a server.

## Privacy practices (dashboard "Data usage" tab)

Collected data types to tick:
- **Personally identifiable information**: the user's name, email, phone, location, work history, education, their resume file, and the answers they saved in their Riseply Autofill profile (including optional self-identification answers they chose) are fetched from their own account to fill forms and attach their resume.
- **Authentication information**: the sign-in token (stored locally) and the email/password typed into the extension popup, sent to Riseply to log in.
- **Website content**: text of the job posting the user is viewing, sent only when they click Score my resume, Generate cover letter or a suggested answer.

Do not tick: financial, location (geolocation), web history, user activity, personal communications. If Google's form asks about health or race/ethnicity data, tick it only for the optional self-identification answers the user chooses to save and has the extension fill; say so in the justification.

Certify all three: not sold to third parties; not used or transferred for purposes unrelated to the single purpose; not used for creditworthiness or lending.

## Reviewer instructions ("Test instructions" box)

> The extension needs a Riseply account. Test login: [create a test account at riseply.com, add a resume under Resume, and put its email and password here]. Open the popup, log in, then visit any job posting, for example any listing on boards.greenhouse.io. A sidebar appears at the top right. Click "Score my resume" to see a score, or "Autofill this page" on an application form to see fields fill and the resume attach (if the form has an upload field). Nothing is submitted automatically.

## Things the reviewers are likely to look at

- **Unused permissions were removed.** The manifest used to request `activeTab` and `scripting` without using them, and `https://riseply.com/*` as a host. Chrome rejects unused permissions, so they are gone. Only `storage` and the API host remain.
- **`<all_urls>` is the biggest review risk.** It is justified above and is honest, but it triggers the "read and change all your data on all websites" warning at install and can slow review. If Google pushes back, the fix is to list the known job-site hosts in `matches` (greenhouse.io, lever.co, ashbyhq.com, myworkdayjobs.com, smartrecruiters.com and so on) and offer the sidebar on other sites through the toolbar button. Tell me if that happens and I'll make the change.
- **Privacy policy must match.** The new section on `riseply.com/privacy` says exactly what the data section above says. If you change one, change the other.
- Review usually takes a few days, sometimes longer for broad host access.

## After approval

- Update `extension/README.md` to say it is published, and add the store link to the Riseply site.
- Every code change needs a new version number in `manifest.json` and a new zip upload.
