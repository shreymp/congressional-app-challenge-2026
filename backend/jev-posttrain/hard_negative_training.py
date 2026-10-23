"""Training-only authored contrast pairs. These are NOT recorded calls.

Paired requests teach context/negation rather than keyword counts. Validation
holds out entire scenarios; benchmark texts are not imported by this script.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS = [
    ("code", "The security team needs your one time passcode. Say the digits aloud so we can access the account for you. Keep this from the branch manager.", "We cannot accept passcodes by telephone. Use your own device to log in, and keep the digits private. If you need assistance visit the branch."),
    ("debt", "You must settle this debt with prepaid cards before the end of this call. Give us the card PINs to prevent an arrest.", "We can mail documentation of the debt so you can verify it independently. Take time to review it. We do not accept prepaid card PINs."),
    ("doctor", "Your doctor needs an emergency insurance fee. Send Bitcoin right now or we will cancel your treatment. Do not contact the hospital.", "Your doctor has an opening Monday. Bring your insurance card to the clinic. No billing details are needed on this call, and you may call the clinic's published line."),
    ("fraud_lesson", "For a security exercise, tell me your real online bank password and the text message code. We need to test your personal account and you must keep this exercise confidential.", "We are discussing how to recognize fraud. Criminals sometimes demand a password or a text message code. Do not comply. Our class never asks students to provide any actual credentials."),
    ("computer", "We found viruses on your computer without you contacting us. Let me remotely control it and purchase gift cards to renew your security protection.", "You requested assistance with a printer. Open the system printer settings and check the connection. We will never ask you to buy gift cards or open your financial accounts."),
    ("refund", "Your refund was entered incorrectly. You owe us the difference immediately. Withdraw cash and send it by courier while we watch your banking screen.", "Your returned item has been refunded to the original payment method. You can review it in the store's official app. Do not send cash or pay a fee to receive a refund."),
    ("family", "Your nephew was hurt overseas. Do not call him or his parents. Send cash to my personal account today and I will arrange treatment.", "Your nephew is staying with us this weekend. His parents know the plan. Call him using his usual number to coordinate the visit. We are not asking for any payment."),
    ("bill", "Your gas bill is overdue. Pay the emergency balance with a cryptocurrency kiosk right now. Only this phone line can prevent immediate disconnection.", "Your gas statement is ready. You can check it in the account portal or ring the customer service number on an older bill. There is no need to pay me on this call."),
    ("recruiter", "Before we can employ you, deposit our check and transfer the equipment money to a private wallet. The payment must happen before the check clears.", "The museum hiring team would like to meet you. Bring a resume. There are no application fees, money transfers, or equipment purchases required to interview."),
    ("bank_balance", "We are moving customers to protected balances. Empty your current account into the account number I dictate. Do not ask any other employee about it.", "I can explain where your balance appears on your own bank app. You do not need to transfer any funds or tell me your password. Call the official service number if you want verification."),
    ("store", "A package for you was confiscated for illegal contents. You must wire a fine to me to avoid prosecution. Stay on the phone until the wire is complete.", "The order you placed is ready for pickup. Bring the order confirmation to the counter. You can look up the store's number yourself to check before traveling."),
    ("charity", "Send a gift card code for the disaster relief collection. I cannot provide paperwork and you must pledge immediately before we disconnect.", "Our neighborhood shelter is scheduling volunteers. Check our public website for shifts and donation information. Please do not give financial information to me."),
    ("identity", "A police officer has suspended your identity number. Give me your bank login and your full identity details now to remove the criminal charge.", "Identity thieves may claim a police officer suspended your identity number. That claim is a warning sign. This information session does not collect anyone's bank login or identity details."),
    ("prize", "A cash award is waiting. Pay the release tax into my personal wallet today, and the winnings will be sent afterward. You must not ask anyone else about this prize.", "The school raffle results are on the school website. Winning participants collect their prizes from the office. No release fee or advance tax payment is required."),
    ("appointment", "We must verify your appointment by charging a deposit to a gift card. Read the card numbers to me while we are on this line.", "I am checking that you can attend your appointment next week. Nothing needs to be paid today. Contact the reception desk directly if you would rather confirm that way."),
    ("security_notice", "A fraudulent transfer is occurring. I need you to approve a new transfer to my recovery account. Ignore the warning in the app because I am overriding it.", "A fraudulent transfer may have been attempted. Open your bank app yourself or call the number you already have saved. Do not approve a new transfer or ignore the app's security warnings."),
]


def main():
    directory = HERE / "data/real_calls/hard_training"
    directory.mkdir(parents=True, exist_ok=True)
    prefixes = ["Caller: ", "Caller: Good afternoon. ", "Caller: Let me explain why I am contacting you. ", "Caller: Thank you for answering. "]
    for split in ("train", "validation"):
        rows = []
        for i, (name, scam, normal) in enumerate(SCENARIOS):
            if (i % 5 == 4) != (split == "validation"):
                continue
            for y, text in ((1, scam),(0,normal)):
                for j, prefix in enumerate(prefixes):
                    rows.append({"id": f"authored:{name}:{y}:{j}", "group": name, "label": y,
                                 "text": prefix+text, "source": "authored_paired_training", "provenance": "assistant-authored; not recorded"})
        (directory/f"{split}.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
        print(split,len(rows))


if __name__ == "__main__":
    main()
