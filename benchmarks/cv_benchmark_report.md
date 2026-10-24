# APInex Free-Tier Models CV Generation Benchmark Report
**Generated at:** 2026-10-24 17:15:27
**Total models tested:** 10 (excluding `free/jev-1.13`)

## 1. Summary Comparison

| Model | Status | Latency (s) | Prompt Tokens | Output Tokens | Total Tokens | Summary Words | Banned Words Found | JSON Valid |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|
| `free/muse-spark-1.3` | **FAIL** | 4.61s | 4345 | 744 | 5089 | - | None | No |
| `free/deepseek-v4.1-flash` | **FAIL** | 3.92s | 4353 | 755 | 5108 | - | None | No |
| `free/glm-5.3-flash` | **OK** | 7.01s | 4357 | 1000 | 5357 | 38 | None | Yes |
| `free/minimax-m3.1-flash` | **OK** | 5.38s | 4351 | 1224 | 5575 | 36 | None | Yes |
| `free/glm-5.3` | **OK** | 4.89s | 4356 | 1131 | 5487 | 43 | None | Yes |
| `free/gemini-3.8-flash` | **OK** | 4.19s | 4348 | 850 | 5198 | 38 | None | Yes |
| `free/deepseek-v4-pro-0813` | **OK** | 4.91s | 4356 | 1097 | 5453 | 42 | None | Yes |
| `free/gpt-6-luna` | **OK** | 4.0s | 4352 | 740 | 5092 | 46 | None | Yes |
| `free/glm-5.3-flashx` | **OK** | 4.81s | 4358 | 909 | 5267 | 36 | None | Yes |
| `free/mimo-v2.6-pro` | **OK** | 5.1s | 4345 | 1145 | 5490 | 35 | None | Yes |

---

## 2. Structural & Layout Adherence

| Model | Roles Extracted (Bullets per ID) | Projects Extracted | Skill Groups |
|---|---|---|---|
| `free/muse-spark-1.3` | - | - | - |
| `free/deepseek-v4.1-flash` | - | - | - |
| `free/glm-5.3-flash` | Role 6: 3b, Role 7: 2b, Role 8: 2b, Role 9: 1b | Proj 13: 2b | 3 groups |
| `free/minimax-m3.1-flash` | Role 6: 4b, Role 7: 3b, Role 8: 3b, Role 9: 1b | Proj 13: 3b | 4 groups |
| `free/glm-5.3` | Role 6: 4b, Role 7: 3b, Role 8: 3b, Role 9: 2b | Proj 13: 3b | 4 groups |
| `free/gemini-3.8-flash` | Role 6: 4b, Role 7: 3b, Role 8: 3b, Role 9: 2b | Proj 13: 3b | 4 groups |
| `free/deepseek-v4-pro-0813` | Role 6: 4b, Role 7: 2b, Role 8: 2b, Role 9: 1b | Proj 13: 2b | 4 groups |
| `free/gpt-6-luna` | Role 6: 4b, Role 7: 3b, Role 8: 3b, Role 9: 2b | Proj 13: 2b | 4 groups |
| `free/glm-5.3-flashx` | Role 6: 4b, Role 7: 3b, Role 8: 3b, Role 9: 2b | Proj 13: 3b | 4 groups |
| `free/mimo-v2.6-pro` | Role 6: 4b, Role 7: 3b, Role 8: 3b, Role 9: 2b | Proj 13: 3b | 3 groups |

---

## 3. Generated Summaries Review

### Model: `free/muse-spark-1.3`
- **Failed with error**: `Invalid JSON generated: Expecting ',' delimiter: line 1 column 3839 (char 3838)`

---

### Model: `free/deepseek-v4.1-flash`
- **Failed with error**: `Invalid JSON generated: Extra data: line 1 column 3894 (char 3893)`

---

### Model: `free/glm-5.3-flash`
> "Mobile developer with 3 years of professional experience building cross-platform Flutter applications for consumer and enterprise users. Recent work includes a Flutter BLoC app with offline-first sync and native camera integration, plus backend services for feature-rich mobile products."
- **Word count**: 38 words (Target: ~45 words)
- **Banned words check**: Clean

---

### Model: `free/minimax-m3.1-flash`
> "Mobile and backend engineer with 3 years of professional experience building cross-platform apps with Flutter, Dart, and scalable REST APIs. Recent work includes an offline-first field service application using BLoC state management and native platform channels."
- **Word count**: 36 words (Target: ~45 words)
- **Banned words check**: Clean

---

### Model: `free/glm-5.3`
> "Mobile developer with 3 years of professional experience building cross-platform apps with Flutter and Dart, now targeting roles in health-tech mobile development. Recent work includes an offline-first field service app with modular architecture, plus real-time chat and performance-optimized modules shipped to app stores."
- **Word count**: 43 words (Target: ~45 words)
- **Banned words check**: Clean

---

### Model: `free/gemini-3.8-flash`
> "Flutter Developer with 3 years of professional mobile experience building cross-platform apps for iOS and Android. Recent work includes a privacy-first resume parser on a local Mistral LLM plus offline-first enterprise field service apps using BLoC state management."
- **Word count**: 38 words (Target: ~45 words)
- **Banned words check**: Clean

---

### Model: `free/deepseek-v4-pro-0813`
> "Mobile engineer with 3 years of professional Flutter development across commercial and educational apps, now contributing full-stack backend and DevOps expertise. Work includes a clean-architecture field service app with offline sync, real-time chat, and native platform integrations for health and wellness products."
- **Word count**: 42 words (Target: ~45 words)
- **Banned words check**: Clean

---

### Model: `free/gpt-6-luna`
> "Software engineer with 3 years of professional experience in mobile development and backend development, specializing in cross-platform mobile apps. Recent work includes a Flutter field service application built with a modular Clean Architecture and automated BLoC state management, plus real-time mobile apps shipped to international learners."
- **Word count**: 46 words (Target: ~45 words)
- **Banned words check**: Clean

---

### Model: `free/glm-5.3-flashx`
> "Mobile developer with 3 years of professional experience building cross-platform applications in Flutter and Dart. Recent work includes a privacy-first Flutter field service app using Drift and an end-to-end BLoC architecture implemented for offline enterprise workflows."
- **Word count**: 36 words (Target: ~45 words)
- **Banned words check**: Clean

---

### Model: `free/mimo-v2.6-pro`
> "Flutter and Mobile Developer with 3 years of professional experience across Android, iOS, and Flutter cross-platform development. Recent work includes a BLoC-based offline-first field service app and real-time messaging features serving thousands of daily users."
- **Word count**: 35 words (Target: ~45 words)
- **Banned words check**: Clean

---


## 4. Full Raw Model Responses

### Raw Output: `free/muse-spark-1.3`
```text
{"summary":"Flutter and Mobile Developer with 3 years of professional experience in cross-platform app development and backend integrations. Recent work includes a modular offline-first field service app with BLoC state management and real-time chat features built for thousands of daily users.","roles":[{"id":6,"title":"Full-Stack Developer","org":"Freelance","bullets":[{"text":"Delivered custom Flutter mobile apps and web dashboards end to end for international clients, shipping features from initial concept through store deployment.","source_fact_index":"0"},{"text":"Developed RESTful APIs with Python and Java Spring Boot, integrating relational databases and third-party authentication services to support mobile clients.","source_fact_index":"1"},{"text":"Set up Docker-based deployment workflows with basic CI automation to ensure reproducible build environments.","source_fact_index":"2"},{"text":"Collaborated directly with non-technical stakeholders to scope requirements, manage release milestones and handle post-launch maintenance.","source_fact_index":"3"}]},{"id":7,"title":"Mobile Developer","org":"E-Taalim","bullets":[{"text":"Built cross-platform features in Flutter/Dart with state management and offline storage, serving thousands of daily learners with responsive UI components.","source_fact_index":"0"},{"text":"Integrated real-time messaging, push notifications and audio streaming using Firebase Cloud Messaging and WebSocket connections.","source_fact_index":"1"},{"text":"Optimized rendering performance and startup latency, reducing memory footprint across entry-level Android devices.","source_fact_index":"2"}]},{"id":8,"title":"Mobile Developer","org":"Cynoia","bullets":[{"text":"Developed and maintained core modules of a cross-platform mobile app using Flutter, including real-time chat, channel navigation and file previewing.","source_fact_index":"0"},{"text":"Implemented local SQLite caching with optimistic UI updates to maintain consistent offline-first state during intermittent connectivity.","source_fact_index":"1"},{"text":"Refactored legacy navigation and state handling logic, resolving memory leaks and improving crash-free session rates.","source_fact_index":"2"}]},{"id":9,"title":"End of Studies Project Intern","org":"Cynapsys by Gfi / Inetum","bullets":[{"text":"Built an internal reporting and notification mobile interface in Flutter connected to backend telemetry services for operational monitoring.","source_fact_index":"0"},{"text":"Implemented event ingestion adapters and data visualization widgets displaying real-time metrics, alerts and historical incident logs.","source_fact_index":"1"}]}],"projects":[{"id":13,"title":"Cross-Platform Enterprise Field Service App","bullets":[{"text":"Engineered an offline-first app in Flutter using Drift/SQLite for local persistence and background queue sync upon reconnection.","source_fact_index":"0"},{"text":"Designed a modular architecture separating presentation, domain business rules and data repositories with automated BLoC state management.","source_fact_index":"1"},{"text":"Integrated camera scanning, PDF work order generation and biometric authentication using native platform channel plugins.","source_fact_index":"2"}]}],"skills":[{"category":"Mobile & Frontend","skills":["Flutter","Dart","BLoC","Provider","Riverpod","Clean Architecture","GoRouter","Firebase"]},{"category":"Core Languages","skills":["Python","Java","Kotlin","Swift","SQL","RESTful APIs","WebSockets","Native Development"]},{"category":"Architectures & Patterns","skills":["Cross-platform Architecture","MVVM","Offline-first","Optimistic UI","Clean Code","Automated Testing","CI/CD","Git"]},{"category":"Cloud, DevOps & Release","skills":["Docker","GitHub Actions","Fastlane","Google Play Console","App Store","Linux","Databases","Monitoring"]
```

---

### Raw Output: `free/deepseek-v4.1-flash`
```text
{"summary":"Software engineer with 3 years of experience in mobile and backend development, now focusing on cross-platform Flutter apps. Recent work includes an offline-first field service app with native integrations and real-time mobile experiences for thousands of users.","roles":[{"id":6,"title":"Full-Stack Developer","org":"Freelance","bullets":[{"text":"Delivered custom Flutter mobile applications and web dashboards end to end for international clients, taking features from concept through App Store and Google Play deployment.","source_fact_index":"0"},{"text":"Developed RESTful backend APIs with Python (FastAPI) and Java (Spring Boot), connecting relational databases and third-party authentication for seamless client integrations.","source_fact_index":"1"},{"text":"Established Docker-based deployment pipelines with CI automation, ensuring reproducible environments across mobile and backend services.","source_fact_index":"2"},{"text":"Partnered directly with non-technical stakeholders to define product scope, manage release milestones and maintain post-launch performance.","source_fact_index":"3"}]},{"id":7,"title":"Mobile Developer","org":"E-Taalim","bullets":[{"text":"Built cross-platform Flutter features for thousands of daily learners, implementing state management, offline storage and responsive UI components.","source_fact_index":"0"},{"text":"Enabled real-time messaging, push notifications and audio streaming through Firebase Cloud Messaging and WebSocket connections for continuous user engagement.","source_fact_index":"1"},{"text":"Optimized rendering performance and startup latency on entry-level Android devices, significantly reducing memory footprint across the user base.","source_fact_index":"2"}]},{"id":8,"title":"Mobile Developer","org":"Cynoia","bullets":[{"text":"Developed core modules of a cross-platform app in Flutter, including real-time chat, channel navigation and file previewing for active users.","source_fact_index":"0"},{"text":"Implemented SQLite caching with optimistic UI updates to maintain consistent offline-first state during intermittent connectivity.","source_fact_index":"1"},{"text":"Refactored legacy navigation and state logic to resolve memory leaks and drive crash-free sessions below target thresholds.","source_fact_index":"2"}]},{"id":9,"title":"End of Studies Project Intern","org":"Cynapsys by Gfi / Inetum","bullets":[{"text":"Built a real-time operational monitoring interface in Flutter connected to backend telemetry services, visualizing metrics and incident logs.","source_fact_index":"0"},{"text":"Implemented event ingestion adapters and automated build pipelines targeting Google Play Console and Apple App Store TestFlight distributions.","source_fact_index":"1"}]}],"projects":[{"id":13,"title":"Cross-Platform Enterprise Field Service App","bullets":[{"text":"Engineered an offline-first Flutter app with Drift/SQLite local persistence and background queue sync upon reconnection.","source_fact_index":"0"},{"text":"Applied modular architecture separating presentation, domain logic and data repositories with automated BLoC state management.","source_fact_index":"1"},{"text":"Integrated camera scanning, PDF work order generation and biometric authentication via native platform channels.","source_fact_index":"2"}]}],"skills":[{"category":"Mobile & Frontend","skills":["Flutter","Dart","BLoC","Riverpod","Provider","Clean Architecture","Native Channels (iOS/Android)","State Management"]},{"category":"Backend Engineering & APIs","skills":["Python","FastAPI","Java","Spring Boot","RESTful APIs","WebSockets","PostgreSQL","Git"]},{"category":"Cloud, DevOps & Release","skills":["Docker","GitHub Actions","CI/CD","Firebase","Fastlane","AWS","Linux","Bash"]},{"category":"Testing & Quality","skills":["Automated Testing","Code Review","Unit Testing","Widget Testing","Regression Testing","UAT"]}]}}
```

---

### Raw Output: `free/glm-5.3-flash`
```json
{
  "summary": "Mobile developer with 3 years of professional experience building cross-platform Flutter applications for consumer and enterprise users. Recent work includes a Flutter BLoC app with offline-first sync and native camera integration, plus backend services for feature-rich mobile products.",
  "roles": [
    {
      "id": 6,
      "title": "Full-Stack Developer",
      "org": "Freelance",
      "bullets": [
        {
          "text": "Delivered end-to-end Flutter mobile and web products for international clients, owning features from initial concept through App Store and Play Console release.",
          "source_fact_index": 0
        },
        {
          "text": "Integrated RESTful APIs and third-party authentication into client apps, ensuring secure data exchange across mobile and dashboard interfaces.",
          "source_fact_index": 1
        },
        {
          "text": "Partnered with non-technical stakeholders to scope product requirements, sequence release milestones and maintain post-launch reliability.",
          "source_fact_index": 3
        }
      ]
    },
    {
      "id": 7,
      "title": "Mobile Developer",
      "org": "E-Taalim",
      "bullets": [
        {
          "text": "Built cross-platform learning features in Flutter with responsive state management, serving thousands of daily active users on entry-level Android devices.",
          "source_fact_index": 0
        },
        {
          "text": "Connected real-time messaging, push notifications and audio streaming via WebSocket and Firebase Cloud Messaging, keeping learners engaged across networks.",
          "source_fact_index": 1
        }
      ]
    },
    {
      "id": 8,
      "title": "Mobile Developer",
      "org": "Cynoia",
      "bullets": [
        {
          "text": "Refactored legacy navigation and state handling, eliminating memory leaks and lifting crash-free sessions above internal targets.",
          "source_fact_index": 2
        },
        {
          "text": "Led automated build and release pipelines to Google Play Console and App Store TestFlight, streamlining feature delivery for the mobile team.",
          "source_fact_index": 3
        }
      ]
    },
    {
      "id": 9,
      "title": "End of Studies Project Intern",
      "org": "Cynapsys by Gfi / Inetum",
      "bullets": [
        {
          "text": "Built a Flutter monitoring interface for internal operational telemetry, visualizing real-time alerts and historical incident data.",
          "source_fact_index": 0
        }
      ]
    }
  ],
  "projects": [
    {
      "id": 13,
      "title": "Cross-Platform Enterprise Field Service App",
      "org": null,
      "bullets": [
        {
          "text": "Engineered an offline-first Flutter app with Drift/SQLite persistence and background queue sync, keeping field workers productive without connectivity.",
          "source_fact_index": 0
        },
        {
          "text": "Architected modular layers separating presentation, domain rules and data repositories around automated BLoC state management, then added native camera and biometric features through platform channels.",
          "source_fact_index": 1
        }
      ]
    }
  ],
  "skills": [
    {
      "category": "Mobile & Frontend",
      "skills": [
        "Flutter",
        "Dart",
        "BLoC",
        "Provider",
        "Clean Architecture",
        "MVVM",
        "Native Channels (iOS/Android)",
        "UI/UX Implementation"
      ]
    },
    {
      "category": "Core Languages",
      "skills": [
        "Java",
        "Kotlin",
        "Swift",
        "Python",
        "JavaScript",
        "SQL",
        "REST APIs",
        "WebSockets"
      ]
    },
    {
      "category": "DevOps, Cloud & Release",
      "skills": [
        "Git",
        "GitHub Actions",
        "CI/CD",
        "Docker",
        "Fastlane",
        "Firebase (Auth, Crashlytics, Remote Config)",
        "App Store & Play Console",
        "Linux"
      ]
    }
  ]
}
```

---

### Raw Output: `free/minimax-m3.1-flash`
```json
{
  "summary": "Mobile and backend engineer with 3 years of professional experience building cross-platform apps with Flutter, Dart, and scalable REST APIs. Recent work includes an offline-first field service application using BLoC state management and native platform channels.",
  "roles": [
    {
      "id": 6,
      "title": "Full-Stack Developer",
      "org": "Freelance",
      "bullets": [
        {
          "text": "Designed and delivered custom Flutter mobile applications and web dashboards end to end for international clients, taking features from initial concept through store deployment.",
          "source_fact_index": 0
        },
        {
          "text": "Developed RESTful backend APIs with Python (FastAPI) and Java (Spring Boot), integrating relational databases and third-party authentication services.",
          "source_fact_index": 1
        },
        {
          "text": "Set up Dockerized deployment workflows and cloud infrastructure, ensuring reproducible environments and basic CI automation.",
          "source_fact_index": 2
        },
        {
          "text": "Collaborated directly with non-technical stakeholders to scope product requirements, manage release milestones and handle post-launch maintenance.",
          "source_fact_index": 3
        }
      ]
    },
    {
      "id": 7,
      "title": "Mobile Developer",
      "org": "E-Taalim",
      "bullets": [
        {
          "text": "Built cross-platform mobile features in Flutter/Dart, implementing state management, offline storage and responsive UI components serving thousands of daily learners.",
          "source_fact_index": 0
        },
        {
          "text": "Integrated real-time messaging, push notifications and audio streaming via Firebase Cloud Messaging and WebSocket connections.",
          "source_fact_index": 1
        },
        {
          "text": "Optimized application rendering performance and startup latency, reducing memory footprint across entry-level Android devices.",
          "source_fact_index": 2
        }
      ]
    },
    {
      "id": 8,
      "title": "Mobile Developer",
      "org": "Cynoia",
      "bullets": [
        {
          "text": "Developed and maintained core modules of the Cynoia cross-platform mobile app using Flutter, including real-time chat, channel navigation and file previewing.",
          "source_fact_index": 0
        },
        {
          "text": "Refactored legacy navigation and state handling logic, resolving memory leaks and driving crash-free session rates below target thresholds.",
          "source_fact_index": 2
        },
        {
          "text": "Participated in automated build and deployment pipelines targeting Google Play Console and Apple App Store TestFlight distributions.",
          "source_fact_index": 3
        }
      ]
    },
    {
      "id": 9,
      "title": "End of Studies Project Intern",
      "org": "Cynapsys by Gfi / Inetum",
      "bullets": [
        {
          "text": "Built an internal reporting and notification mobile interface in Flutter connected to backend telemetry services for operational monitoring.",
          "source_fact_index": 0
        }
      ]
    }
  ],
  "projects": [
    {
      "id": 13,
      "title": "Cross-Platform Enterprise Field Service App",
      "bullets": [
        {
          "text": "Engineered an offline-first mobile application in Flutter using Drift/SQLite for local persistence and background queue sync upon reconnection.",
          "source_fact_index": 0
        },
        {
          "text": "Designed modular architecture separating presentation, domain business rules and data repositories with automated BLoC state management.",
          "source_fact_index": 1
        },
        {
          "text": "Integrated camera scanning, PDF work order generation and biometric authentication using native platform channel plugins.",
          "source_fact_index": 2
        }
      ]
    }
  ],
  "skills": [
    {
      "category": "Mobile & Frontend",
      "skills": [
        "Flutter",
        "Dart",
        "BLoC",
        "Riverpod",
        "Clean Architecture",
        "Native Platform Channels",
        "GoRouter",
        "Firebase (Auth, Crashlytics)"
      ]
    },
    {
      "category": "Backend Engineering & APIs",
      "skills": [
        "Python",
        "FastAPI",
        "Java",
        "Spring Boot",
        "RESTful APIs",
        "WebSockets",
        "SQLAlchemy",
        "Microservices"
      ]
    },
    {
      "category": "Cloud, DevOps & Release",
      "skills": [
        "Docker",
        "Docker Compose",
        "Git",
        "GitHub Actions",
        "CI/CD",
        "AWS (S3, EC2)",
        "Fastlane",
        "Linux"
      ]
    },
    {
      "category": "Databases & Storage",
      "skills": [
        "PostgreSQL",
        "SQLite",
        "Drift",
        "Redis",
        "MongoDB",
        "MySQL",
        "DuckDB",
        "Qdrant"
      ]
    }
  ]
}
```

---

### Raw Output: `free/glm-5.3`
```json
{
  "summary": "Mobile developer with 3 years of professional experience building cross-platform apps with Flutter and Dart, now targeting roles in health-tech mobile development. Recent work includes an offline-first field service app with modular architecture, plus real-time chat and performance-optimized modules shipped to app stores.",
  "roles": [
    {
      "id": 6,
      "title": "Full-Stack Developer",
      "org": "Freelance",
      "bullets": [
        {
          "text": "Delivered end-to-end Flutter mobile applications and web dashboards for international clients, taking features from initial concept through store deployment.",
          "source_fact_index": 0
        },
        {
          "text": "Integrated relational databases and third-party authentication into Python and Java backend APIs to support cross-platform client apps.",
          "source_fact_index": 1
        },
        {
          "text": "Established Docker-based deployment workflows with basic CI automation to guarantee reproducible production environments.",
          "source_fact_index": 2
        },
        {
          "text": "Scoped product requirements with non-technical stakeholders and managed release milestones across multiple client engagements.",
          "source_fact_index": 3
        }
      ]
    },
    {
      "id": 7,
      "title": "Mobile Developer",
      "org": "E-Taalim",
      "bullets": [
        {
          "text": "Built cross-platform Flutter features with state management and responsive UI components serving thousands of daily learners.",
          "source_fact_index": 0
        },
        {
          "text": "Integrated real-time messaging, push notifications, and audio streaming via Firebase Cloud Messaging and WebSocket connections.",
          "source_fact_index": 1
        },
        {
          "text": "Optimized rendering performance and startup latency, reducing memory footprint across entry-level Android devices.",
          "source_fact_index": 2
        }
      ]
    },
    {
      "id": 8,
      "title": "Mobile Developer",
      "org": "Cynoia",
      "bullets": [
        {
          "text": "Developed core Flutter modules including real-time chat, channel navigation, and file previewing for the cross-platform app.",
          "source_fact_index": 0
        },
        {
          "text": "Implemented SQLite caching with optimistic UI updates to maintain consistent offline-first state during network interruptions.",
          "source_fact_index": 1
        },
        {
          "text": "Refactored legacy navigation and state logic, eliminating memory leaks and lowering crash rates below target thresholds.",
          "source_fact_index": 2
        }
      ]
    },
    {
      "id": 9,
      "title": "End of Studies Project Intern",
      "org": "Cynapsys by Gfi / Inetum",
      "bullets": [
        {
          "text": "Built a Flutter reporting and notification interface connected to backend telemetry services for operational monitoring.",
          "source_fact_index": 0
        },
        {
          "text": "Implemented event ingestion adapters and real-time data visualization widgets for metrics, alerts, and incident logs.",
          "source_fact_index": 1
        }
      ]
    }
  ],
  "projects": [
    {
      "id": 13,
      "title": "Cross-Platform Enterprise Field Service App",
      "bullets": [
        {
          "text": "Engineered an offline-first Flutter app using Drift/SQLite with background queue sync upon reconnection.",
          "source_fact_index": 0
        },
        {
          "text": "Designed modular architecture separating presentation, domain rules, and data repositories with automated BLoC state management.",
          "source_fact_index": 1
        },
        {
          "text": "Integrated camera scanning, PDF work order generation, and biometric authentication via native platform channel plugins.",
          "source_fact_index": 2
        }
      ]
    }
  ],
  "skills": [
    {
      "category": "Mobile & Frontend",
      "skills": ["Flutter", "Dart", "BLoC", "Provider", "Clean Architecture", "MVVM", "Native Channels", "Fastlane"]
    },
    {
      "category": "Backend Engineering & APIs",
      "skills": ["Python", "FastAPI", "Java", "Spring Boot", "RESTful APIs", "WebSockets", "PostgreSQL", "Git"]
    },
    {
      "category": "Databases & Storage",
      "skills": ["SQLite", "Drift", "PostgreSQL", "MongoDB", "Redis", "Firebase (Auth, Crashlytics)"]
    },
    {
      "category": "Cloud, DevOps & Release",
      "skills": ["Docker", "GitHub Actions", "CI/CD", "Fastlane", "Git", "Firebase Cloud Messaging", "App Store", "TestFlight"]
    }
  ]
}
```

---

### Raw Output: `free/gemini-3.8-flash`
```json
{"summary": "Flutter Developer with 3 years of professional mobile experience building cross-platform apps for iOS and Android. Recent work includes a privacy-first resume parser on a local Mistral LLM plus offline-first enterprise field service apps using BLoC state management.", "roles": [{"id": 6, "title": "Full-Stack Developer", "org": "Freelance", "bullets": [{"text": "Delivered custom Flutter mobile apps and web dashboards end to end for international clients, shipping features from concept through store deployment.", "source_fact_index": 0}, {"text": "Built RESTful APIs with Python FastAPI and Java Spring Boot, integrating relational databases and third-party authentication services.", "source_fact_index": 1}, {"text": "Established Docker-based deployment workflows with basic CI automation, ensuring reproducible production environments.", "source_fact_index": 2}, {"text": "Partnered directly with non-technical stakeholders to scope requirements, manage release milestones and maintain post-launch releases.", "source_fact_index": 3}]}, {"id": 7, "title": "Mobile Developer", "org": "E-Taalim", "bullets": [{"text": "Implemented cross-platform learning features in Flutter/Dart with state management, offline storage and responsive UI serving thousands of daily users.", "source_fact_index": 0}, {"text": "Connected real-time messaging, push notifications and audio streaming via Firebase Cloud Messaging and WebSocket services.", "source_fact_index": 1}, {"text": "Optimized rendering performance and startup latency, shrinking the memory footprint across entry-level Android devices.", "source_fact_index": 2}]}, {"id": 8, "title": "Mobile Developer", "org": "Cynoia", "bullets": [{"text": "Developed core Flutter modules including real-time chat, channel navigation and file previewing for the cross-platform app.", "source_fact_index": 0}, {"text": "Implemented local SQLite caching with optimistic UI updates, keeping offline-first state consistent during network interruptions.", "source_fact_index": 1}, {"text": "Refactored legacy navigation and state logic, resolving memory leaks and lifting crash-free session rates above target thresholds.", "source_fact_index": 2}]}, {"id": 9, "title": "End of Studies Project Intern", "org": "Cynapsys by Gfi / Inetum", "bullets": [{"text": "Built an internal reporting and notification interface in Flutter connected to backend telemetry for operational monitoring.", "source_fact_index": 0}, {"text": "Implemented event ingestion adapters and data visualization widgets displaying real-time metrics, alerts and historical incident logs.", "source_fact_index": 1}]}], "projects": [{"id": 13, "title": "Cross-Platform Enterprise Field Service App", "bullets": [{"text": "Engineered an offline-first mobile app in Flutter using Drift/SQLite for local persistence with queued sync on reconnection.", "source_fact_index": 0}, {"text": "Designed modular architecture separating presentation, domain rules and data repositories with automated BLoC state management.", "source_fact_index": 1}, {"text": "Integrated camera scanning, PDF work order generation and biometric authentication through native platform channel plugins.", "source_fact_index": 2}]}], "skills": [{"category": "Mobile & Frontend", "skills": ["Flutter", "Dart", "Cross-platform Architecture", "Clean Architecture", "MVVM", "BLoC", "Riverpod", "Native Development"]}, {"category": "Core Languages", "skills": ["Dart", "Python", "Java", "Swift", "Kotlin", "SQL"]}, {"category": "APIs & Integration", "skills": ["RESTful APIs", "WebSockets", "Firebase (Auth, Crashlytics, Remote Config)", "Third-party Authentication"]}, {"category": "DevOps, Cloud & Release", "skills": ["Git", "GitHub Actions", "CI/CD", "Docker", "Fastlane", "App Store & Play Store Release"]}]}
```

---

### Raw Output: `free/deepseek-v4-pro-0813`
```json
{
  "summary": "Mobile engineer with 3 years of professional Flutter development across commercial and educational apps, now contributing full-stack backend and DevOps expertise. Work includes a clean-architecture field service app with offline sync, real-time chat, and native platform integrations for health and wellness products.",
  "roles": [
    {
      "id": 6,
      "title": "Full-Stack Developer",
      "org": "Freelance",
      "bullets": [
        {
          "text": "Designed and delivered custom Flutter mobile applications and web dashboards end to end for international clients, taking features from initial concept through store deployment.",
          "source_fact_index": "0"
        },
        {
          "text": "Integrated RESTful backend APIs with Python FastAPI and Java Spring Boot, connecting relational databases and third-party authentication services to support cross-platform clients.",
          "source_fact_index": "1"
        },
        {
          "text": "Established deployment workflows using Docker containers and cloud infrastructure, ensuring reproducible environments and basic CI automation.",
          "source_fact_index": "2"
        },
        {
          "text": "Collaborated directly with non-technical stakeholders to scope product requirements, manage release milestones and handle post-launch maintenance.",
          "source_fact_index": "3"
        }
      ]
    },
    {
      "id": 7,
      "title": "Mobile Developer",
      "org": "E-Taalim",
      "bullets": [
        {
          "text": "Implemented state management, offline storage and responsive UI components in Flutter/Dart, supporting thousands of daily learners across entry-level devices.",
          "source_fact_index": "0"
        },
        {
          "text": "Integrated real-time messaging, push notifications and audio streaming using Firebase Cloud Messaging and WebSocket connections.",
          "source_fact_index": "1"
        }
      ]
    },
    {
      "id": 8,
      "title": "Mobile Developer",
      "org": "Cynoia",
      "bullets": [
        {
          "text": "Maintained core modules of the cross-platform app using Flutter, including real-time chat, channel navigation and file previewing.",
          "source_fact_index": "0"
        },
        {
          "text": "Refactored legacy navigation and state handling logic, resolving memory leaks and decreasing crash-free session rates below target thresholds.",
          "source_fact_index": "2"
        }
      ]
    },
    {
      "id": 9,
      "title": "End of Studies Project Intern",
      "org": "Cynapsys by Gfi / Inetum",
      "bullets": [
        {
          "text": "Built an internal reporting and notification mobile interface in Flutter connected to backend telemetry services for operational monitoring.",
          "source_fact_index": "0"
        }
      ]
    }
  ],
  "projects": [
    {
      "id": 13,
      "title": "Cross-Platform Enterprise Field Service App",
      "bullets": [
        {
          "text": "Engineered an offline-first mobile application in Flutter using Drift/SQLite for local persistence and background queue sync upon reconnection.",
          "source_fact_index": "0"
        },
        {
          "text": "Designed modular architecture separating presentation, domain business rules and data repositories with automated BLoC state management.",
          "source_fact_index": "1"
        }
      ]
    }
  ],
  "skills": [
    {
      "category": "Mobile & Frontend",
      "skills": [
        "Flutter",
        "Dart",
        "BLoC",
        "Provider",
        "Riverpod",
        "Clean Architecture",
        "State Management",
        "Native Channels"
      ]
    },
    {
      "category": "Backend Engineering & APIs",
      "skills": [
        "Python",
        "FastAPI",
        "Java",
        "Spring Boot",
        "RESTful APIs",
        "WebSockets",
        "Firebase",
        "Git"
      ]
    },
    {
      "category": "Databases & Storage",
      "skills": [
        "SQLite",
        "PostgreSQL",
        "Drift",
        "Local Caching",
        "Optimistic UI",
        "Offline-First"
      ]
    },
    {
      "category": "Cloud, DevOps & Release",
      "skills": [
        "Docker",
        "GitHub Actions",
        "Fastlane",
        "CI/CD",
        "App Store Deployment",
        "TestFlight",
        "Git",
        "Agile"
      ]
    }
  ]
}
```

---

### Raw Output: `free/gpt-6-luna`
```json
{"summary":"Software engineer with 3 years of professional experience in mobile development and backend development, specializing in cross-platform mobile apps. Recent work includes a Flutter field service application built with a modular Clean Architecture and automated BLoC state management, plus real-time mobile apps shipped to international learners.","roles":[{"id":6,"title":"Full-Stack Developer","org":"Freelance","bullets":[{"text":"Delivered end-to-end custom Flutter mobile apps and web dashboards for international clients, taking features from initial concept through App Store and Play Store deployment.","source_fact_index":0},{"text":"Built RESTful APIs with Python (FastAPI) and Java (Spring Boot), integrating relational databases and third-party authentication services to support mobile backends.","source_fact_index":1},{"text":"Established deployment workflows with Docker containers and CI automation, delivering reproducible environments for cross-platform release cycles.","source_fact_index":2},{"text":"Coordinated with non-technical stakeholders to scope requirements, manage release milestones, and handle post-launch maintenance for mobile products.","source_fact_index":3}]},{"id":7,"title":"Mobile Developer","org":"E-Taalim","bullets":[{"text":"Implemented cross-platform features in Flutter/Dart with state management, offline storage, and responsive UIs serving thousands of daily learners.","source_fact_index":0},{"text":"Connected real-time messaging, push notifications, and audio streaming via Firebase Cloud Messaging and WebSocket services for a responsive learning experience.","source_fact_index":1},{"text":"Optimized rendering performance and startup latency, reducing memory footprint across entry-level Android devices.","source_fact_index":2}]},{"id":8,"title":"Mobile Developer","org":"Cynoia","bullets":[{"text":"Developed and maintained core Flutter modules including real-time chat, channel navigation, and file previewing for the cross-platform mobile app.","source_fact_index":0},{"text":"Introduced local SQLite caching and optimistic UI updates, keeping state consistent during intermittent network conditions.","source_fact_index":1},{"text":"Refactored legacy navigation and state logic, resolving memory leaks and improving crash-free session rates.","source_fact_index":2}]},{"id":9,"title":"End of Studies Project Intern","org":"Cynapsys by Gfi / Inetum","bullets":[{"text":"Built an internal Flutter reporting and notification interface connected to backend telemetry services for operational monitoring.","source_fact_index":0},{"text":"Implemented event ingestion adapters and real-time data visualization widgets displaying metrics, alerts, and incident logs.","source_fact_index":1}]}],"projects":[{"id":13,"title":"Cross-Platform Enterprise Field Service App","bullets":[{"text":"Engineered an offline-first Flutter app with Drift/SQLite persistence and background queue sync for reliable field operations.","source_fact_index":0},{"text":"Designed modular architecture separating presentation, domain rules, and repositories with automated BLoC state management and Clean Architecture.","source_fact_index":1}]}],"skills":[{"category":"Mobile Development","skills":["Flutter","Dart","State Management (BLoC, Riverpod)","Clean Architecture","MVVM","REST & WebSocket APIs","Firebase (Auth, Crashlytics)","Automated Testing"]},{"category":"Core Languages","skills":["Dart","Kotlin","Java","Python","SQL","Git/GitHub"]},{"category":"Databases & Local Storage","skills":["SQLite (Drift)","PostgreSQL","Offline-First Design","SQLite Caching"]},{"category":"Cloud, DevOps & Release","skills":["Docker","CI/CD","GitHub Actions","Fastlane","App Store & Play Console","AWS (S3, EC2)"]}]}
```

---

### Raw Output: `free/glm-5.3-flashx`
```json
{"summary": "Mobile developer with 3 years of professional experience building cross-platform applications in Flutter and Dart. Recent work includes a privacy-first Flutter field service app using Drift and an end-to-end BLoC architecture implemented for offline enterprise workflows.", "roles": [{"id": 6, "title": "Full-Stack Developer", "org": "Freelance", "bullets": [{"text": "Delivered end-to-end Flutter mobile applications and web dashboards for international clients, moving features from initial concept through store deployment on both platforms.", "source_fact_index": 0}, {"text": "Developed RESTful backend APIs with Python FastAPI and Java Spring Boot, integrating relational databases and third-party authentication services to support client apps.", "source_fact_index": 1}, {"text": "Established Docker-based deployment workflows and cloud infrastructure, guaranteeing reproducible environments and introducing baseline CI automation.", "source_fact_index": 2}, {"text": "Collaborated directly with non-technical stakeholders to scope product requirements, manage release milestones and handle post-launch maintenance.", "source_fact_index": 3}]}, {"id": 7, "title": "Mobile Developer", "org": "E-Taalim", "bullets": [{"text": "Built cross-platform mobile features in Flutter/Dart, implementing state management, offline storage and responsive UI components serving thousands of daily learners.", "source_fact_index": 0}, {"text": "Integrated real-time messaging, push notifications and audio streaming through Firebase Cloud Messaging and WebSocket connections for engaged user retention.", "source_fact_index": 1}, {"text": "Optimized rendering performance and startup latency, cutting memory footprint across entry-level Android devices to broaden market reach.", "source_fact_index": 2}]}, {"id": 8, "title": "Mobile Developer", "org": "Cynoia", "bullets": [{"text": "Developed and maintained core modules of the cross-platform Cynoia app, including real-time chat, channel navigation and file previewing with Flutter.", "source_fact_index": 0}, {"text": "Implemented local SQLite caching with optimistic UI updates, keeping state consistent during intermittent network conditions.", "source_fact_index": 1}, {"text": "Refactored legacy navigation and state handling, resolving memory leaks and pushing crash-free sessions below target thresholds.", "source_fact_index": 2}]}, {"id": 9, "title": "End of Studies Project Intern", "org": "Cynapsys by Gfi / Inetum", "bullets": [{"text": "Built an internal reporting and notification mobile interface in Flutter connected to backend telemetry services for operational monitoring.", "source_fact_index": 0}, {"text": "Implemented event ingestion adapters and data visualization widgets displaying real-time metrics, alerts and historical incident logs.", "source_fact_index": 1}]}], "projects": [{"id": 13, "title": "Cross-Platform Enterprise Field Service App", "bullets": [{"text": "Engineered an offline-first mobile application in Flutter using Drift/SQLite for local persistence and background queue sync upon reconnection.", "source_fact_index": 0}, {"text": "Designed modular architecture separating presentation, domain business rules and data repositories with automated BLoC state management.", "source_fact_index": 1}, {"text": "Integrated camera scanning, PDF work order generation and biometric authentication using native platform channel plugins for iOS and Android.", "source_fact_index": 2}]}], "skills": [{"category": "Mobile & Frontend", "skills": ["Flutter", "Dart", "BLoC", "State Management", "Cross-platform Architecture", "Clean Architecture", "Native Development", "Git"]}, {"category": "Backend Engineering & APIs", "skills": ["Python", "FastAPI", "Java", "Spring Boot", "RESTful APIs", "WebSockets", "Firebase Services", "PostgreSQL"]}, {"category": "DevOps, Cloud & Release", "skills": ["Docker", "CI/CD", "GitHub Actions", "Fastlane", "App Store Deployment", "Linux", "AWS", "Docker Compose"]}, {"category": "Databases & Storage", "skills": ["SQLite", "Drift", "PostgreSQL", "MySQL", "Redis", "MongoDB", "Offline-First Design", "Local Caching"]}]}
```

---

### Raw Output: `free/mimo-v2.6-pro`
```json
{
  "summary": "Flutter and Mobile Developer with 3 years of professional experience across Android, iOS, and Flutter cross-platform development. Recent work includes a BLoC-based offline-first field service app and real-time messaging features serving thousands of daily users.",
  "roles": [
    {
      "id": 6,
      "title": "Full-Stack Developer",
      "org": "Freelance",
      "bullets": [
        {
          "text": "Delivered end-to-end Flutter mobile apps and web dashboards for international clients, shipping features from initial concept through store deployment.",
          "source_fact_index": 0
        },
        {
          "text": "Integrated RESTful APIs with Python (FastAPI) and Java (Spring Boot), connecting relational databases and third-party authentication.",
          "source_fact_index": 1
        },
        {
          "text": "Implemented Docker-based deployment workflows with CI automation to ensure reproducible environments across client projects.",
          "source_fact_index": 2
        },
        {
          "text": "Partnered with non-technical stakeholders to scope requirements, manage release milestones and maintain post-launch performance.",
          "source_fact_index": 3
        }
      ]
    },
    {
      "id": 7,
      "title": "Mobile Developer",
      "org": "E-Taalim",
      "bullets": [
        {
          "text": "Built cross-platform learning features in Flutter/Dart with state management and responsive UI, serving thousands of daily users.",
          "source_fact_index": 0
        },
        {
          "text": "Enabled real-time messaging, push notifications and audio streaming via Firebase Cloud Messaging and WebSocket integration.",
          "source_fact_index": 1
        },
        {
          "text": "Cut memory footprint and startup latency on entry-level Android devices through rendering and asset optimizations.",
          "source_fact_index": 2
        }
      ]
    },
    {
      "id": 8,
      "title": "Mobile Developer",
      "org": "Cynoia",
      "bullets": [
        {
          "text": "Developed core modules of the cross-platform app in Flutter, including real-time chat, channel navigation and file previews.",
          "source_fact_index": 0
        },
        {
          "text": "Implemented SQLite caching with optimistic UI updates, maintaining consistent offline-first state during network interruptions.",
          "source_fact_index": 1
        },
        {
          "text": "Resolved legacy navigation and memory leak issues while participating in CI/CD pipelines for Play and TestFlight releases.",
          "source_fact_index": 2
        }
      ]
    },
    {
      "id": 9,
      "title": "End of Studies Project Intern",
      "org": "Cynapsys by Gfi / Inetum",
      "bullets": [
        {
          "text": "Built a Flutter reporting interface connected to backend telemetry services for real-time operational monitoring.",
          "source_fact_index": 0
        },
        {
          "text": "Created event ingestion adapters and visualization widgets displaying live metrics, alerts and incident history.",
          "source_fact_index": 1
        }
      ]
    }
  ],
  "projects": [
    {
      "id": 13,
      "title": "Cross-Platform Enterprise Field Service App",
      "bullets": [
        {
          "text": "Engineered an offline-first app using Drift/SQLite for local persistence with background queue sync upon reconnection.",
          "source_fact_index": 0
        },
        {
          "text": "Implemented a BLoC-based clean architecture separating presentation, domain rules and data repositories.",
          "source_fact_index": 1
        },
        {
          "text": "Integrated camera scanning, PDF generation and biometric authentication via native platform channel plugins.",
          "source_fact_index": 2
        }
      ]
    }
  ],
  "skills": [
    {
      "category": "Mobile & Frontend",
      "skills": [
        "Flutter",
        "Dart",
        "BLoC",
        "Provider",
        "Riverpod",
        "State Management",
        "Clean Architecture",
        "GoRouter"
      ]
    },
    {
      "category": "Backend & APIs",
      "skills": [
        "RESTful APIs",
        "WebSockets",
        "FastAPI",
        "Spring Boot",
        "Firebase Services",
        "Git Version Control",
        "Native Channels",
        "Offline-First Patterns"
      ]
    },
    {
      "category": "Cloud, DevOps & Release",
      "skills": [
        "Docker",
        "GitHub Actions",
        "CI/CD",
        "Fastlane",
        "Google Play Console",
        "App Store Connect",
        "Linux",
        "Debugging & Optimization"
      ]
    }
  ]
}
```

---
