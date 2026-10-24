# APInex Free-Tier Models Scoring Benchmark Report
**Generated at:** 2026-10-24 17:04:22
**Total models tested:** 11

## 1. Summary Comparison

| Model | Status | Latency (s) | Prompt Tokens | Output Tokens | Total Tokens | Score | Verdict | JSON Valid |
|---|---|---:|---:|---:|---:|---:|---|:---:|
| `free/muse-spark-1.3` | **OK** | 3.19s | 2976 | 432 | 3408 | 72 | `maybe` | Yes |
| `free/deepseek-v4.1-flash` | **OK** | 2.92s | 2984 | 409 | 3393 | 78 | `maybe` | Yes |
| `free/glm-5.3-flash` | **OK** | 2.71s | 2988 | 421 | 3409 | 78 | `maybe` | Yes |
| `free/minimax-m3.1-flash` | **OK** | 3.19s | 2982 | 555 | 3537 | 72 | `apply` | Yes |
| `free/glm-5.3` | **OK** | 2.87s | 2987 | 456 | 3443 | 72 | `maybe` | Yes |
| `free/gemini-3.8-flash` | **OK** | 3.3s | 2979 | 510 | 3489 | 78 | `maybe` | Yes |
| `free/deepseek-v4-pro-0813` | **OK** | 3.78s | 2987 | 501 | 3488 | 80 | `apply` | Yes |
| `free/gpt-6-luna` | **OK** | 3.1s | 2983 | 523 | 3506 | 72 | `maybe` | Yes |
| `free/glm-5.3-flashx` | **OK** | 4.43s | 2989 | 476 | 3465 | 82 | `apply` | Yes |
| `free/mimo-v2.6-pro` | **OK** | 2.91s | 2976 | 467 | 3443 | 78 | `maybe` | Yes |
| `free/jev-1.13` | **FAIL** | 0.19s | 0 | 0 | 0 | - | `-` | No |

---

## 2. Detailed Responses & Error Logs

### Model: `free/muse-spark-1.3`
- **Status**: SUCCESS
- **Execution Time**: 3.19s
- **Tokens**: Prompt: 2976 | Completion: 432 | Total: 3408

**Model Response Output:**
```json
{"overall_score": 72, "verdict": "maybe", "disqualifying_flags": ["No EU/Gulf work authorization; requires visa sponsorship from Tunisia"], "dimensions": {"role_match": {"score": 90, "reason": "Directly matched to Flutter developer role; 3 years of professional Flutter/Dart experience across multiple production apps and a freelance full-stack role with mobile focus."}, "skills_match": {"score": 85, "reason": "Strong match: BLoC/Provider state management, REST APIs, WebSockets, Flutter/Dart, native iOS (Swift) and Android (Java/Kotlin), architecture patterns, Docker/CI/CD, and automated testing all present."}, "seniority_fit": {"score": 80, "reason": "3 years of experience meets the 2-year minimum; not overqualified but has broader full-stack/data exposure that may be beyond the core mobile role."}, "location_eligibility": {"score": 15, "reason": "Tunisian national needing visa sponsorship; job is based in Berlin, Germany with hybrid work model; sponsorship likelihood depends on company willingness and local labor market conditions."}, "language_requirements": {"score": 90, "reason": "English full professional proficiency meets the job's requirement; German is listed as a plus, not required."}}, "key_strengths": ["3 years professional Flutter/Dart experience with multiple shipped apps", "Experience with BLoC and Provider state management", "Native development exposure (Swift, Kotlin/Java) and WebSocket integration", "Strong engineering education (Master's in Software Engineering) and CI/CD skills"], "critical_gaps": ["Requires visa sponsorship for Germany (no EU work authorization)", "German language not required but absent", "May be overqualified with heavy recent data engineering focus"], "summary": "Strong technical match for the Flutter developer role with 3 years of relevant experience and required skills. The primary barrier is the need for German visa sponsorship from Tunisia, making this a maybe pending the company's willingness to sponsor."}
```

---

### Model: `free/deepseek-v4.1-flash`
- **Status**: SUCCESS
- **Execution Time**: 2.92s
- **Tokens**: Prompt: 2984 | Completion: 409 | Total: 3393

**Model Response Output:**
```json
{"overall_score": 78, "verdict": "maybe", "disqualifying_flags": ["Work authorization: needs employer visa sponsorship; job is in Berlin, Germany, not explicitly open to candidates requiring relocation support."], "dimensions": {"role_match": {"score": 95, "reason": "Candidate is a Flutter developer with 3 years of professional experience, directly matching the role title and core responsibilities of cross-platform iOS/Android app development."}, "skills_match": {"score": 90, "reason": "Strong match on Flutter, Dart, BLoC/Provider state management, REST APIs, WebSockets, clean architecture, and performance optimization. Native development experience is present but not explicitly detailed for Swift/Kotlin."}, "seniority_fit": {"score": 85, "reason": "3 years of professional experience exceeds the required 2 years. Candidate is slightly senior to mid-level but not overqualified."}, "location_eligibility": {"score": 30, "reason": "Candidate is Tunisian, needs visa sponsorship, and is not a citizen/resident of EU or target countries. Job is based in Berlin, Germany, with no explicit statement of relocation support."}, "language_requirements": {"score": 90, "reason": "English is full professional proficiency, meeting the required communication language. German is a plus, not required."}}, "key_strengths": ["3 years of professional Flutter/Dart experience with iOS and Android delivery", "Deep expertise in state management (BLoC, Provider), REST APIs, and WebSockets", "Experience with performance optimization, clean architecture, and CI/CD pipelines", "Strong English communication skills and international client collaboration"], "critical_gaps": ["Requires visa sponsorship for Germany, which may limit hiring eligibility", "Native iOS (Swift) or Android (Kotlin) experience is not explicitly demonstrated", "German language skills not mentioned (only a plus, but could aid integration)"]}
```

---

### Model: `free/glm-5.3-flash`
- **Status**: SUCCESS
- **Execution Time**: 2.71s
- **Tokens**: Prompt: 2988 | Completion: 421 | Total: 3409

**Model Response Output:**
```json
{"overall_score": 78, "verdict": "maybe", "disqualifying_flags": ["Requires Germany work visa sponsorship"], "dimensions": {"role_match": {"score": 95, "reason": "Candidate's target role and primary experience as a Flutter mobile developer align almost perfectly with the job's core task of developing cross-platform iOS and Android apps."}, "skills_match": {"score": 90, "reason": "Strong hands-on Flutter and Dart experience with BLoC, native channel plugins, REST APIs, WebSockets, and modern state management directly matches requirements; minor uncertainty on documented production-grade Clean Architecture usage."}, "seniority_fit": {"score": 90, "reason": "3 years of professional Flutter experience plus a Master's in Software Engineering exceed the 2-year minimum; no indication of over-qualification for a mid-level contributor role."}, "location_eligibility": {"score": 15, "reason": "Tunisian national based in Tunis needing visa sponsorship to work in Germany; no evidence of EU/Gulf work authorization or existing right to work in Germany."}, "language_requirements": {"score": 90, "reason": "Full professional English fluency meets the required language; German is listed as a plus, not a requirement, so the gap is low-risk."}}, "key_strengths": ["3 years of professional Flutter/Dart experience across multiple production mobile applications", "Hands-on native platform channel development (iOS Swift / Android Kotlin) plus hybrid architecture knowledge", "Strong experience with state management (BLoC, Provider), REST APIs, WebSockets, and offline-first architectures", "Master's degree in Software Engineering with solid software architecture background", "English proficiency at full professional level"], "critical_gaps": ["Requires visa sponsorship to work in Germany, which may limit eligibility for candidates seeking immediate local hires", "Limited documented evidence of applying Clean Architecture or MVVM in production at scale", "No German language skills, though this is a plus rather than a requirement"]}
```

---

### Model: `free/minimax-m3.1-flash`
- **Status**: SUCCESS
- **Execution Time**: 3.19s
- **Tokens**: Prompt: 2982 | Completion: 555 | Total: 3537

**Model Response Output:**
```json
{
  "overall_score": 72,
  "verdict": "apply",
  "disqualifying_flags": ["Needs employer visa sponsorship for Germany; candidate is not an EU/Gulf citizen or resident"],
  "dimensions": {
    "role_match": {"score": 95, "reason": "Exact match: candidate has 3 years of professional Flutter/Dart experience across three mobile roles plus freelance work, directly aligning with the Flutter developer role and its iOS/Android cross-platform tasks."},
    "skills_match": {"score": 90, "reason": "Strongly meets core requirements: state management (BLoC, Provider, Riverpod-capable), REST APIs, WebSockets, Clean Architecture/MVVM experience, native channel knowledge, and automated testing/CI/CD. German is not required."},
    "seniority_fit": {"score": 95, "reason": "3 years of professional mobile experience exceeds the 2-year minimum, with progressive responsibility, performance optimization, and architecture contributions — well-suited to the mid-level role without being over-qualified."},
    "location_eligibility": {"score": 25, "reason": "Based in Tunisia with no EU/Gulf work authorization; requires German employer visa sponsorship, which is the single largest uncertainty and likely barrier for this Berlin-based role."},
    "language_requirements": {"score": 95, "reason": "English is full professional proficiency, meeting the role's very good English requirement; German is a plus, not a requirement."}
  },
  "key_strengths": [
    "3 years of dedicated professional Flutter/Dart experience with production apps on both iOS and Android",
    "Demonstrated expertise in BLoC and other state management patterns plus Clean Architecture experience",
    "Real REST API and WebSocket integration experience across multiple apps",
    "Native platform channel experience (iOS/Android) exceeding the 'advantage' criterion",
    "Proven performance optimization, CI/CD, and automated testing background"
  ],
  "critical_gaps": [
    "Visa sponsorship required for Germany — candidate has no EU or German work authorization",
    "German language skills not provided (a plus, but may matter for team integration in Berlin)"
  ],
  "summary": "Strong Flutter developer with exactly the required 3 years of professional experience and all core technical competencies, including state management, APIs, WebSockets, and native channels. The main barrier is visa sponsorship for the Berlin-based role, which the candidate will need to negotiate with the employer."
}
```

---

### Model: `free/glm-5.3`
- **Status**: SUCCESS
- **Execution Time**: 2.87s
- **Tokens**: Prompt: 2987 | Completion: 456 | Total: 3443

**Model Response Output:**
```json
{"overall_score": 72, "verdict": "maybe", "disqualifying_flags": [], "dimensions": {"role_match": {"score": 90, "reason": "Candidate's track is Mobile/Flutter Developer with 3 years of professional Flutter experience across multiple roles, closely matching the job's cross-platform Flutter development responsibilities."}, "skills_match": {"score": 85, "reason": "Strong proficiency in Flutter, Dart, state management (BLoC, Provider), REST APIs, WebSockets, Clean Architecture, and native development experience. Meets all core technical requirements with additional full-stack and DevOps skills."}, "seniority_fit": {"score": 80, "reason": "3 years of professional experience exceeds the 2-year minimum requirement. Mid-level fit appropriate for independent feature implementation."}, "location_eligibility": {"score": 40, "reason": "Candidate is in Tunisia and requires employer visa sponsorship for Germany. Job is based in Berlin with hybrid work model. Sponsorship not explicitly confirmed and visa processing may be challenging without explicit company willingness."}, "language_requirements": {"score": 95, "reason": "English is full professional level, meeting the 'very good communication skills in English' requirement. German is not required, only listed as a plus."}}, "key_strengths": ["3 years professional Flutter/Dart experience across multiple production apps", "Strong state management expertise (BLoC, Provider)", "REST API and WebSocket integration experience", "Native iOS/Swift and Android/Kotlin background", "Clean Architecture and testing experience", "Full-stack backend knowledge (Python, Java, FastAPI, Spring Boot)", "DevOps and CI/CD capabilities"], "critical_gaps": ["Visa sponsorship required for Germany; eligibility uncertain", "German language not required but would be an asset", "Limited explicit evidence of testing automation frameworks beyond Git workflows"], "summary": "A strong Flutter developer with 3 years of professional experience and comprehensive mobile development skills that align well with the job requirements. The main concern is visa sponsorship for Berlin, Germany, as the candidate is based in Tunisia and requires employer support to work legally in the target country."}
```

---

### Model: `free/gemini-3.8-flash`
- **Status**: SUCCESS
- **Execution Time**: 3.3s
- **Tokens**: Prompt: 2979 | Completion: 510 | Total: 3489

**Model Response Output:**
```json
{"overall_score": 78,"verdict": "maybe","disqualifying_flags": ["Visa sponsorship required for Germany; candidate is not an EU citizen or resident","Language: German not required; English proficiency is sufficient"], "dimensions": {"role_match": {"score": 92, "reason": "Candidate's track and experience align precisely with the Flutter Developer role, including cross-platform iOS/Android app development, architecture contributions, and UI/UX implementation."}, "skills_match": {"score": 88, "reason": "Core required skills (Flutter, Dart, state management with BLoC/Provider, REST APIs, WebSockets, Clean Architecture/MVVM, native dev advantage) are well covered; automated testing experience is present though light."}, "seniority_fit": {"score": 85, "reason": "3 years of professional Flutter experience exceeds the 2-year minimum; experience level matches mid-level expectations without over-qualification."}, "location_eligibility": {"score": 35, "reason": "Candidate is a Tunisian national requiring visa sponsorship to work in Germany and does not hold EU citizenship or residence; sponsorship feasibility is uncertain and not confirmed."}, "language_requirements": {"score": 90, "reason": "English proficiency meets the required working language; German is listed as a plus but not required, so this is not a blocker."}}, "key_strengths": ["3 years of professional Flutter/Dart mobile development across multiple production apps", "Strong state management experience (BLoC, Provider) and offline-first architecture", "REST API and WebSocket integration experience from multiple projects", "Native development exposure (iOS/Swift, Android/Kotlin) via platform channels", "Full lifecycle ownership from concept through app store deployment", "Strong backend skills in Python (FastAPI) and Java (Spring Boot)", "DevOps and CI/CD experience with Docker and GitHub Actions"], "critical_gaps": ["Requires visa sponsorship for Germany; no EU work authorization", "German language skills not present (though listed as optional plus)", "Automated testing experience mentioned but not deeply detailed", "Clean Architecture/MVVM explicitly named but not explicitly emphasized in work history"], "summary": "The candidate is a strong technical match for the Flutter Developer role with 3 years of relevant experience and all core required skills. However, the need for German visa sponsorship as a non-EU citizen introduces significant location eligibility risk that prevents a strong recommendation."}
```

---

### Model: `free/deepseek-v4-pro-0813`
- **Status**: SUCCESS
- **Execution Time**: 3.78s
- **Tokens**: Prompt: 2987 | Completion: 501 | Total: 3488

**Model Response Output:**
```json
{
  "overall_score": 80,
  "verdict": "apply",
  "disqualifying_flags": [],
  "dimensions": {
    "role_match": {
      "score": 90,
      "reason": "Candidate's targeted Flutter Developer track directly aligns with the job responsibilities for cross-platform iOS/Android development using Flutter and Dart."
    },
    "skills_match": {
      "score": 85,
      "reason": "Strong match on core requirements: 3 years Flutter/Dart experience, BLoC/Provider state management, REST API and WebSocket integration, Clean Architecture familiarity, and native iOS/Android exposure."
    },
    "seniority_fit": {
      "score": 90,
      "reason": "3 years of professional experience exceeds the 2-year minimum requirement and aligns well with mid-level expectations without over-qualification."
    },
    "location_eligibility": {
      "score": 40,
      "reason": "Tunisian national requiring German visa sponsorship; uncertainty around Healy's sponsorship willingness and target country eligibility creates significant risk."
    },
    "language_requirements": {
      "score": 85,
      "reason": "English full professional proficiency meets the job's core communication requirement; German is listed as a plus and not required."
    }
  },
  "key_strengths": [
    "3 years of professional Flutter development with BLoC, Provider, and state management expertise",
    "Demonstrated experience with REST APIs, WebSockets, and native iOS/Android integration",
    "Strong backend skills (Python/FastAPI, Java/Spring Boot) supporting full cross-functional collaboration",
    "Clean Architecture, automated testing, and CI/CD experience in production mobile apps"
  ],
  "critical_gaps": [
    "Requires German work visa sponsorship with no confirmation of employer sponsorship availability",
    "German language skills absent (listed as a plus, not required)",
    "Location is Berlin-based with hybrid model requiring physical presence"
  ],
  "summary": "Strong technical match for the Flutter Developer role with relevant mid-level experience in state management, APIs, and native integration. Visa sponsorship for Germany presents the primary eligibility uncertainty despite solid overall qualifications."
}
```

---

### Model: `free/gpt-6-luna`
- **Status**: SUCCESS
- **Execution Time**: 3.1s
- **Tokens**: Prompt: 2983 | Completion: 523 | Total: 3506

**Model Response Output:**
```json
{
  "overall_score": 72,
  "verdict": "maybe",
  "disqualifying_flags": [
    "Requires Germany visa sponsorship; not an EU/Gulf citizen or resident",
    "Target country work authorization requires employer sponsorship"
  ],
  "dimensions": {
    "role_match": {
      "score": 90,
      "reason": "Candidate has 3 years of dedicated Flutter/mobile development experience, matching the job's core focus on cross-platform Flutter app development for iOS and Android. Multiple roles and projects align with the specified tasks."
    },
    "skills_match": {
      "score": 88,
      "reason": "Strong match on Flutter, Dart, state management (BLoC, Provider), REST APIs, WebSocket, architecture patterns, and native integration. Meets all stated technical requirements; German not required."
    },
    "seniority_fit": {
      "score": 80,
      "reason": "3 years of professional experience exceeds the minimum 2-year requirement, fitting a mid-level Flutter developer role without being overqualified."
    },
    "location_eligibility": {
      "score": 30,
      "reason": "Candidate is based in Tunisia and requires German/visa sponsorship to work in Germany; eligibility depends on employer willingness to sponsor and successful visa process."
    },
    "language_requirements": {
      "score": 95,
      "reason": "Full professional English meets the job's communication requirement. German is listed as a plus and is not required."
    }
  },
  "key_strengths": [
    "3 years of professional Flutter/Dart development across multiple roles",
    "Proven experience with state management, REST APIs, WebSockets, and native integrations",
    "Strong mobile architecture and offline-first development skills",
    "Full professional English communication",
    "Additional backend, data, and DevOps skills provide versatility"
  ],
  "critical_gaps": [
    "Requires employer visa sponsorship for Germany",
    "German language not present (only a plus, not required)"
  ],
  "summary": "The candidate strongly matches the Flutter developer role with 3 years of professional experience, solid skills in the required technologies, and exceeds the minimum experience threshold. The primary concern is work authorization, as visa sponsorship is required for Germany."
}
```

---

### Model: `free/glm-5.3-flashx`
- **Status**: SUCCESS
- **Execution Time**: 4.43s
- **Tokens**: Prompt: 2989 | Completion: 476 | Total: 3465

**Model Response Output:**
```json
{"overall_score": 82, "verdict": "apply", "disqualifying_flags": ["Needs employer visa sponsorship; not an EU citizen or resident. Germany does not sponsor visas for applicants outside the highly-skilled Shortage Occupations list; Flutter developers are not currently on the official shortage list, making legal work authorization uncertain."], "dimensions": {"role_match": {"score": 95, "reason": "The candidate's track and roles (Flutter Developer) match the job title and tasks (cross-platform iOS/Android development in Flutter) precisely."}, "skills_match": {"score": 92, "reason": "Strong Flutter/Dart experience across multiple real apps, with BLoC, Provider, state management, REST APIs, WebSockets, native channels, and CI/CD. Clean Architecture/MVVM and automated testing are implied but not explicitly documented."}, "seniority_fit": {"score": 85, "reason": "3 years of professional mobile development plus internship and extensive personal projects exceeds the 2-year requirement; no over-qualification."}, "location_eligibility": {"score": 25, "reason": "Candidate is Tunisian and requires employer visa sponsorship; Berlin-based role without explicit remote option creates significant legal work authorization barriers."}, "language_requirements": {"score": 90, "reason": "Fluent English meets the requirement; German is only a plus and not required. French and Arabic are additional strengths for an international team."}}, "key_strengths": ["3+ years of professional Flutter/Dart experience across multiple production apps", "Strong state management skills (BLoC, Provider) and offline-first architecture", "REST API, WebSocket, and native platform channel experience", "Clean code, CI/CD, and testing practices", "English fluency plus French and Arabic"], "critical_gaps": ["Visa sponsorship required for Germany; no EU citizenship or residence", "Clean Architecture/MVVM explicitly not documented in profile", "Automated testing experience mentioned but not detailed"], "summary": "Strong Flutter candidate with 3 years of relevant experience exceeding the job's 2-year requirement, but visa sponsorship needs present a significant barrier for a Berlin-based position. The role may be worth pursuing if the company supports remote work or visa sponsorship."}
```

---

### Model: `free/mimo-v2.6-pro`
- **Status**: SUCCESS
- **Execution Time**: 2.91s
- **Tokens**: Prompt: 2976 | Completion: 467 | Total: 3443

**Model Response Output:**
```json
{"overall_score": 78, "verdict": "maybe", "disqualifying_flags": ["needs visa sponsorship (Germany)", "German language not required but preferred, candidate has no German"], "dimensions": {"role_match": {"score": 95, "reason": "Candidate's primary track is Mobile/Flutter with 3 years of professional Flutter experience, directly aligning with the job's core responsibilities of cross-platform app development."}, "skills_match": {"score": 90, "reason": "Strong match on Flutter/Dart, state management (BLoC/Provider), REST APIs, WebSockets, clean architecture, and native experience (Java/Kotlin, Swift). Meets or exceeds all required technical competencies."}, "seniority_fit": {"score": 85, "reason": "3 years of professional experience exceeds the 2+ years requirement; appropriately senior without being overqualified for a Flutter developer role."}, "location_eligibility": {"score": 30, "reason": "Candidate is based in Tunisia and requires visa sponsorship to work in Germany. While visa sponsorship may be possible, it is an unknown and significant barrier without confirmation of employer willingness."}, "language_requirements": {"score": 95, "reason": "English proficiency is confirmed at full professional level, meeting the very good English requirement. German is listed as a plus and is not required."}}, "key_strengths": ["3+ years professional Flutter/Dart mobile development experience", "Proven state management expertise (BLoC, Provider)", "REST API and WebSocket integration experience", "Native iOS/Android development knowledge (Swift/Kotlin)", "Clean architecture understanding and automated testing practices", "Fluent in English, which meets communication requirements"], "critical_gaps": ["Requires German work visa sponsorship; employer willingness unknown", "No German language skills (only a plus for this role)", "Location in Tunisia, not local to Berlin"], "summary": "The candidate is a strong technical match for the Flutter developer role with 3 years of professional experience exceeding requirements and proficiency in all core technologies. The primary concern is the need for German visa sponsorship, which is an unknown factor that could disqualify the application depending on the company's willingness to sponsor."}
```

---

### Model: `free/jev-1.13`
- **Status**: FAILED
- **Execution Time**: 0.19s
- **Tokens**: Prompt: 0 | Completion: 0 | Total: 0
- **Error / Issue**: `HTTP 400: {"error":{"message":"Model 'free/jev-1.13' is a Jev Group Decision model and cannot be called on /v1/chat/completions. Please use POST /v1/decisions instead (docs: https://apinex.bond/developers/model`

---
