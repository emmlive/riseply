// Plain-language guides, each written to answer one question a job seeker
// actually asks. Advice is general and standard; the "How Riseply helps"
// section only states what the product does today.
export interface Guide {
  slug: string;
  title: string;          // the question, as a person would type it
  description: string;    // meta description
  answer: string;         // the direct answer, shown first
  sections: { h: string; p?: string[]; ul?: string[] }[];
  riseply: string;        // how Riseply helps, one honest paragraph
  related: string[];      // other guide slugs
}

export const GUIDES_PUBLISHED = "2026-10-24";

export const GUIDES: Guide[] = [
  {
    slug: "tailor-resume-without-exaggerating",
    title: "How do you tailor your resume to a job without exaggerating?",
    description: "A practical way to tailor your resume for each job using only what is true: pick the right facts, mirror the posting's wording honestly, and leave out what does not fit.",
    answer: "Tailoring means choosing and ordering true facts so the most relevant ones come first, and using the posting's own words for things you really did. It never means adding skills, titles or results you do not have.",
    sections: [
      { h: "Start with the posting, not your resume", p: ["Read the job description and underline the five or six things it asks for most: tools, responsibilities, outcomes. Those are what a reader will look for in the first few seconds."] },
      { h: "Match each requirement to something you actually did", ul: [
        "For every requirement, find the closest real example in your history, even if it was in a different job or a side project.",
        "If you did it under a different name, use the posting's term for it, so long as it describes the same thing.",
        "If you have nothing true for a requirement, leave it out. A gap you do not hide is better than a claim you cannot back up in an interview.",
      ] },
      { h: "Reorder and trim", ul: [
        "Move the most relevant roles, bullets and skills to the top.",
        "Cut bullets that do not help for this job, so the strong ones are not buried.",
        "Keep numbers only when they are real. Round honestly, and be ready to explain where each came from.",
      ] },
      { h: "Check the result", p: ["Ask of every line: could I describe this in detail to the interviewer? If not, soften it or remove it. A tailored resume that gets you an interview you cannot handle has not helped."] },
      { h: "Changing careers", p: ["Lead with a short summary that names the new direction, then show transferable work: projects, responsibilities, tools and results that carry over. Say plainly what you are moving toward instead of implying experience you have not had."] },
    ],
    riseply: "Riseply writes a tailored, ATS-friendly resume for each job from the resume you uploaded. It rearranges and rewords what is already there and does not add employers, titles, degrees, certifications or skills you have not told it about. You review the result before you use it.",
    related: ["make-an-ats-friendly-resume", "autofill-job-applications-safely"],
  },
  {
    slug: "make-an-ats-friendly-resume",
    title: "How do you make an ATS-friendly resume?",
    description: "What an applicant tracking system can and cannot read, and a simple checklist for a resume that parses cleanly: one column, standard headings, real text.",
    answer: "Use a plain, one-column layout with standard section headings, real text instead of images, and common fonts. An applicant tracking system (ATS) mainly needs to read your resume correctly, and most of the damage comes from layouts that confuse the parser.",
    sections: [
      { h: "What an ATS does", p: ["An ATS stores applications and lets recruiters search and filter them. Many do not automatically reject people on a score; recruiters often search by keywords and job titles, so your resume has to be read correctly and contain the words a recruiter would search for."] },
      { h: "A checklist that works", ul: [
        "One column. Avoid tables, text boxes and side columns for important content.",
        "Standard headings: Summary, Experience, Education, Skills.",
        "Put contact details in the body of the page, not in the header or footer, which some parsers skip.",
        "Use a common font and normal bullet characters.",
        "Send a Word file or a PDF made from text, not a scan or an image of text.",
        "Use job titles, dates and employers in plain lines, in a consistent order.",
        "Spell out terms and add the acronym once, for example Certified Information Systems Auditor (CISA), so both versions can be found.",
      ] },
      { h: "Keywords", p: ["Use the words the posting uses for skills and tools you really have. Do not paste a list of keywords you cannot discuss; a person will read the resume after the software does."] },
      { h: "Test it", p: ["Copy all the text from your resume and paste it into a plain text editor. If the order is jumbled or parts are missing, a parser will likely see the same thing."] },
    ],
    riseply: "Riseply generates resumes in a plain one-column layout so they read cleanly in applicant tracking systems, and it can attach the tailored file to the application form for you. The content comes only from your own resume.",
    related: ["tailor-resume-without-exaggerating", "autofill-job-applications-safely"],
  },
  {
    slug: "autofill-job-applications-safely",
    title: "How do you autofill job applications safely?",
    description: "How to save time on application forms without sending wrong answers: what to prepare, what to check on every page, and what never to automate.",
    answer: "Prepare your standard answers once, let a tool fill the routine fields, and review every page yourself before you continue. Never let any tool submit an application you have not looked at.",
    sections: [
      { h: "Prepare once", ul: [
        "Keep one clean record of your contact details, address, work history, education and links.",
        "Decide your standard answers ahead of time: work authorization, sponsorship, notice period, relocation, salary expectations and how you heard about the company.",
        "Keep your resume file and a plain-text version ready for upload.",
      ] },
      { h: "Check each page before moving on", ul: [
        "Look for fields that were filled with the wrong thing, such as a phone number in the wrong format or the wrong state.",
        "Read every yes/no question yourself, especially anything about legal status, past employment with the company or conflicts of interest.",
        "Confirm dates and job titles match your resume exactly. Application systems often compare them.",
        "Voluntary self-identification questions are optional. Answer only if you choose to.",
      ] },
      { h: "Stay safe", ul: [
        "Do not save job-site passwords on a shared or public computer.",
        "Be wary of any tool that submits for you. Bulk applications can carry wrong answers in your name.",
        "Keep a record of where you applied and which resume you sent, so you can follow up and prepare.",
      ] },
      { h: "Multi-page systems", p: ["Systems like Workday often make you create an account and walk through several pages. Expect to complete a few custom questions by hand, and save your progress before you close the tab."] },
    ],
    riseply: "The Riseply Autofill Chrome extension fills routine fields from an Autofill profile you set up, handles dropdowns, checkboxes and dates on common systems including multi-page Workday forms, and lists anything it left for you. It only fills answers you chose, never overwrites a field you already filled, and asks you to confirm before it clicks Next, Log in or Submit. It is being prepared for the Chrome Web Store and is not listed there yet.",
    related: ["make-an-ats-friendly-resume", "follow-up-on-a-job-application"],
  },
  {
    slug: "follow-up-on-a-job-application",
    title: "How and when should you follow up on a job application?",
    description: "When to follow up after applying or interviewing, what to say, and a short template that is polite and specific.",
    answer: "Follow up about a week after you apply, or a few days after the date the employer gave you. Keep it to a few sentences: say who you are, name the role, restate one reason you fit, and ask about the timeline.",
    sections: [
      { h: "Timing", ul: [
        "After applying with no news: wait about a week, then send one short message.",
        "After an interview: send thanks within a day, then follow up once if the promised date passes.",
        "If you still hear nothing after a second message, move on, and keep the door open.",
      ] },
      { h: "Who to write to", p: ["Prefer the recruiter or hiring manager named in the posting or on the application page. If there is no name, use the recruiting contact address and include the job title and any requisition number."] },
      { h: "A short template", p: ["Subject: Following up on the [Role] application", "Hello [Name], I applied for the [Role] position on [date] and wanted to confirm it reached you. My background in [one relevant thing] matches what the role needs, and I would welcome a conversation. Could you tell me where the process stands? Thank you, [Your name]."] },
      { h: "Tips", ul: [
        "Be specific and brief. One clear question gets answered more often than a paragraph.",
        "Never sound annoyed. A friendly tone keeps you in consideration.",
        "Keep track of every application and the date you followed up, so nothing slips.",
      ] },
    ],
    riseply: "Riseply tracks each application, and when you have heard nothing for a week or more it suggests a follow-up and drafts the message for you to edit and send.",
    related: ["prepare-for-a-job-interview", "autofill-job-applications-safely"],
  },
  {
    slug: "prepare-for-a-job-interview",
    title: "How do you prepare for a job interview?",
    description: "A practical interview preparation plan: research the company, prepare stories in the STAR format, practice out loud, and plan your questions.",
    answer: "Research the company and role, prepare five or six real stories you can adapt to common questions, practice answering out loud, and bring good questions of your own.",
    sections: [
      { h: "1. Research", ul: [
        "Read the job posting line by line and note what the team seems to care about most.",
        "Learn what the company does, who its customers are, and any recent news.",
        "Look up your interviewers if you know their names.",
      ] },
      { h: "2. Build your stories", p: ["Choose five or six real examples: a result you are proud of, a mistake you learned from, a conflict, a time you led, a time you learned something fast. Outline each as Situation, Task, Action, Result (STAR), with one number or concrete outcome."] },
      { h: "3. Practice out loud", p: ["Say your answers aloud, ideally to another person or a recording. Aim for answers of about two minutes. Practice the opening question, \"tell me about yourself\", until it is a short, clear story of where you have been and why this role is next."] },
      { h: "4. Plan your questions", ul: [
        "What does success look like in the first six months?",
        "What are the biggest challenges the team faces right now?",
        "How does the team make decisions and give feedback?",
      ] },
      { h: "5. The day itself", p: ["Test your technology for a video call, arrive early, and have your resume and a notebook ready. Send a short thank-you note afterward that mentions one specific part of the conversation."] },
    ],
    riseply: "Riseply's Career Coach runs mock interviews and knowledge drills for the role you are aiming at and ends each session with an honest score. Interview prep for a specific application draws on the job posting and a brief about the company.",
    related: ["follow-up-on-a-job-application", "study-for-a-certification-exam"],
  },
  {
    slug: "study-for-a-certification-exam",
    title: "How do you build a study plan for a certification exam?",
    description: "A step-by-step way to plan study for a professional certification exam such as CISA: use the official outline, test yourself early, and practice in short repeated sessions.",
    answer: "Start from the official exam outline, take a short diagnostic to find your weak domains, then study in short, repeated sessions weighted by how much each domain counts. Finish with timed practice exams.",
    sections: [
      { h: "Use the official source first", p: ["The organization that runs the exam publishes an outline or candidate guide listing the domains and how much each is worth. Build your plan from that document, and check it again before test day because outlines are revised."] },
      { h: "Find your starting point", p: ["Take a short diagnostic quiz before you study. It shows which domains need the most time, so you do not spend weeks on what you already know."] },
      { h: "Plan the weeks", ul: [
        "Work backward from the exam date.",
        "Give more time to heavily weighted domains and to your weakest ones.",
        "Use short daily sessions instead of long weekend marathons.",
        "Revisit older topics on a schedule. Spaced repetition beats rereading.",
      ] },
      { h: "Practice the way the exam asks", ul: [
        "Answer many questions, and read the explanation for the ones you missed and the ones you guessed.",
        "Learn the style of the exam. Many professional exams ask for the best answer among several reasonable ones.",
        "In the last two weeks, take timed full-length practice exams.",
      ] },
    ],
    riseply: "Riseply's exam prep builds a study plan and practice questions from the domains of the exam you name. It writes from general knowledge of the exam, so check it against the official outline. The Career Coach can also teach a topic as a short course with a recap after each module, and you can save notes into study folders to quiz yourself later.",
    related: ["prepare-for-a-job-interview", "tailor-resume-without-exaggerating"],
  },
];

export function getGuide(slug: string): Guide | undefined {
  return GUIDES.find((g) => g.slug === slug);
}
