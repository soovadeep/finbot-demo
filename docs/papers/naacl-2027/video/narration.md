# NAACL 2027 demo video: narration and storyboard (draft 4: November 24 build, scene 5 re-recorded November 28)

Target: under 2 min 30 s (NAACL limit). About 330 words at 145 words a minute, so roughly 2:15 with pauses.
Every scene is the hosted demo as it is now (https://finbot-demo-20852907589.us-central1.run.app/), driven by a script, so it can be re-recorded after any change.
Numbers are the paper's (Table 1 and Section 4.3, eight candidate records). No KDD numbers appear.
Captions are generated from this text.

| # | Time | Screen | Narration |
|---|---|---|---|
| 1 | 0:00 to 0:15 | Title card: "Finbot: from payment ambiguity to evidence grounded answers", the four author names. Then the empty conversation page. | Customers rarely quote a transaction ID. When a message could match several payments, an assistant that guesses can give a correct-sounding answer about the wrong money. Finbot is built not to guess. |
| 2 | 0:15 to 0:45 | Customer types and sends "My $200 payment hasn't arrived. When will it get there?" Open "Inspect record beliefs and question scores": four $200 records, scores for payment type, date and payee. | A customer of a fictional bank types: "My two-hundred-dollar payment hasn't arrived. When will it get there?" No date, no payee, no transaction ID. Their account has four two-hundred-dollar payments, so the amount alone rules nothing out. Finbot keeps a probability for each record the customer is allowed to see, scores each question it could ask by how much it would narrow things down, and asks the best one: was it a card payment or a bank transfer? |
| 3 | 0:45 to 1:05 | Customer clicks "Bank transfer". Asked for the date, types "Willow Repairs". One record offered; customer confirms. | The customer picks bank transfer. Asked for the date, they name the payee instead, and Finbot uses that. One record now fits what the customer said, but a probability never selects a record on its own. The customer has to confirm it. |
| 4 | 1:05 to 1:40 | Fault menu set to "Invented fee in draft and repair". "How the answer was checked": record fetched again, draft rejected, repair rejected, answer built from the record. A callout compares the draft with the record: 200.00 USD and pending are found, the 12.34 fee is not. | Now the confirmed record is fetched again, and the customer's question goes to the writer. Here, the draft adds a processing fee. Plain code, not another model, looks for every amount, status and ID from the draft in the record. The fee isn't there, so the draft is rejected, and so is the repair. The answer is built from the record instead: the transfer is pending, expected November eighteenth. An answer that skipped the date would be sent back too. Each answer is labelled with who wrote it. |
| 5 | 1:39 to 1:51 | Hosted inspector, scenario "Payment is not refund": run; the draft's "Refund amount: 200.00" is rejected by the role check (200.00 is on the record, but as the payment; refund.amount is 50.00); the repair states 50.00 and passes. | Being on the record isn't enough: each amount must also play the right role. This draft gives the two-hundred-dollar payment as the refund, which was fifty, so it is rejected and repaired. |
| 6 | 1:55 to 2:20 | One results slide: top-1 13% none, 19% fixed order, 69-74% one Bayesian question; wrong-record 21-26% if acting on the top guess vs 2-4% with confirmation. | We tested this on 224 real Banking77 questions with the reference removed, with simulated customers from two model families. Among eight records, one well-chosen question puts the right record first in about seven of ten conversations, against two in ten for a fixed question. Confirmation keeps wrong-record selections at two to four percent, against over twenty if Finbot acted on its best guess. |
| 7 | 2:20 to 2:30 | Hosted demo URL, repository link, "runs offline, no API key". | Try it in your browser, or run it offline with no API key. |

## Production plan

- Screen: Playwright drives the hosted demo with these exact inputs and records 1280x800 video; slide 6 and the cards are rendered as HTML pages.
- Voice: Piper (sample in this folder) or a macOS voice (recorded with `say` on the Mac). Your choice.
- Assembly: ffmpeg lays the narration over the screen recording, burns in captions, and exports MP4 (H.264, AAC) under 2:30.
- Delivery: the MP4 is on Google Drive (anyone with the link can view: https://drive.google.com/file/d/1ifUSzuIPhGMZAHMt0FXP5l9ivdZmbrYK/view?usp=sharing), linked from the repository README, with a copy in this folder.
