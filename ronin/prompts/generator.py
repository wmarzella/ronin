"""Dynamic prompt generation from user profile.

Replaces hardcoded personal data in prompts with values pulled from a
Profile object, making the system portable across users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ronin.profile import Profile


def _format_skills_section(profile: Profile) -> str:
    """Format the skills dictionary into a readable section.

    Args:
        profile: The user profile containing skills by category.

    Returns:
        A multi-line string with one line per skill category.
    """
    lines: list[str] = []
    for category, skills in profile.professional.skills.items():
        lines.append(f"- {category}: {', '.join(skills)}")
    return "\n".join(lines)


def _format_resume_profiles_section(profile: Profile) -> str:
    """Format resume profiles with their matching rules.

    Args:
        profile: The user profile containing resume definitions.

    Returns:
        A numbered list of resume profiles with job-type matching rules.
    """
    lines: list[str] = []
    for i, rp in enumerate(profile.resumes, 1):
        job_types = ", ".join(rp.use_when.job_types) if rp.use_when.job_types else "any"
        desc = rp.use_when.description or "No additional guidance"
        lines.append(f'{i}. "{rp.name}" — Use for: {job_types}. {desc}')
    return "\n".join(lines)


def generate_job_analysis_prompt(profile: Profile) -> str:
    """Build a job analysis prompt from the user's profile.

    The prompt instructs the AI to score jobs 0-100, classify them, identify
    the tech stack, select the best resume profile, and give a recommendation.

    Args:
        profile: The user profile with skills, preferences, and resume
            definitions.

    Returns:
        A complete system prompt string for job analysis.
    """
    prefs = profile.professional.preferences
    high_value = (
        ", ".join(prefs.high_value_signals)
        if prefs.high_value_signals
        else "None specified"
    )
    red_flags = ", ".join(prefs.red_flags) if prefs.red_flags else "None specified"
    work_types = (
        ", ".join(prefs.preferred_work_types) if prefs.preferred_work_types else "Any"
    )
    arrangements = (
        ", ".join(prefs.preferred_arrangements)
        if prefs.preferred_arrangements
        else "Any"
    )
    skills_section = _format_skills_section(profile)
    resume_section = _format_resume_profiles_section(profile)
    resume_names = ", ".join(f'"{rp.name}"' for rp in profile.resumes)

    return f"""\
You are a veteran technical recruiter and career strategist. Your mission is to \
analyse job descriptions against the candidate's profile, score them, and select \
the most appropriate resume version.

CANDIDATE SKILLS:
{skills_section}

HIGH-VALUE SIGNALS (boost score when present):
{high_value}

RED FLAGS (reduce score when present):
{red_flags}

PREFERRED WORK TYPES: {work_types}
PREFERRED ARRANGEMENTS: {arrangements}

RESUME PROFILES (pick the best match):
{resume_section}

JOB CLASSIFICATION CRITERIA:
- CASH_FLOW: Contract roles, short-term engagements, consulting/agency positions, \
roles emphasising immediate delivery, high day rates, or positions where impressive \
credentials matter more than cultural fit.
- LONG_TERM: Permanent positions, roles emphasising growth/learning, team-focused \
environments, startups building culture, or positions where authenticity and \
potential matter more than inflated achievements.

Your response MUST be a valid JSON object with these fields:

{{
    "score": <integer 0-100>,
    "tech_stack": <primary cloud/platform, e.g. "AWS", "Azure", "GCP">,
    "job_classification": "CASH_FLOW" or "LONG_TERM",
    "resume_profile": <one of {resume_names}>,
    "recommendation": "One-line assessment in 50 words or less, including any red flags."
}}

RESUME SELECTION RULES:
- Match the job to a resume profile based on the use_when rules above.
- If no profile is a clear match, pick the most general one.

IMPORTANT: Focus on signs of platform influence and decision-making authority, not \
just raw technical requirements. Be especially wary of positions combining legacy \
tools with modern platforms — this often signals a struggling migration rather than \
genuine transformation."""


def generate_form_field_prompt(profile: Profile, keywords: list[str]) -> str:
    """Build a screening-question prompt from the user's profile.

    The prompt tells the AI how to answer application form fields (checkbox,
    radio, select, textarea) using the candidate's real work rights, skills,
    and salary expectations.

    Args:
        profile: The user profile with work rights, skills, and salary info.
        keywords: The job search keywords for context.

    Returns:
        A complete system prompt string for form-field answering.
    """
    wr = profile.work_rights
    skills_section = _format_skills_section(profile)

    # Work rights details
    citizenship = wr.citizenship or "Not specified"
    visa = wr.visa_status or "Not specified"
    drivers = "Yes" if wr.has_drivers_license else "No"
    police = "Yes" if wr.police_check else "No"

    clearances_held = (
        ", ".join(wr.security_clearances) if wr.security_clearances else "None"
    )
    willing_clearance = "Yes" if wr.willing_to_obtain_clearance else "No"
    willing_relocate = "Yes" if wr.willing_to_relocate else "No"
    willing_travel = "Yes" if wr.willing_to_travel else "No"
    notice = wr.notice_period or "Not specified"

    salary_min = profile.professional.salary_min
    salary_max = profile.professional.salary_max
    currency = profile.professional.salary_currency or "AUD"

    return f"""\
You are a professional job applicant assistant helping me apply to jobs with \
keywords: {keywords}.

ABOUT ME:
- Citizenship: {citizenship}
- Visa / work rights: {visa}
- Driver's licence: {drivers}
- Willing to undergo police check: {police}
- Security clearances held: {clearances_held}
- Willing to obtain clearance if required: {willing_clearance}
- Willing to relocate: {willing_relocate}
- Willing to travel: {willing_travel}
- Notice period: {notice}
- Salary expectations: {currency} ${salary_min:,} – ${salary_max:,}

MY SKILLS (select these when relevant):
{skills_section}

INSTRUCTIONS:
Based on my resume, provide concise, relevant, professional answers to job \
application questions.

RESPONSE FORMAT (valid JSON only):
- For textareas: {{"response": "your answer"}}
- For radios: {{"selected_option": "exact id from options"}}
- For checkboxes: {{"selected_options": ["id1", "id2"]}}
- For selects: {{"selected_option": "exact value from options"}}

CRITICAL RULES:
- ONLY use IDs/values exactly as provided in options
- NEVER make up IDs or values
- For textareas, keep under 100 words

CHECKBOX RULES (select all that apply):
- Be AGGRESSIVE about selecting options that match my skills
- If I have equivalent experience, SELECT IT — transferable skills count
- For "select all that apply" questions, select EVERY option I could reasonably claim

SECURITY CLEARANCE:
- If asked about current status and I hold none, answer "No"
- If forced to select, choose lowest/baseline option or "None"
- For required fields with validation errors, select something appropriate"""


def generate_cover_letter_prompt(
    profile: Profile,
    engagement_type: str,
    engagement_context: str,
    example: str,
    resume_text: str,
) -> str:
    """Build a cover letter prompt from the user's profile.

    The prompt combines the candidate's personal info, writing preferences,
    anti-slop rules, engagement framing, an example letter, and resume text
    into a single system prompt.

    Args:
        profile: The user profile with personal info and cover letter prefs.
        engagement_type: Short label, e.g. "CONTRACT/TEMP" or "FULL-TIME".
        engagement_context: The framing paragraph (contract_framing or
            fulltime_framing from the profile).
        example: An example cover letter to guide tone and structure.
        resume_text: The candidate's resume text to reference.

    Returns:
        A complete system prompt string for cover letter generation.
    """
    cl = profile.cover_letter
    name = profile.personal.name
    spelling = cl.spelling or "Australian English"
    max_words = cl.max_words or 150
    tone = cl.tone or "Like an email to a colleague you haven't met yet"

    anti_slop_lines = ""
    if cl.anti_slop_rules:
        anti_slop_lines = "\n".join(f"- {rule}" for rule in cl.anti_slop_rules)

    return f"""\
You write cover letters for {name}.

GOAL: Write something that sounds like a real person wrote it. Not a template. \
Not AI slop.

ENGAGEMENT TYPE: {engagement_type}

{engagement_context}

TONE:
- {tone}
- Confident but not inflated — say what you did, not what it "stands as a \
testament to"
- Vary sentence length. Short ones. Then a longer one when it makes sense.
- Have a voice. It's fine to be slightly casual.
- Use {spelling} spelling

STRUCTURE:
1. What they need (one line, not "I'm excited to apply")
2. Why you fit — specific, brief
3. Simple close

ANTI-SLOP RULES — Never use:
{anti_slop_lines}

EXAMPLE:
{example}

ADDRESS:
- NEVER use placeholders like [Recruiter's Name] or [Company Name] — if you \
don't know a name, use the company/agency name or just "Hi," or "Hi Team,"
- Strip taglines (e.g. "Talent — Specialists in tech" → "Talent")
- If company name is provided, use "Hi [Company] Team," (e.g. "Hi Acme Team,")

Keep it under {max_words} words. Recruiters skim.

{name}'s resume: {resume_text}

Output valid JSON:
{{"response": "cover letter text"}}"""
