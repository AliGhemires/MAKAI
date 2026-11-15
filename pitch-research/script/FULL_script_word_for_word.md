# MAKAI pitch: full word-for-word script (backup)

**5:00 version** (final): ~463 spoken words, ends at 4:26, leaving ~30 s of slack for pauses and the demo. **4:00 version** (round 1): skip every line marked ✂, ~372 words.
Read it to learn the flow, then speak from the cues in FINAL_script.md. Pace: slow, about 130 words a minute. Pause after every number.

## 1 · Hook · 60 socks  (0:00–0:12) · Mohamed
*Slide already on screen. Stand still, let it sit two seconds.*

- What do sixty socks teach a robot?
- Each photo is one of us guiding its arm. That is how it learns to grasp.

## 2 · Why it matters · Leukerbad  (0:12–0:30) · Mohamed
*Click to slide 2.*

- Leukerbad lives on short stays, almost half of them in holiday flats.
- Every checkout needs a cleaner, and a final clean here is priced at eighty to a hundred francs.
- ✂ At Sunday’s Forum, the Valais Chamber of Commerce named the real risk: not enough people.

## 3 · Why it matters · Why now  (0:30–0:48) · Mohamed
*Click.*

- For Airbnb bookings from this Friday, hosts can no longer require guests to strip beds or take the trash out. It lands on the cleaner.
- The best robot on sale got a paper ball into its box once in more than forty tests.
- So let us show you ours.

## 4 · Live demo  (0:48–2:03) · Mohamed + fixer
*Walk to the mat. Start the mission before 1:15. Then speak only when something happens.*

- Everything now is autonomous, at normal speed. Nobody touches the controller.
- On the screen: the map, its path, and what it sees.
- It sweeps in rows, like a vacuum… it sees an object… picks it… laundry or not?… right bin… back to its row.
- (If a run fails twice: “Here is a recorded run, autonomous, normal speed.” Play the video. No comment on the failure.)

## 5 · Execution · Architecture  (2:03–2:25) · [Speaker 2]
*Back to the slides. One click per block.*

- The robot only relays motors and cameras. All the thinking runs on the laptop, in four blocks: see, plan, move, grasp.
- Only the grasp is learned. The rest is geometry we can test, and every block has a simulated twin.

## 6 · Execution · Perception  (2:25–2:40) · [Speaker 2]
*Click.*

- ✂ Ready-made detectors failed on our robot’s camera.
- So the robot labels its own data: the object is there at the start of each demo and gone at the end. Free labels.
- Fourteen of fourteen cans, ten of twelve socks, no false alarms.

## 7 · Execution · Learning  (2:40–3:02) · [Speaker 2]
*Click. Point at the curves, then at the table.*

- Six trainings ran in one night on DTU’s cluster.
- ✂ We replay recorded episodes and compare each model with the human pilot.
- The simplest one wins: within one and a half degrees for the sock, one point three for the can.

## 8 · Execution · Compute and checks  (3:02–3:15) · [Speaker 2]
*Click. Optional in round 1.*

- ✂ Under five hours on the cluster, instead of fifty-three on a laptop.
- ✂ Give it black images and it barely moves: it really uses its eyes.

## 9 · Execution · Results  (3:15–3:35) · [Speaker 2]
*Click. Same calm voice whatever the numbers are.*

- IF MEASURED: On the real robot, the grasp worked [x] out of [N] for the sock, [y] out of [N] for the can.
- IF NOT YET: The one number we don’t have yet is the success rate on the real robot, so we don’t show one.
- ✂ In simulation, the marker on the bin takes us from two objects out of four to four out of four.
- Limits: no obstacle avoidance yet, two object types, small items.

## 10 · Execution · Scaling  (3:35–3:52) · [Speaker 2]
*Click.*

- A new object costs an hour of demos, zero hand-drawn labels, and one night of GPU.
- ✂ Then a pilot on real floors, and one model for many objects.

## 11 · Business  (3:52–4:10) · Mohamed
*Click.*

- Our customers are aparthotels and hostels: a checkout clean is already priced at eighty to a hundred francs.
- We rent the robot per month and start with a three-month pilot here.
- It takes the bending-down part, not the job.

## 12 · Team  (4:10–4:16) · Mohamed
*Click. Don’t read the names.*

- Five students. This weekend we built, trained and tested all of this.

## 13 · Close  (4:16–4:26) · Mohamed
*Click. Slow down. Then stop talking.*

- Sixty socks taught it to grasp. Give us three months, and we’ll run the pilot here in Leukerbad.
- We are MAKAI. Thank you.

## 4:00 timing (round 1)
Hook 0:00–0:10 · Leukerbad 0:10–0:22 · Why now 0:22–0:38 · Demo 0:38–1:53 · Architecture 1:53–2:12 · Perception 2:12–2:22 · Learning 2:22–2:37 · Compute: skip, click through · Results 2:37–2:52 · Scaling 2:52–3:02 · Business 3:02–3:20 · Team 3:20–3:25 · Close 3:25–3:35 (25 s buffer).
