# NAACL 2027 demo video

`finbot-naacl2027-demo.mp4` (2:26, 1080p, H.264/AAC, burned-in captions) walks through the hosted
demo. `narration.md` is the script and storyboard; `captions.srt` holds the captions.

This recording predates the revised evaluation. Its results slide describes the
`ClarificationSession` component, not measured customer performance of the deployed controller.
The revised paper adds stronger heuristics, the full-list comparison and paired verification
diagnostics. Its bounded claims supersede the narration's statement that code extracts
"every amount, status and ID": extraction covers finite formats and does not establish
semantic correctness or completeness. Update the narration, captions and results slide before
using this recording as the final submission video; the original audio clips are not bundled.

To rebuild (Linux, with Xvfb, ffmpeg, Node and Playwright):

1. Run the demo locally: `python -m finbot.demo --port 8766`.
2. Render the cards: `node build/cards/shot.js` (writes title, results and closing PNGs).
3. Record the screen on a virtual display while `build/record.js` drives the browser. Scene
   lengths come from the `DURS` environment variable, set to fit the narration clips.
4. `build/assemble.py` cuts the scenes, adds the narration clips (`s1`–`s7`) and the cards, and
   burns in the captions. The voice clips themselves are not in the repository.
