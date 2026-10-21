# Flutter Developer application – Mohamed Hassen Amara

```text
Subject: Flutter Developer application – Mohamed Hassen Amara

Hi Adam,

I'm applying for the Flutter Developer role at Healy World and wanted to reach out directly.

At Reality Sports I built the Flutter frontend for a sports management app with 10+ screens and integrated 15+ RESTful backend services for real-time data sync. I also set up GitHub Actions pipelines for automated builds and releases, and refactored a legacy codebase under Clean Architecture, cutting the app's binary size by 15%.

Would you be able to take a look at my attached CV and let me know if you'd recommend me for the role?

Best regards,
Mohamed Hassen Amara
```

model: claude-sonnet-5 | prompt: outreach/v13 | language: en (rule: en) | words: 98

## Code checks
- warning [company] body: The company name “Healy World GmbH” isn't mentioned


## Claude claim verifier: passed
- **supported** “The candidate is applying for the Flutter Developer role.” (source facts; FACTS says the candidate is applying, and RECIPIENT names the job as a Flutter developer role.)
- **supported** “The candidate's name is Mohamed Hassen Amara.” (source facts; The name matches FACTS.)
- **not_a_claim** “Greeting to Adam.” (source recipient; This is a greeting, and the name matches the contact in RECIPIENT.)
- **supported** “The candidate is applying for the Flutter Developer role at Healy World.” (source facts; FACTS confirms the application, and RECIPIENT names Healy World GmbH and the Flutter developer job.)
- **not_a_claim** “The candidate wanted to reach out directly.” (source -; This states the writer's intent, not a fact.)
- **supported** “At Reality Sports the candidate built the Flutter frontend for a sports management app with 10+ screens.” (source pool:1)
- **supported** “At Reality Sports the candidate integrated 15+ RESTful backend services for real-time data sync.” (source pool:1)
- **supported** “The candidate set up GitHub Actions pipelines for automated builds and releases.” (source pool:1)
- **supported** “The candidate refactored a legacy codebase under Clean Architecture.” (source pool:1)
- **supported** “The refactor cut the app's binary size by 15%.” (source pool:1; The same bullet ties the 15% reduction to the refactor.)
- **not_a_claim** “Request to review the CV and recommend the candidate.” (source -; This is a request.)
- **not_a_claim** “Sign-off with the writer's name.” (source -; This is a sign-off.)
