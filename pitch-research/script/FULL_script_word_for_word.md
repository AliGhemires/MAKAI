# MAKAI pitch: full word-for-word script (backup)

**5:00 version** (final): ~537 spoken words, ends at 4:35, leaving ~30 s of slack for pauses and the demo. **4:00 version** (round 1): skip every line marked ✂, ~433 words.
Read it to learn the flow, then speak from the cues in FINAL_script.md. Pace: slow, about 130 words a minute. Pause after every number.

**The through-line:** one question opens and closes the pitch (“What do sixty socks teach a robot?” → “To bend down, so cleaners don’t have to.”). Every slide answers the question the previous one raised: why does it matter → why now → does it work → how → how do we know → how far can it go → how big is it → who pays → who are we. The image that comes back throughout: the cleaner who bends down.

## 1 · Hook · 60 socks  (0:00–0:15) · Mohamed
*Slide already on screen. Stand still, let it sit two seconds. Ask the question slowly.*

- What do sixty socks teach a robot?
- Each photo is one of us guiding its arm. By the end, you’ll know what they taught it.

## 2 · Why it matters · Leukerbad  (0:15–0:37) · Mohamed
*Click. Bridge: from the sock to the room it was left in.*

- Leukerbad lives on short stays: almost half of all nights are in holiday flats.
- Every stay ends the same way: a cleaner walks in and first bends down for what guests left on the floor.
- ✂ A final clean here is priced at eighty to a hundred francs.
- ✂ At Sunday’s Forum, the Valais Chamber of Commerce named the real risk for the Alps: not enough people to do this work.

## 3 · Why it matters · Why now  (0:37–0:55) · Mohamed
*Click. Bridge: the problem is about to grow.*

- And it’s growing: for Airbnb bookings from this Friday, guests no longer have to strip beds or take out the trash.
- Can a robot help? The best one on sale got a paper ball into its box once in more than forty tests.
- So we built our own. Let me show you.

## 4 · Live demo  (0:55–2:10) · Mohamed + fixer
*Walk to the mat. Start the mission before 1:15. Then speak only when something happens.*

- Everything now is autonomous, at normal speed. Nobody touches the controller.
- ✂ On the screen: the map, its path, and what it sees.
- It sweeps in rows, like a vacuum… it sees something… it bends down… picks it… laundry or not?… right bin… and back to its row.
- (If a run fails twice: “Here is a recorded run, autonomous, normal speed.” Play the video. No comment on the failure.)
- Handover: “[Speaker 2] built how it works.”

## 5 · Execution · Architecture  (2:10–2:30) · [Speaker 2]
*Back to the slides. One click per block. Bridge: from what you saw to how it works.*

- The hardest moment in that demo is when it bends down and grasps. So that is the only thing we let it learn.
- Seeing, planning and moving are geometry we can test, each with a simulated twin.

## 6 · Execution · Perception  (2:30–2:45) · [Speaker 2]
*Click. Bridge: to learn, it first has to see.*

- ✂ To grasp, it first has to see. Ready-made detectors failed on our robot’s camera.
- So it labels its own data: in each demo, the sock is there at the start and gone at the end. A free label.
- Fourteen of fourteen cans, ten of twelve socks, no false alarms.

## 7 · Execution · Learning  (2:45–3:05) · [Speaker 2]
*Click. Bridge: back to the sixty socks.*

- Then the grasp itself. Those sixty socks trained six models in one night on DTU’s cluster.
- We replay each one against the human pilot, and the simplest wins: within one and a half degrees.

## 8 · Execution · Compute and checks  (3:05–3:15) · [Speaker 2]
*Click. Optional in round 1.*

- ✂ Under five hours instead of fifty-three on a laptop. And when we blind it, it barely moves: it really uses its eyes.

## 9 · Execution · Results  (3:15–3:35) · [Speaker 2]
*Click. Bridge: “but does it hold on the real robot?” Same calm voice whatever the answer.*

- So does it hold on the real robot?
- In our limit tests, the grasp worked eight out of ten for the sock and seven out of ten for the can. [Normal placements: give the score.]
- Limits: no obstacle avoidance yet, two object types, and image lag on the robot that we’re fixing.

## 10 · Execution · Scaling  (3:35–3:50) · [Speaker 2]
*Click. Bridge: from one sock to many objects.*

- What makes it a product: a new object costs an hour of demos, zero hand-drawn labels, and one night of GPU.
- ✂ Same robot, already two jobs: a room, and a street.
- Handover: “Mohamed, how big is this?”

## 11 · Market  (3:50–4:02) · Mohamed
*Click. Bridge: from one robot to the market.*

- Leukerbad alone spends up to about ten million francs a year on checkout cleans.
- ✂ Switzerland has seven million nights in holiday flats, and forty-four million in hotels.
- We start here.

## 12 · Business  (4:02–4:17) · Mohamed
*Click. Bridge: back to the cleaner.*

- Who pays? Aparthotels and hostels.
- We rent the robot at a hundred francs a month, and test that price in a three-month pilot with ten Leukerbad flats.
- It takes the bending down. The cleaner keeps the job.

## 13 · Team  (4:17–4:22) · Mohamed
*Click. Don’t read the names.*

- Five students. Everything you saw was built this weekend.

## 14 · Close  (4:22–4:35) · Mohamed
*Click. Answer the opening question. Slow down, then stop talking.*

- So, what do sixty socks teach a robot?
- To bend down, so cleaners don’t have to.
- Give us three months, and we’ll prove it in Leukerbad’s flats. We are MAKAI. Thank you.

## 4:00 timing (round 1)
Hook 0:00–0:12 · Leukerbad 0:12–0:27 · Why now 0:27–0:43 · Demo 0:43–1:43 (keep it to 60 s) · Architecture 1:43–2:00 · Perception 2:00–2:12 · Learning 2:12–2:28 · Compute: click through · Results 2:28–2:45 · Scaling 2:45–2:55 · Market 2:55–3:05 · Business 3:05–3:20 · Team 3:20–3:25 · Close 3:25–3:38 (20 s buffer).
