# NAACL 2027 demo video

`finbot-naacl2027-demo.mp4` (2:28, 1080p, H.264/AAC, burned-in captions; also on
[Google Drive](https://drive.google.com/file/d/1ifUSzuIPhGMZAHMt0FXP5l9ivdZmbrYK/view?usp=sharing)) walks through the
November 24 demo build (scene 5 re-recorded on the hosted inspector on November 28), narrated by Soovadeep Bakshi. `narration.md` is the script and storyboard;
`captions.srt` holds the captions.

This video demonstrates clarification, explicit confirmation, record-based recovery and
the payment-vs-refund financial-role check (inspector scenario "Payment is not refund"). It does not demonstrate the newly added context-budget contracts or the
48-pair error challenge. It has not been re-recorded for `abose/evaluation-context-gaps`;
the paper reports those additions separately as offline implementation/evaluation evidence.

The results slide describes the `ClarificationSession` component, not measured customer
performance of the deployed controller. When the narration says code looks for "every amount,
status and ID", extraction covers finite formats and does not establish semantic correctness or
completeness (see the paper's Limitations).

To rebuild (Linux, with Xvfb, ffmpeg, Node and Playwright):

1. Run the demo locally: `python -m finbot.demo --port 8766`.
2. Render the cards: `node build/cards/shot.js` (writes title, results and closing PNGs).
3. Record the screen on a virtual display while `build/record.js` drives the browser. Scene
   lengths come from the `DURS` environment variable, set to fit the narration clips.
4. `build/assemble.py` cuts the scenes, adds the narration clips (`s1`–`s7`) and the cards, and
   burns in the captions from `narration.md` (env `AUD`, `EXT`, `SYNC` = frame of the magenta sync flash, `PAD5`). The voice clips themselves are not in the repository.
5. Scene 5 was re-recorded on November 28 against the hosted inspector with
   `build/scene5-refund-role.js` and spliced into the November 24 cut with
   `build/splice_scene5.py` (old scene 5 = 1:38.6 to 1:51.65), which also regenerates `captions.srt`.
