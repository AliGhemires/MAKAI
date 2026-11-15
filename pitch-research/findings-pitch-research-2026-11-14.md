# MAKAI — Findings before the pitch work (14 Nov 2026)

Research brief: read Ralf Boltshauser's OutCube slides and his Hackathon Guidebook, compare them with the Leukerbad situation, and check what hardware juries reward. No business ideas yet; findings only.
Labels: VERIFIED = seen in a source · INFERRED = our reasoning · UNVERIFIED = reported by a research agent, not re-checked · NOT FOUND.

## 1. What Ralf teaches, and where it comes from
- Ralf Boltshauser: ETH Agentic Systems Lab, now building "laufwerk" (slide "currently-building"). Track record from hackathon-guidebook.com, 2023–2025: Start Hack/Syngenta (winner), BaselHack (2× winner), ETH Agentic Systems Hack (winner), IBM Bobathon (winner), Q-Summit (winner), Moin Hack (2nd), ETH AI Hack (2nd). **All are software or business-case hackathons. None is a hardware build.** (VERIFIED)
- The deck is written for InCube (ETH Entrepreneur Club): 5 days of work and a 3-minute pitch. InCube criteria weights: Problem/need/idea 20%, Prototype 15%, Business model 20%, Innovation 30%, Pitch quality 15%. The InCube 2025 jury was VCs and serial founders (Antler, founders). (VERIFIED, slides)
- Core ideas from the slides:
  - **Misalignment.** Hackathons attract builders, but a short pitch decides the result. Only 30–50% of what you say gets understood.
  - **Emotion first.** "They buy with emotion but justify with logic." Making a show helps (costumes on stage photos).
  - **Question the brief.** Three levels of a case: idea-led, grounded in reality (the minimum), and unique insight from experts (aim for this). Example: the Mars greenhouse moved from calories to meal fatigue after expert calls.
  - **Business case.** Process: scope the biggest problem → the bottleneck → what tech can change → a solution people use. Use a Hackathon Canvas with 16 boxes and a value-proposition sentence: For [customer] who struggle with [problem], [solution] enables [outcome], improving [KPI] from [baseline] to [result]; [buyer] pays [price] because [benefit].
  - **Pitch before you build.** "The only competition value of building your product: it moves a jury score on pitch day." Scope the demo around one customer's flow. Non-builders own the case, evidence, numbers, slides and pitch, and push back on over-engineering.
  - **Pitch principles:**
    - one key message per slide
    - written + visual + spoken
    - the headline carries the message
    - several speakers
    - reveal complex ideas (architecture) step by step
    - pitch and product share one brand and one storyline; the demo is embedded in the pitch
  - **"Make the jury want you to win":**
    - costumes and role-play
    - show interviews
    - show user validation and testing
    - a slightly imperfect pitch
    - get to know the jury beforehand
    - mention the jury's feedback by name
    - give them a reason to make you win
  - **Guidebook, extra points:**
    - judges decide on intuition and preference, not strictly on the criteria
    - one person owns "the jury read"
    - if it's not in the demo, it has zero value
    - the demo must be deterministic: a reset script, run → reset → run
    - **if it's not reliable, don't do it live**
    - at least 15 full pitch run-throughs
    - protect the pitcher's sleep
    - ask what happens if you go over time: if the rule is flexible, go slightly over; if strict, train to the cutoff
    - capture proof of interviews (photos, notes)
  - Matt Pocock skills he recommends: /grill-me, /to-spec, /to-tickets, /prototype (the repo is already in MAKAI/skills).

## 2. The Leukerbad situation
- Hosts: Edelweiss Innovation & Intelligence Institute (EIII), Pedro Jinjun Dong, EuroTech Federation, AI Team (EPFL), HerCode, Young Founders Network; TUM-XR co-organises. coprod is a hardware/platform partner, along with many Chinese robot makers (Unitree, AGIBOT, Galbot, Flexiv…). (VERIFIED, luma.com/vj13ns00, luma.com/yo2pk18n)
- Vision: Leukerbad as a "Living Lab for Future Life", "City-as-a-Showroom", robots deployed in hotels, thermal resorts, restaurants and public spaces, working with the local government, and a model to copy in other European towns. (VERIFIED)
- 4 tracks: Autonomous Urban Services · Resilient & Safe City · Sustainable City · Elderly Care & Rehabilitation. CHF 50,000 total pool. Judges are described only as industry, universities, VC and startups. No public criteria or jury names. (VERIFIED / NOT FOUND)
- **Timing conflict:** Luma gives the submission deadline as **16 Nov 13:00**, with pitches and jury evaluation from 13:30 to 17:00. The team docs say deadline 12:00, pitch 13:00. Guidle gives different times again. → **Ask the organisers which is binding.**
- Criteria from the welcome slides (team's notes): technical quality, innovation, real-world value, completeness. Weights unknown.
- Jury affiliations from the welcome slides: Foxglove, Sereact, The Residency, coprod, Industrial Makers, BTU, Latent Engineering → **at least 4 of the 7 are technical** (Foxglove, Sereact, coprod, Latent Eng.), compared with InCube's VC/founder jury.

## 3. Jury profiles (research agent; identification confidence in brackets)
| Profile | Likely rewards | Likely question / risk |
|---|---|---|
| Foxglove (HIGH): robotics data and observability; native LeRobot backend since 0.6; blogged about LeKiwi in Feb 2026 | Logged, replayable failures; data-quality numbers | "Why Rerun? Show me a failure in the logs." |
| Sereact (HIGH): Stuttgart, $116M Series B, Cortex VLA trained on real deployment data; "you can't build real robotics AI in a lab" | Honest success rate on unseen objects; recovery; measurable value | "How many demos, and does it generalize?" |
| coprod (HIGH): Lausanne-area startup making modular robot components; event partner | Clean module interfaces; low cost, reusable | "What changes if you swap the arm?" |
| The Residency (MEDIUM): builder co-living/accelerator; values speed and resilience | Speed of iteration; team commitment | "Will you keep going after Monday?" |
| BTU (LOW–MED, probably BTU Cottbus) | Rigorous evaluation; safety around people | "How did you measure success?" |
| Latent Engineering (LOW): industrial AI startup | Traceability, documentation | "How do you version data and models?" |
| Industrial Makers (UNRESOLVED) | Path to production, unit cost (INFERRED) | ask the organisers who this is |

- VERIFIED by us: LeRobot 0.7.0 accepts `--display_mode=foxglove` in lerobot-teleoperate, lerobot-record and lerobot-rollout (checked in the 0.7.0 wheel).

## 4. Hardware juries vs business juries
Evidence: LeRobot Worldwide Hackathon 2025, Seeed/NVIDIA Embodied AI Hackathon, AMD Open Robotics, Physical AI Hack SF, robo.innovate (TUM), IEEE Spectrum on spotting teleoperation, the TRI paper "Robot Learning as an Empirical Science", the ML6 ACT field report.
- Physical-AI events score measured outcomes: success %, how much of the task is automated, time, integration. Business weight appears mainly where an industry partner set the challenge.
- **Spotting teleoperation is the biggest difference.** Experts look for teleop cues, and fabric/laundry tasks are the classic suspects. Disclosure ("autonomous, 1×") improves trust. (VERIFIED, Spectrum + NeurIPS 2026 study)
- What impresses on imitation-learning demos: success rate with N trials, starting conditions, failure-mode breakdown, unseen objects or positions. ACT is known to struggle outside its training distribution (ML6: 90% in-distribution, no generalization beyond fixed positions).
- Every winner account found had a live-demo problem and recovered with a backup video, a retry or improvisation. No statistics exist on live-demo failure rates.

| Ralf tactic | In a hardware jury |
|---|---|
| Pitch first / storyline | Adapt: the robot doing the task IS the story; show it in the first seconds |
| Build for the score | Transfers strongly; "completeness" rewards the full loop |
| Business case | Adapt (shrink): 1 of 4 criteria; one concrete user + a grounded number |
| Demo scope | Transfers |
| Mock/fake the rest | Backfires if hidden; label scripted parts |
| Emotion + logic | Adapt: emotion from a relatable chore; logic from success rates / N trials |
| Making a show / costumes | Adapt: hardware already draws attention; spend effort on robustness first |
| Architecture reveal | Transfers, worth more here |
| Gaps as "design choices" | Backfires with experts; name the gap with a number |
| Slightly imperfect pitch / jury wants you to win | Adapt: volunteering a limitation reads as confidence |

## 5. Fact check of claims currently in docs/DEMO_PITCH.md
- ❌ **"Robot vacuums stop at a sock"** is outdated. Roborock Saros Z70 (CES 2025) has an arm for socks and slippers, about $2,600 in the US. BUT independent reviews: Gizmodo got 1 paper ball into the box in 40+ tests and 0% on slippers; digitec says socks rarely ended up in the container. → Reframe around the robot vacuum arms performing poorly in reviews, not on vacuums stopping.
- ⚠️ **"~500 CHF of hardware"** holds only for the cheapest DIY base + arm, without Pi or cameras. Honest range: about USD 500–950 depending on vendor and assembly (agent's arithmetic from reseller prices).
- ⚠️ **"Every room starts with picking up what lies around"** has weak support. The only time study found (JIEM 2021, one 4-star hotel in Seville): about 18 min per room; picking up guest clothes is an "extra", all extras adding about 0.67 min per room on average (UNVERIFIED: our check of the landing page did not show these numbers; read the PDF before quoting). No source quantifies decluttering time.
- ✅ **Leukerbad:** 750,878 overnight stays in 2024/25: holiday apartments 349,056, hotels 191,407, packages 170,695 (My Leukerbad annual report). → Holiday apartments ≈ 46% of nights, hotels ≈ 25% (arithmetic). Bed and hotel counts NOT FOUND.
- ✅ **Staff shortage:** Valais expected a 5–10% skilled-staff gap for 2025/26 (Walliser Hotelier-Verein via Blick, Oct 2025); 80% of Swiss hotels report acute shortage (NZZaS 2024, secondary). Housekeeping-specific Swiss data is old (2021). L-GAV minimum from summer 2026: CHF 3,713/month (category Ia).
- Context: 32.7M home cleaning robots shipped worldwide in 2025 (IDC). TidyBot (2023, Princeton/Stanford) put away 85% of objects in real tests. Home tidying robots (1X NEO, Weave Isaac, Sunday Memo) rely partly on remote teleoperation or are not shipping in Europe.
- Falls: Switzerland ≈1,700 deaths/yr, 95% retirement age (BFU). No source links falls to floor objects → don't claim it.

## 6. Open uncertainties
- Binding deadline and pitch time (12:00 vs 13:00, Luma vs team docs).
- Real judging weights and jury names (not public; the official site leukerbad-robot-carnival.tech returns 404).
- Identity of Industrial Makers, BTU and Latent Engineering at this event.
- Whether going over time is penalised (Ralf: ask).
- Exact kit cost of OUR robot (check the invoice or the organisers' kit list).
