# MAKAI pitch: final script (Round 1, Mon 16 Nov, 13:00)

**Total: 4:00.** Spoken budget: ~390 words (350 talk at ~131 wpm + ~40 during the demo). "Say it" lines: ~170 words; cues fill the rest.
**Speakers:** M = Mohamed (slides 1–4, 7–9). S2 = [second speaker] (slides 5–6). F = fixer, at the robot, never touches the leader arm.
Say "our robot" (no product name). The 60 socks are **human demonstrations**, never autonomous grasps.

## The through-line (read this first)
- **One question opens and closes the pitch:** "What do sixty socks teach a robot?" → last slide: "To bend down, so cleaners don't have to."
- **Each slide answers the question the last one raised.** Say the bridge out loud when you click:
  why it matters ("every stay ends with a cleaner bending down") → why now ("and it's growing") → does it work ("let me show you") → how ("the hardest moment is the grasp, so only that is learned") → how does it see ("it labels its own data") → how did it learn ("those sixty socks trained six models") → does it hold on the robot ("so does it hold?") → how far can it go ("a new object costs an hour of demos") → how big is it ("Mohamed, how big is this?": up to ~CHF 10M a year on checkout cleans in Leukerbad alone) → who pays (aparthotels and hostels; CHF 100 per robot per month, tested in a 3-month pilot with 10 Leukerbad flats) → who are we → the answer.
- **One image comes back throughout:** the cleaner who bends down. The robot takes the bending down; the cleaner keeps the job.
- Word-for-word version: FULL_script_word_for_word (.md / _v2.pdf).

---

**1 · Hook** | 0:00–0:15 | M
- Mosaic: 60 wrist-camera frames, gripper holding a black sock. Let it sit 2 s.
- These are us guiding the arm: 60 demonstrations, 59 ended with the sock in hand.
> "What do 60 socks teach a robot? Each photo is one of us guiding its arm. That is how it learns to grasp."

**2 · Leukerbad** | 0:15–0:35 | M
- 750,878 stays 2024/25; 46% holiday apartments. Checkout clean CHF 80–100.
- Sunday's Smart City Forum, Valais Chamber of Commerce: peripheral Alpine regions most exposed to labour shortfall.
> "In Leukerbad, almost half of all nights are in holiday flats, and every checkout clean costs 80 to 100 francs."

**3 · Checkout chores are moving to the cleaner. No robot on sale can take them yet.** | 0:35–0:55 | M
- From 20 Nov (bookings from that date), in four days: Airbnb hosts can no longer require chores like stripping beds or taking trash out.
- Local terms already ask guests to sort linen and recycling; now it lands on the cleaner.
- Gizmodo's review of the Roborock Saros Z70 ($2,600, vacuum with an arm): paper ball in its box once in 40+ tests, 0% on slippers.
> "In four days, Airbnb hosts can no longer ask guests to do these chores. Someone still has to bend down."

**4 · Live demo** | 0:55–2:15 (80 s) | M, F at robot
- Say first: "Autonomous, 1× speed, nobody touches the controller." Then mostly silence.
- Name each step *as it happens*, never before: rows · sees · picks · laundry or not · bin · back to its row.
> "It sweeps like a vacuum, in rows. It sees something… picks it… decides… drops it… and goes back to its row."

**5 · How it works: only the grasp is learned; the rest is geometry** | 2:15–2:55 | S2
- Answer the hook: 59 demos teach one grasp, not a whole room. So we learn only the grasp.
- See: detector auto-labelled on the robot's own camera. Never-seen robot images: cans 14/14, socks 10/12, empty floor 14/14, no false detection.
- Go: no depth sensor. Floor geometry + wheels; bin marker re-anchors. Sim, 4% wheel slip: 4/4 and back within 3 cm, vs 2/4 then failure without marker.
- Grasp: ACT, one model per object, 59 sock + 68 can demos, overnight on a GPU cluster. Replay within 1.5° / 1.3°. Drop: scripted. LeKiwi + SO-101, [CHF __].
> "Sixty socks are enough to learn one grasp, not a whole room. So only the grasp is learned. The rest is geometry we can test."

**6 · What we measured, including what fails** | 2:55–3:20 | S2
- **(a) Measured (team trials, 15 Nov): limit tests 8/10 sock, 7/10 can; normal placements [__/10].** Earlier template: "On the real robot, the grasp worked [x] out of [N] on [socks/cans], autonomous, 1× speed. Every attempt counted."
- **(b) Not yet scored:** "Our first grasp trials on the robot held almost every time. The scored ten-in-a-row is the number we're still measuring." Then: one camera reads a can at 57.5 cm as 57.3 cm; in simulation both modes deliver 4/4 with slipping wheels.
- Both: no obstacle avoidance · two object types · small, light items · one model per object · on the real robot, images lag up to 2.5 s (being fixed).
- Same calm voice, no apology.

**7 · A checkout clean is already priced at CHF 80–100. We take the bending-down part.** | 3:20–3:40 | M
- Aparthotel and hostel operators pay. Robot-as-a-service, [CHF __/robot/month].
- First step: 3-month pilot in Leukerbad (track prize: EIII robotics lab).
> "The robot helps the cleaner. It takes the bending down, not the job."

**8 · Team** | 3:40–3:47 | M
> "We are five students [check: universities]: [names]."

**9 · Close** | 3:47–4:00 | M
- Why us: full loop shown, numbers with N, limits named, pilot ready here.
- Ask, then stop talking.
> "Sixty socks taught it to grasp. Give us three months in Leukerbad, and we bring back the number that counts: [x] out of [N] in real flats. We are MAKAI."

---

## 5-minute final (15:00): +60 s, no new facts
- Demo +20 s: let a second object run, so both bins are seen.
- Slide 2 +10 s: Valais hoteliers expected 5–10% of positions unfilled for winter 2025/26.
- Slide 5 +15 s: the free label (object on first frame, gone on last); GPU cluster 11× faster than a laptop.
- Slide 7 +15 s: Forum line "jobs force-multiplied, not destroyed": this is the bending-down part.

## If things go wrong
| | |
|---|---|
| Demo fails once | F resets silently. M: "Let's run it again." If <40 s left, video. |
| Fails twice | Video, no comment on the failure: "Here is a recorded run, autonomous, 1× speed." [confirm true for the video] |
| Time overrun | Cut slide 3 to the Airbnb line, then replay degrees. Never cut slide 6 limits or the ask. |
| Blank mind | Read the slide headline aloud. It is the message. Go to the next cue. |
| Hostile question | Number with N, or "we haven't measured that", next step. Stop. |
| Mic issue | Don't wait. Step forward, speak louder; S2 hands over the spare mic. |

## Top 10 Q&A (one breath, then stop)
1. **Grasp success rate?** (a) "[x]/[N], autonomous, 1× speed." (b) "Not measured yet. Offline: within 1.5° and 1.3° of the pilot. A 10-trial test is next."
2. **Why ACT, where does it run?** "59 and 68 demos, one night of GPU: ACT fits that budget. It runs on the laptop, 29–30 commands per second; the Pi on the robot handles motors and cameras."
3. **Generalise or memorise?** "Two object types, one model each; a new object means new demos."
4. **Why no depth camera?** "Floor geometry gives distance; the marker re-anchors. The cost: no obstacle avoidance, where depth would earn its place."
5. **Sim-to-real / what changes for a real hotel?** "Navigation is proven in simulation only: 4/4, within 3 cm. Next: real-floor test, obstacle avoidance, more object types."
6. **How do you find failures?** "Demos are recorded; 59 of 60 sock demos ended in hand, we trained on those. The pilot logs every pick attempt with video."
7. **Help or replace cleaners?** "It takes the bending-down part, not the job. The cleaner empties the bins, so a person sees every item."
8. **Who did you talk to?** "No customer interviews yet: a gap. We used rental terms, Airbnb's rule and Sunday's Forum. Talking to cleaning staff is pilot step one."
9. **Who pays, payback, unit cost?** "A checkout clean is already priced at CHF 80–100. Payback needs minutes saved: the pilot measures that. Parts: [CHF __]; no volume quote."
10. **Safety and privacy?** "Empty flat after checkout only; no obstacle avoidance, so never near people. Privacy: [what is stored, how long, who sees it]."

**Extra facts for Q&A, checked against the team's own logs (docs/EXPLORATIONS.md, docs/REGISTRY.md) or verified sources:**
- Black images instead of camera images: error jumps from 5.3° to 33.3°, so the model really uses its cameras. Swapping the two cameras: no effect.
- 3 failed demonstrations removed in total: 1 of 60 socks, 2 of 70 cans (so 59 and 68 used). No conflict.
- Four sock trainings compared (reference, random lighting, 50-action chunks, wrist camera only): same learning speed. One model for both objects failed (LeRobot's merge broke the video alignment, caught before training), hence one model per object.
- First detector, trained on phone photos: found the can in only 4 of 14 robot images → v2 labels itself on the robot's own camera.
- Radio link: two camera streams = 61 Mbit/s; Pi's own Wi-Fi 6 ms vs 38–143 ms through a phone hotspot.
- RoboHack 2026 winners (peg insertion, fixed arm, ACT default settings, 50 demos): 26% on-robot success; they still won with a full loop and a clear pitch (github.com/Encrux/robohack26).
- US hotel study (Am J Ind Med 2010): housekeepers 7.9 injuries per 100 worker-years vs 5.2 for all hotel workers (verified). Use only if asked about the cleaners' work, framed as US data.
- Valais minimum wage for routine cleaning 2026: CHF 20.72/h (Unia Valais). Not verified by us: check before quoting.

---

## Deck v3 timing (13 slides, 5:00) — use this when presenting the expanded deck
| # | Slide | Window | Cue |
|---|---|---|---|
| 1 | Hook (60 socks) | 0:00–0:10 | "What do 60 socks teach a robot? Each photo is one of us guiding its arm." |
| 2 | Why it matters · Leukerbad | 0:10–0:30 | 46% holiday flats, CHF 80–100 per checkout, Sunday's Forum |
| 3 | Why now | 0:30–0:50 | Airbnb from 20 Nov; best robot: 1 in 40+ |
| 4 | Live demo | 0:50–2:05 | "Autonomous, 1× speed, nobody touches the controller." |
| 5 | Architecture | 2:05–2:30 | Robot relays, laptop thinks; see/plan/move/grasp; only grasp learned; simulated twins |
| 6 | Perception | 2:30–2:45 | 4 methods; robot labels its own data; 14/14, 10/12 |
| 7 | Learning | 2:45–3:10 | 6 trainings, one night; replay picks the winner: 1.5° / 1.3°; one model per object |
| 8 | Compute and checks | 3:10–3:25 | 4 h 50 vs 53 h; blind it → 33°: it uses its eyes |
| 9 | Results | 3:25–3:45 | on-robot rate (or "not yet"), marker 2/4 → 4/4 in sim, limits |
| 10 | Scaling | 3:45–4:05 | ≈1 h demos + 0 labels + one night per new object; pilot → scale |
| 11 | Business | 4:05–4:25 | hosts pay CHF 80–100; robot as a service; 3-month pilot |
| 12 | Team | 4:25–4:32 | one sentence |
| 13 | Close | 4:32–4:45 | "We are MAKAI. Give us three months…" (15 s buffer) |

**For the 4-minute round 1:** keep all slides but only flash 6 (Perception) and 8 (Compute) with one sentence each, cut the demo narration to the essentials, and shorten Why now to the Airbnb line.


## Market and price (added Sun 15, evening)
- **Market (slide 11):** Leukerbad alone: up to ~106,000 holiday-flat checkouts a year (349,056 nights ÷ 3.3-night average stay) × CHF 80–100 = CHF 8.5–10.6M a year spent on checkout cleans. An upper bound, and cleaning spend, not our revenue. Switzerland: 7.4M nights in managed holiday flats and 43.9M hotel nights in 2025 (BFS).
- **Price:** CHF 100 per robot per month, a hypothesis the pilot tests. Parts (≈ USD 500–950) pay back in about 5–9 months.
- **Pilot:** 3 months; EIII lab, then 10 Leukerbad units, measuring minutes saved per checkout. No host has agreed yet: say "we want to run".
