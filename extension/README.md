# Riseply Autofill (Chrome extension)

Adds a sidebar to job postings and application forms: score your resume
against the job, tailor an ATS resume, autofill the form, draft a cover
letter, and click Next or Log in for you after you confirm. The sidebar only
appears on pages that look like a job (known application sites, pages with
job-posting data, or careers pages whose text reads like a job). It never
appears on shops, news or search pages, or on Riseply's own site.

Not on the Chrome Web Store yet. See `STORE_LISTING.md` for the submission
pack. Until then it is loaded in Developer Mode.

## Install (Developer Mode)

1. Open `chrome://extensions` and turn **Developer mode** on.
2. **Load unpacked**, then pick this `extension/` folder.
3. Pin it, click the icon and log in with your Riseply account.

After any code change, press the refresh icon on the extension's card.

## What it does

- **Autofill this page**: name, email, phone, links, address, work history,
  education, standard answers (work authorization, sponsorship, salary,
  notice period), optional self-identification answers, and your saved
  answers. Saved answers fill text boxes, dropdowns and radio buttons, but
  only when they point at exactly one option.
- **Works inside iframes** (iCIMS, embedded Greenhouse) and on Workday-style
  pick-from-a-list questions.
- **Attaches your resume** to the upload field (the tailored one if you made
  it).
- **Review and undo**: after Autofill, a list shows what went into each
  question, with an Undo button. Pick-from-a-list choices can't be reset from
  the page and are counted for you to change by hand.
- **Still for you**: lists the questions it couldn't answer and sends their
  text (never your answers) to Riseply, so you can answer once in your
  Autofill profile.

## Rules it keeps

- Fills only empty fields and never overwrites what you typed.
- Never guesses between options.
- Never submits for you. Next, Log in and Submit are clicked only after you
  confirm.
- Site logins you save stay in this browser and are never sent to Riseply.

## Tests

`node extension/tests/profilefill.test.js` (needs Playwright and Chromium).
