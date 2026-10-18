Call Shield: demo and testing pack
October 17, 2026
Working name: Call Shield. The name ideas below are suggestions for the team to choose from.
Demo scripts
These are original fictional scripts based on documented scam patterns, not transcripts of actual calls. Generate the three AI examples with an authorized synthetic voice or a consenting team member's voice. Record the fourth with a human reader. Keep the headings and notes out of the audio. At about 140–160 words per minute, aim for 45–60 seconds of speech; record the actual duration. Never give real account details or act on the requests in these fixtures.
D1: Fake grandchild emergency — synthetic voice
Grandma, it's Alex. Can you hear me? I know I sound strange, but I'm really shaken up. I was in an accident on my way home, and now someone says I have to pay before I can leave. I'm okay, but I don't know what to do. Please don't call Mom yet. I don't want everyone getting worried before I can explain what happened. They said I need fifteen hundred dollars today, and you're the only person I could think of calling. I need you to send the money right away. Can you stay on the phone with me while you get it ready? I know this is a lot to ask. Please just help me take care of it now, and I'll explain everything when I'm home.
Pattern source: FTC, “Scammers Use Fake Emergencies To Steal Your Money.” Family impersonation, an urgent payment request, and secrecy. https://consumer.ftc.gov/articles/scammers-use-fake-emergencies-steal-your-money
D2: Fake parent in trouble — synthetic voice
Hey, it's Dad. Listen, I need your help with something, and I need you to stay calm. I'm using another phone because mine isn't working. There's a problem here, and I've been told that a payment needs to be made before I can get out of it. They want two thousand dollars today. I know that sounds strange. I wouldn't be asking if I had another option. Please don't call the rest of the family right now. It will only make this harder to sort out. Can you get the money together and stay on this call? There's someone here waiting for an answer. I need you to trust me for a minute. Once this is over, I'll call you again from my own phone and explain what happened.
Pattern source: FBI/IC3, “Criminals Use Generative Artificial Intelligence to Facilitate Financial Fraud,” December 3, 2024. A generated relative's voice is used to support a fictional crisis and payment demand. https://www.ic3.gov/psa/2024/psa241203
D3: Fake manager requesting payment — synthetic voice
Hi, this is Morgan. I'm heading into a meeting, so I only have a minute. There is a supplier payment that needs to go through before the end of the day, and I need you to handle it for me. The amount is twenty-four hundred dollars. This is separate from the invoices you normally process, so don't wait for the usual approval email. I have already approved it. Please keep this between us until the agreement is announced. If you ask the whole office about it, we're going to miss the deadline. Can you start the transfer now and tell me when it's done? I need an answer before I go into this meeting. You know my voice, and I wouldn't ask you to do this unless it mattered.
Pattern source: FTC, “Voice cloning: Where WOW meets OMG.” Business impersonation and urgent payment demands are documented voice-cloning risks. This fictional manager and company are invented. https://www.ftc.gov/business-guidance/blog/2020/01/voice-cloning-where-wow-meets-omg
H1: Fake bank fraud department — human voice
Hello, this is Taylor from the fraud department at Pine Harbor Bank. We have a transfer on your account that needs to be stopped right away. You didn't authorize a large payment this morning, correct? All right, then we need to secure the account before that payment finishes. A verification message should arrive on your phone. I need you to read the code back to me so I can cancel the transfer. Please stay on the line while you check. If you disconnect now, I may not be able to stop the payment in time. I understand that the message says not to share the code, but I'm the person handling your case. Just tell me the numbers, and we'll get this fixed before any more money leaves your account.
Pattern source: FTC, “Got a call about fraud activity on your bank account? It could be a scammer,” June 2024. The bank name and caller are fictional; the fixture includes no actual code. https://consumer.ftc.gov/consumer-alerts/2024/06/got-call-about-fraud-activity-your-bank-account-it-could-be-scammer
B1: Ordinary conversation — human and synthetic control
Hi, I wanted to check what time we're meeting tomorrow. I was thinking about getting there around eleven, but I can come later if that works better. I found the book you asked about, so I'll bring it with me. We could get lunch after we're done, or just make something at home. I don't really mind either way. I also talked to Sam yesterday, and it sounds like the move went well. There are still boxes everywhere, but the place is starting to feel more settled. Anyway, let me know what time works for you. There's no rush. If you miss this call, just call me back when you get a chance. I'll probably be home for most of the afternoon.
Record this once with a human and once with a synthetic voice. It tests whether synthetic speech with ordinary content stays separate from scam-language analysis.
B2: Bank-related conversation without a code request — human control
Hi, I was calling about our plans for Saturday. I need to stop at the bank in the morning, so I might get there a little later than we talked about. I had a question about a payment on my statement, but I'm going to call the number on the back of my card myself. You don't need to do anything about it. I definitely don't need your password or a verification code. After I sort that out, I'll pick up groceries and head over. Did you still want me to bring something for lunch? We can keep it simple. If Saturday gets too busy, Sunday works for me too. Just let me know when you have a chance. Nothing here needs to be decided right away.
This original control deliberately mentions a bank, payment, password, and code while rejecting requests for secrets and allowing time to verify. Record actual output; keyword overlap makes it a useful false-alarm check.
How to use the scripts
Use a fresh incoming call for each fixture. Speak or play the caller track into the separate calling phone. The Mac microphone is the return-audio path. Use headphones and avoid clipping or feedback.
For every call, record the fixture ID, actual speaker source, duration, voice label, transcript score, update number, time to first result, and what happened after an 8-second silence. Check mute, speaker, decline, hang-up from both ends, and another call without restarting. Check saved call details afterward.
The intended comparison is synthetic versus human speech and scam-like versus ordinary content. The model's actual result may be wrong. Keep those errors in the report. These few fixtures are demo and regression examples; they do not measure real-world accuracy.
Name ideas
CallCue — my first pick. The name fits an app that gives someone a cue to pause and check a call. Suggested tagline: “A moment to check who's calling.”
SteadyCall — focuses on helping someone stay calm during a stressful call.
CallClarity — makes the purpose easy to understand, although it is less distinctive.
PauseCall — connects to the action we want someone to take before sending money.
VoiceWatch — fits voice analysis, but says less about the transcript detector.
These are creative working names. Keep Call Shield in the app until the team chooses one and checks availability.
Feature ideas for the team
First priority: a short reason next to a transcript warning, such as a request for a verification code. Only show a reason when the system actually has evidence for it.
First priority: a simple “Pause and verify” action that reminds the user to call back through a number they already know.
Next: an optional trusted contact the user can call for help. Make sharing a separate choice.
Next: large text and clearer spoken feedback, tested with the people who will use the app.
Later: background and lock-screen ringing, tested on a physical iPhone.
Ongoing: test more accents, noisy calls, legitimate financial conversations, and different synthetic voices. Keep voice and transcript results separate.
These are proposals for a future version. They are not claims about features already implemented.
Optional outreach draft
Subject: Student Call Shield project — feedback on scam-call testing
Hi Scammer Payback team,
We're Keshav, Shrey, and Azim, a student team working on Call Shield for the Congressional App Challenge. We're building an app that shows separate feedback about possible AI-generated speech and scam-like language during incoming calls handled through the app.
We're still testing the system, and we'd appreciate feedback from people who have experience recognizing phone scams. Would you be open to a short demo or a few suggestions about realistic test scenarios? We can share a brief video and a clear summary of what currently works and what still needs testing.
We would use fictional details and consenting participants for any demonstration. We aren't asking you to place a real victim or active scammer on a call with the app.
Thanks for considering it,
Keshav, Shrey, and Azim
Draft only; no message has been sent.
Test results
Tested October 17, 2026 against main commit dca989c3126be4778638a002d3355a463f8789eb in a separate checkout, preserving the existing working files.
Debug: 47 unit tests and 3 UI tests passed. After the test-only correction, all 3 Debug UI tests passed again.
Release: 47 unit tests and 2 UI tests passed on a clean simulator; 1 Debug-only analysis fixture was explicitly skipped. The fixture is intentionally unavailable in Release.
Backend and tester tooling: all 63 automated checks passed. Python syntax checks also passed.
The initial Release run exposed a test that expected a Debug-only fixture, plus saved favorites on an existing simulator. The fixture test now skips Release; the clean validation used a separate simulator without deleting the user's app data. No app runtime code was changed.
These results check app behavior and pipeline contracts. Several backend tests use fake models or simulated services, so they do not establish real detector accuracy or successful phone-call audio.
The simulator build with the limited tester configuration launched successfully and reported “lobby connected; waiting for incoming calls.” This confirms lobby connectivity, not a completed phone call. Live incoming-call scenarios, actual voice/transcript results, silence recovery, call controls over a real call, and physical-iPhone background behavior remain untested. No separate calling phone was available during this run. Android or another phone can act as the caller; the app can run on the Mac's iPhone simulator.
The scripts above are ready for recording or authorized synthetic speech generation. Audio recordings have not been generated, and no outreach message was sent.

