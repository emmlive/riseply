// Plain facts about Riseply, kept in one place so the FAQ, the how-it-works
// page and the llms.txt summary never disagree. Only state what is true today.
export const UPDATED = "2026-10-24";
export const UPDATED_LABEL = "October 2026";

export const FAQS: { q: string; a: string }[] = [
  {
    q: "What is Riseply?",
    a: "Riseply is an AI job-search platform. It finds jobs that fit your resume, tailors your resume for each one without inventing experience, prepares you for interviews, helps fill in application forms, and then helps you grow into your next role with a Career Coach, skill-gap reports and career-path plans. You approve every step; nothing is sent to an employer without your OK.",
  },
  {
    q: "Is Riseply free?",
    a: "Yes, you can start on a free plan, which has monthly limits on matches, tailored resumes, coaching messages and other AI actions. Riseply Pro raises those limits. Riseply Enterprise is a separate offering for companies.",
  },
  {
    q: "Does Riseply apply to jobs for me automatically?",
    a: "No. Riseply does not mass-apply on your behalf. It finds and scores jobs, prepares a tailored resume and cover letter, and can fill in the form, but you review everything and confirm before anything is submitted. That is deliberate: automated bulk applications tend to hurt response rates and can put wrong answers in front of employers.",
  },
  {
    q: "Will Riseply make up experience or exaggerate my resume?",
    a: "No. Tailoring only rearranges, emphasizes and rewords what is already in your resume for the job at hand, including for a career change. It does not add employers, titles, degrees, certifications or skills you have not told it about. The Career Coach follows the same rule.",
  },
  {
    q: "Where do the jobs come from?",
    a: "Riseply pulls openings from public sources: company career boards on Greenhouse and Lever, job feeds such as RemoteOK, Arbeitnow and Adzuna, and USAJobs for US federal roles. It checks new postings against your search profiles every day and scores each match against your resume, with a short reason. It also shows the closest near-misses when nothing clears your threshold.",
  },
  {
    q: "How does the match score work?",
    a: "Each job posting is compared with your resume and your search profile, and Riseply gives a score from 0 to 100 with a one-sentence reason. Jobs above your threshold are queued for your review. Jobs that are clearly in a different field are skipped before any AI scoring, so they do not use up your monthly limit.",
  },
  {
    q: "What is the Riseply browser extension?",
    a: "Riseply Autofill is a Chrome extension that adds a sidebar to job postings. It can score your resume against the posting, generate a tailored ATS-friendly resume and attach it to the form, fill in your contact details, work history, education and standard answers, and mark the job as applied in Riseply. It only fills answers you have chosen yourself, never overwrites a field you already filled, and asks you to confirm before it clicks Next, Log in or Submit. The extension is being prepared for the Chrome Web Store and is not listed there yet.",
  },
  {
    q: "Does autofill work on Workday, Greenhouse and Lever forms?",
    a: "It is built for the common patterns on those and many other application systems, including multi-page Workday forms with dropdowns, checkboxes and date fields. Application forms differ a lot, so it lists anything it left for you to complete instead of guessing.",
  },
  {
    q: "How is Riseply different from using ChatGPT or Claude directly?",
    a: "A general chatbot can rewrite a resume when you paste it in, but you still have to find the jobs, keep track of what you applied to, and remember which resume went where. Riseply connects those steps: daily matching, a tailored resume per job saved with the application, form filling, follow-up reminders, interview prep and coaching, all working from the same resume and profile. It also holds the line on honesty, with no invented experience.",
  },
  {
    q: "What does the Career Coach do?",
    a: "The Career Coach runs practice sessions for any role you are aiming at: knowledge drills, mock interviews, resume coaching, offer negotiation and upskilling. It can also teach a skill as a short course, with modules, timers and a recap after each one, and it saves notes into study folders you can quiz yourself from later. Sessions end with an honest score and feedback.",
  },
  {
    q: "Can Riseply help me study for a certification exam?",
    a: "Yes. Exam prep builds a study plan from the domains of the exam you name, such as CISA, and practice questions to work through. It writes from general knowledge of the exam, so check it against the official exam outline.",
  },
  {
    q: "Is there a version for companies?",
    a: "Yes. Riseply Enterprise applies the same ideas to a team: an AI onboarding buddy grounded in your own handbook (Buddy as a Service), mentor matching (Mentor as a Service), and internal job mobility. Conversation content stays private to the employee, and admins see only aggregate usage.",
  },
  {
    q: "What happens to my resume and data?",
    a: "Your resume and profile are used to run the features you ask for. Job-site logins you choose to save in the extension stay in your own browser and are never sent to Riseply. See the Privacy Policy and the Security & Trust page for the details.",
  },
];

export const STAGES: { name: string; summary: string; what: string[] }[] = [
  {
    name: "Get ready",
    summary: "Give Riseply the facts once, so every later step starts from them.",
    what: [
      "Upload your resume. It is the only source Riseply tailors from.",
      "Fill in your Autofill profile once: contact details, work history, education, skills and your standard application answers.",
      "Set one or more search profiles: the roles, places and keywords you want.",
    ],
  },
  {
    name: "Find",
    summary: "New jobs are matched to your resume every day.",
    what: [
      "Riseply checks public job sources daily and scores each new posting against your resume, from 0 to 100, with a one-sentence reason.",
      "Jobs above your threshold wait in your Applications list for review. When nothing clears the bar, you see the closest near-misses instead of an empty page.",
      "Rejecting a match with a reason teaches the matcher what to skip next time.",
    ],
  },
  {
    name: "Apply",
    summary: "Prepare each application quickly, then decide.",
    what: [
      "Generate a tailored, ATS-friendly resume for the job. It reuses only what is already in your resume.",
      "Draft a cover letter, get help with custom questions, and get interview prep for the company and role.",
      "In Chrome, the Riseply Autofill extension can fill the application form and attach the tailored resume. You confirm before it moves on or submits, and the job is marked applied in Riseply.",
      "Riseply tracks each application and suggests a follow-up when you have heard nothing for a week.",
    ],
  },
  {
    name: "Win",
    summary: "Practice until the interview feels familiar.",
    what: [
      "Career Coach sessions for knowledge drills, mock interviews, resume coaching and offer negotiation, each ending with an honest score.",
      "A readiness view that shows where you are strong and what still needs work.",
    ],
  },
  {
    name: "Grow",
    summary: "Keep moving after the offer, or while you wait for it.",
    what: [
      "Skill-gap reports compare your resume with the role you want and show what is missing.",
      "A career path plan lays out the steps from where you are to your target role.",
      "Courses taught by the Career Coach, exam prep, a task guide for finishing real work assignments, and an onboarding buddy for your first weeks in a new job.",
    ],
  },
];
