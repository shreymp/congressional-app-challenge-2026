# Three staged test calls

Get explicit consent before routing audio through the app. Names and situations below are fictional. Use only your own voice or a synthetic voice you are allowed to use. Never enter a real code, send money, or contact an outside target. Read both roles naturally, with pauses. Each script exceeds 180 spoken words: at 120–150 words per minute it should last over a minute; measure the actual recording. For the submission video, select short excerpts and identify time cuts.

## 1. Regular human conversation

Caller uses their own natural voice. Desired comparison: likely human voice and little scam-language concern. This is a test expectation, not a guaranteed model result.

**Caller:** Hey, it's Alex. I'm calling about dinner on Saturday. I finally checked the weather, and it looks like we can probably sit outside if it stays warm. Would six o'clock work for you, or would you rather eat a little earlier?

**Recipient:** Six sounds good. Are we meeting at your house, or should I make a reservation somewhere?

**Caller:** Let's do my house. I was thinking pasta, salad, and that bread you brought last time. I already have most of the groceries, so you don't need to pick anything up. If you want to bring something, maybe the pictures from your trip. I'd like to see the ones from the garden you visited.

**Recipient:** I can bring those. Is anyone else coming?

**Caller:** Jamie said they could stop by after work, but they might be a little late. We can start eating and save them a plate. Also, I found the blue sweater you left here last month. It's on the chair by the front door, so remind me to give it back before you leave.

**Recipient:** I wondered where that went. Thanks for finding it.

**Caller:** No problem. I'll see you Saturday at six. If the weather changes, we'll just eat inside. Take your time getting here, and give me a call if you need directions. Have a good rest of your afternoon.

**After the call:** Check the actual voice result, peak scam score, contact name, call duration, and saved history. A false AI/scam result is a failure to investigate, not something to edit out as a successful test.

## 2. Synthetic voice and scam language

Use an authorized synthetic voice for Caller. The words alone do not make this a deepfake test. Desired comparison: AI voice evidence and elevated scam-language concern. “AI-generated” does not prove impersonation.

**Caller:** Hi, it's Sam. Please don't hang up. I know my voice sounds different, but I'm using someone else's phone because mine stopped working. I'm in trouble, and I need you to listen before you call anyone else. I was told I only have a few minutes to sort this out.

**Recipient:** What happened? Where are you right now?

**Caller:** I'm at an office near the station. Someone here says I need to pay a release fee before I can leave. They told me I shouldn't involve the rest of the family because that would make the process take longer. Please keep this between us for now. I don't want anyone to worry.

**Recipient:** I should call your usual number or check with your parents first.

**Caller:** No, please don't do that yet. My usual phone won't work, and we don't have time. They said the payment needs to happen right away. Could you go to a store and get a prepaid gift card? Once you have it, I need you to read the numbers from the back over the phone. That will supposedly clear the fee.

**Recipient:** Asking for gift cards sounds suspicious. I'm going to end this call and check with someone I know.

**Caller:** Please stay on the line. They said if you disconnect, I'll lose this chance to leave. Don't tell the cashier what it's for, and don't send a message to anyone else until we're finished.

**Recipient:** I'm hanging up. I'll contact Sam using the number already saved in my contacts.

**After the call:** Check the separate voice and scam results. If excerpt delivery was enabled for this consented test, review the saved excerpt in call details. It must not appear as a live transcript. No actual payment occurs.

## 3. Human voice and scam language

Caller uses a real human voice. Desired comparison: human voice evidence with elevated scam-language concern. This checks that “human” does not imply “safe.”

**Caller:** Hello, this is Jordan from the security department at your bank. I'm calling because our system supposedly detected an unusual purchase on your account this afternoon. Before I explain the transaction, I need to verify that I'm speaking with the account holder. Are you able to stay on the phone for a few minutes?

**Recipient:** I can talk, but I don't recognize this number. Which bank are you calling from?

**Caller:** We handle security for several institutions, so the number might look unfamiliar. The important thing is that we stop this purchase before it goes through. You may receive a text message with a security code in a moment. Please read that code out loud so I can confirm your identity and cancel the payment.

**Recipient:** The message says I should never share the code with anyone. I think I should call my bank directly.

**Caller:** That warning is for other situations. I'm already working on your case, and calling the main number could delay the cancellation. Please don't open your banking app or speak to another representative while I'm doing this. I just need the code, then I may ask you to move the remaining balance into a temporary account for protection.

**Recipient:** I'm not going to share a code or move any money. I'll hang up and call the number printed on my card.

**Caller:** If you end the call now, we may not be able to stop the charge in time. Can you at least tell me the first few digits?

**Recipient:** No. Goodbye.

**After the call:** Confirm that the voice result and scam warning remain separate. Verify that a later lower model score cannot lower the peak shown for this call, and that the next call starts fresh.

## Test log

For each actual run record: build/commit, server version, consent confirmed, caller voice source, duration, first voice-result time, voice result at 30 seconds, peak scam score, false alarms, contact match, end-call cleanup, excerpt setting, and history readback. Keep automated contract tests, synthetic audio, and real phone-call evidence separate.
