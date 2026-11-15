# Q&A bank: MAKAI (2 min round 1, 3 min final)

Rules of use: answer in one breath, give the number with its N, stop. **(P)** = contains a placeholder: fill it before Monday 12:00 or use the fallback line.

## Damien LaRocque (Sereact)

**Q: What is the on-robot grasp success rate?** **(P)**
- If measured: "[__] out of [__] grasps, autonomous, 1× speed. For reference, the RoboHack 2026 winners reported 26% on-robot with the same method: ACT, default settings, 50 demos."
- If not: "We don't have an x/N we'd defend yet. Offline, the models reproduce the pilot within 1.5° (sock) and 1.3° (can). A 10-trial test is next."

**Q: Why ACT, and where does it run?**
"59 sock and 68 can demos, one night of GPU: ACT fit that budget. It runs on the laptop at 29–30 commands/s, linked to the Pi 5 on the base by direct Wi-Fi, 6 ms."

**Q: Does it generalise, or memorise?**
"Black images push its error from 5.3° to 33.3°, so it really uses the cameras. But we have two object types, one model each; a new object means new demos."

## Raphael Levy (Foxglove)

**Q: How do you find and replay failures?**
"Every demonstration is recorded with video. We replay recorded episodes to check the models: within 1.5° and 1.3° of the pilot. The 3 failed grasps were removed before training."

**Q: What about fleet monitoring?**
"Not built: one robot today. The pilot's first need is a log of every pick attempt with its video, so the success rate is measured, not claimed."

## Loïc Delineau (coprod)

**Q: What was the hardest integration problem?**
"The network. Through a phone hotspot the link took 38–143 ms; a direct Wi-Fi link gives 6 ms. Two camera streams weigh 61 Mbit/s, so networking is a design constraint."

**Q: What must change for a real hotel?** **(P)**
"Obstacle avoidance, which we don't have. Navigation validated on a real floor, not done yet. More object types. Hardware is the open-source LeKiwi base and SO-101 arm, [CHF __] today."

## Adrián Sager (Latent Engineering)

**Q: What breaks when you change a part?**
"Changing the camera broke perception: a detector trained on phone photos found the can in 4 of 14 robot images. We auto-labelled on the robot's own camera: 14/14 cans."

**Q: How does sim transfer to real?** **(P: update if the real-floor test happened)**
"Navigation is proven in simulation only: with 4% wheel slip, 4/4 objects and back within 3 cm thanks to the marker, versus 2/4 without. Real-floor validation is next."

## Tom Love (Latent Engineering)

**Q: How do you know a model change is an improvement?**
"We compared four sock trainings: reference, random lighting, 50-action chunks, wrist camera only. All learned at the same rate, so offline curves can't separate them; on-robot trials will."

**Q: Why one model per object?**
"We tried merging both datasets. LeRobot's merge tool produced videos misaligned with episodes; we caught it before training. So one model per object, and the detector says which to run."

## Dr. Lora Koycheva (BTU Cottbus)

**Q: Who did you talk to?**
"No customer interviews yet: that's a gap. We used local rental terms, Airbnb's rule change and this morning's Chamber of Commerce talk. Talking to Leukerbad cleaning staff comes first in the pilot."

**Q: Does it help or replace cleaners?**
"It takes the bending-down part, not the job. Data we found, not Leukerbad data: a US hotel study counted 7.9 injuries per 100 worker-years for housekeepers versus 5.2 for all hotel workers."

**Q: What about people around the robot?**
"It has no obstacle avoidance today, so it works only in an empty flat after checkout, which is our use case. Working around people waits until avoidance exists."

## Roland Graser (The Residency)

**Q: Who pays first?** **(P)**
"Aparthotel and hostel operators; a checkout clean is already priced at CHF 80–100 here. Robot-as-a-service at [CHF __ per robot per month], starting with a 3-month pilot in Leukerbad."

**Q: Is this a company or a weekend project?** **(P)**
"Look at the iteration speed: detector v1 failed on robot images, v2 was auto-labelled on the robot's own episodes and found 14/14 cans. [Team commitment after Monday]."

## Thomas J. Dittler (Industrial Makers)

**Q: What is the payback?** **(P)**
"We can't compute it yet: we don't know the minutes saved per clean. The pilot measures that against the CHF 80–100 billed per clean. [Routine-cleaning minimum wage Valais: CHF 20.72/h. Check before quoting.]"

**Q: What about wear?**
"No wear data yet: the arm has run for a weekend, not a season. The pilot will log operating hours and failures per part."

## Six hard generic questions

**Q: Why not a VLA like SmolVLA?**
"With 59 demos and one night of GPU, we chose a policy that fits our data and runs on a laptop at 29–30 commands/s. A VLA is worth comparing once we have an on-robot baseline."

**Q: Why no depth camera?**
"Distance comes from floor geometry; the printed marker on the bin re-anchors position at every visit. The limit: no obstacle avoidance. That is where a depth sensor would earn its place."

**Q: What about safety around guests and children?** **(P)**
"It is built for the empty flat after checkout and has no obstacle avoidance today, so it must not run near guests or children. Before any pilot: [obstacle detection and stop measures]."

**Q: Cameras in rooms: what about privacy?** **(P)**
"It works after checkout, in an empty flat; the policy runs on a local laptop over direct Wi-Fi. A pilot needs a written rule: [what is stored, for how long, who sees it]."

**Q: What if a guest's belonging is valuable or personal?**
"It targets only two trained object types; on empty floor, zero false detections in 14 images. Items go to marked bins, not the trash, and the cleaner empties them: a person sees every item."

**Q: What is the unit cost at 1,000 units?** **(P)**
"The prototype is the open-source LeKiwi and SO-101 at [CHF __]. We have no volume quote for 1,000 units; [estimate, or: a costed bill of materials is a pilot deliverable]."

## Three rules when we can't answer

1. **Say "we haven't measured that"**, give the closest number we do have with its N, then the next step. Never estimate a number on stage.
2. **One speaker per question, one or two sentences, then stop.** If it isn't your part, pass to the teammate who owns it in five words; no group debate.
3. **Never defend with hype.** Name the limit before the juror does ("no obstacle avoidance", "two object types") and offer the data or video after the session.
