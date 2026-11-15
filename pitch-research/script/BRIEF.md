# Pitch brief — team MAKAI, Leukerbad Robotics Carnival Hack 2026 (Track 1: Autonomous Urban Services)

## Format and stakes
- Round 1: Mon 16 Nov 13:00, **4 min pitch + 2 min questions**, one winner per track. Final (if we win the track): 15:00, **5 min + 3 min**. Deadline for submission 12:00.
- Scoring: technical quality, innovation, real-world value, completeness (weights unknown).
- Speaker: Mohamed (main), second speaker TBD. A "fixer" stands by the robot and never touches the leader arm.
- Language: English. Jurors are international, mostly technical. Speaking pace: plan **~130–140 words per minute** of talk (non-native speakers, nervous); the live demo segment has very few words.
- The script must be **bullet points / cues first**, not prose to memorize. Then an optional "say it like this" line per beat.

## Team and naming
- **MAKAI is the TEAM name. The product has no name yet.** Refer to "our robot" or "the robot". Do not invent a product name.
- Team: 5 students (names TBD on slides).

## The jury (public professional profiles)
- Damien LaRocque (Sereact, robotics engineer, trained/deployed ACT and π0.5, LeRobot contributor; knows ArUco and homography): wants success rate x/N, number of demos, generalisation, why ACT, where the policy runs.
- Raphael Levy (Foxglove, Europe go-to-market): logs, replay of failures, fleet monitoring.
- Loïc Delineau (coprod CEO, EPFL startup, modular robot hardware): integration pain, unit cost, what to change for a real hotel.
- Adrián Sager (Latent Engineering CTO; ExoMars rover simulation): traceability, what breaks when you change a part, sim-to-real.
- Tom Love (Latent Engineering): similar.
- Dr. Lora Koycheva (anthropologist of robotics, BTU Cottbus; "Robots, actually!"): who did you talk to, does it help or replace workers, people around the robot. Dislikes hype.
- Roland Graser (The Residency, founder selection): is this a company, who pays first, speed of iteration.
- Thomas J. Dittler (Industrial Makers; ex-Boeing/Roland Berger; investor): unit cost at scale, wear, payback.

## Slide outline the script must follow (v2)
1. **Hook** (shown before we start): full-bleed photo, a holiday-flat floor right after checkout (towels, a sock, a crushed can). No title. Optional line: "Who bends down for this?"
2. **Leukerbad** — 750,878 overnight stays in 2024/25; 46% in holiday apartments (biggest segment); a checkout clean of a Leukerbad holiday flat is billed CHF 80–100 (2026/27 price list). At this morning's Smart City Forum, the Valais Chamber of Commerce said peripheral Alpine regions are most exposed to labour shortfall and framed AI as "jobs force-multiplied, not destroyed". Valais hoteliers expected 5–10% of positions unfilled for winter 2025/26.
3. **Why now (local, little text)** — Local rental terms already ask guests to put linen with the towels and separate recycling from residual waste (Ferien-Vacances GmbH terms). From 20 Nov 2026 (bookings from that date), Airbnb no longer lets hosts require checkout chores such as stripping beds or taking trash out → the work lands on the cleaner. The best robot on sale (Roborock Saros Z70, $2,600 vacuum with an arm): in Gizmodo's review it put a paper ball in its box once in 40+ tests and 0% on slippers.
4. **Live demo** — the robot sweeps the room like a vacuum, in rows, without turning; spots an object; picks it; decides laundry or not; drops it in the right marked bin; returns to its row. Autonomous, 1× speed. Fallback video if the live run fails twice (switch without commenting on the failure).
5. **How it works** — "Only the grasp is learned; the rest is geometry." (1) See: detector trained on our own images, then auto-labelled on the robot's own camera (object present on first frame, gone on last frame = free label): on never-seen robot images, cans 14/14, socks 10/12, empty floor 14/14 with no false detection. (2) Go: no depth sensor, floor geometry + wheel odometry; the printed marker on the bin is the only fixed point and re-anchors the map at every visit: in simulation with 4% wheel slip, 4/4 objects and back within 3 cm, versus 2/4 then failure without the marker. (3) Grasp: ACT imitation-learning policy, one model per object, trained on 59 sock and 68 can demonstrations, overnight on a university GPU cluster (11× faster than a laptop). Replay check: the final models reproduce the human pilot's commands within 1.5° (sock) and 1.3° (can) on recorded episodes. (4) Drop: scripted, bins found by printed markers. Hardware: open-source LeKiwi base + SO-101 arm (Hugging Face LeRobot), cost [CHF __].
6. **Results / honest limits** — On-robot grasp success rate: [__ / 10] — NOT YET MEASURED at time of writing; keep a placeholder and a version of the line for "if we have it" and "if we don't". Known limits: no obstacle avoidance, two object types, small light items, one model per object, navigation not yet validated on the real floor at time of writing.
7. **Business model (one lean slide)** — Who pays: aparthotel and hostel operators who already pay CHF 80–100 per checkout clean. Model: robot-as-a-service, [CHF __ per robot per month] (placeholder, not decided). First step: 3-month pilot in Leukerbad (the track prize includes 3 months at the EIII robotics lab). Robot helps cleaning staff (takes the bending-down part); it does not replace them.
8. **Team** — photos and names.
9. **Closing** — full-bleed team photo, "We are MAKAI." + one-line ask.

## Rules for content
- Use ONLY the facts above. Placeholders in [brackets] for anything unknown. Never invent numbers, quotes or customer conversations. We did NOT interview any customer.
- Avoid: "robots will replace", hype ("revolutionary", "AI that understands"), the word "simply". Name limits ourselves.
- Ralf Boltshauser's principles (hackathon coach): emotion first then logic; one message per slide; headline = message; persona storytelling; show the robot early; a limit stated is better than a limit discovered; "give the jury a reason to make you win".
- Hardware-jury specifics: say "autonomous, 1× speed, nobody touches the controller" explicitly; numbers with N; no cherry-picking.
