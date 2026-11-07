# Daily health short: production recipe

This repo is the daily pipeline for one 9:16 health & wellness short a day. The audience is US women 30+, but the videos should still work for men. Each video is posted as a Facebook Reel through Metricool. Every run follows this file exactly. Never test or retry a paid generation: ElevenLabs charges for each one.

## Fixed settings (do not change without the owner's say-so)

| Thing | Value |
|---|---|
| ElevenLabs flow (reuse it every day) | `wUExjTQxFX7dXQHd8tfH` |
| Presenter portrait node (saved presenter, never regenerate) | `IwnPS9Z19npztCcIYYHR` (active generation `Clz4gqm3ZNkHWa2shJjc`) |
| Voice | Nicole, `54FMJGnzgRE67pxXGHg4`, model `eleven_v4`, **1 take** (`generations_count: 1`) |
| Presenter clip | `heygen-avatar4`, params `{"talking_style":"expressive","resolution":"1080p","aspect_ratio":"9:16"}`, image from `IwnPS9Z19npztCcIYYHR`, audio from the hook TTS node |
| B-roll start frames | `gemini-3.1-flash-image`, params `{"aspect_ratio":"9:16","resolution":"1K"}`, 1 each |
| B-roll clips | `ltx-v2-fast`, params `{"duration_secs":6,"resolution":"1080p","target_fps":25,"generate_audio":false}`, start_frame wired from its frame node |
| Credit cap per video | **13,500**. Estimate everything first (`estimate_only`, which is free) and stop if the total is over the cap |
| Metricool brand | blogId `7945364` ("So Filthy" Facebook page), timezone `Europe/Dublin` |
| Video URL for Metricool | `https://raw.githubusercontent.com/mylottoie1-sketch/socialvideos/main/videos/<id>.mp4` |

## Steps

1. **Pick the topic.**
   - Read `topics/log.json` (everything already posted) and `topics/backlog.json`.
   - Take the first backlog entry whose `id` is not in the log.
   - If the backlog is used up, research a new topic first (see "New topics" below), append it to `backlog.json`, then use it.

2. **Voice.** Create one TTS node for the hook and one for each entry in `lines`, all on the flow with the fixed voice, model and 1 take. Each node's prompt is the `tts` text, and the hook node uses `hook_tts`. Label them `<id> hook` and `<id> line 00`, `01` and so on.

3. **Visuals.**
   - Add a `heygen-avatar4` node labelled `<id> presenter`, wired from the presenter portrait node and the hook TTS node.
   - Add 4 image nodes from the spec's `broll[k].frame_prompt`.
   - Add 4 `ltx-v2-fast` nodes from `broll[k].motion_prompt`, each wired from its frame node.

4. **Cost check.** Run `creative_run_flow_nodes` with `estimate_only: true` on all new nodes, then add up the costs. If the total is over 13,500, stop, generate nothing, and report it.

5. **Generate**, in dependency order:
   - TTS and image nodes first (images 1 each). Wait for them to finish.
   - Then the presenter and LTX nodes. Wait until all are complete, polling `creative_get_flow_run_status` every ~30 s.
   - Never re-run a node to retry. If one fails, report it and stop.

6. **Download** every output with `creative_get_generations` and `curl` into a work dir `/tmp/<id>/`:
   - `hook.mp4` (presenter)
   - `line_00.mp3`, `line_01.mp3` and so on
   - `b1.mp4` … `b4.mp4`
   - `spec.json` (the backlog entry)

   `elevenlabsusercontent.com` is on the allowlist.

7. **Compose.**
   - Run `python3 pipeline/compose.py /tmp/<id>`.
   - Check the result: look at `preview.jpg`, and run `ffprobe` to confirm 1080x1920, video plus audio, 30–60 s long.
   - Grab 3 frames and look at them. If text overflows or anything looks broken, fix the spec text (not the paid assets) and re-compose. Composing is free.

8. **Publish the file.**
   - Copy `final.mp4` to `videos/<id>.mp4`.
   - Append to `topics/log.json`: `{"id", "topic", "date", "credits", "post_time", "sources": [...]}`.
   - Commit and push to `main`.
   - Check that the raw URL returns HTTP 200: `curl -sI`.

9. **Schedule the post.**
   - Pick the best Facebook slot in the next 24 h with `getBestTimeToPostByNetwork` (brand 7945364, timezone Europe/Dublin). It must be at least 30 min from now. If that fails, use 23:30 Europe/Dublin (6:30 pm US Eastern).
   - Call `createScheduledPost` with `blogId 7945364` and `info`:
     - `providers [{"network":"facebook"}]`
     - `text`: the spec's `fb_text`, followed by a blank line and `Presenter, voice and visuals created with AI.`
     - `media ["<raw URL>"]`
     - `facebookData {"type":"REEL","title": fb_title}`
     - `autoPublish true`, `draft false`
     - `publicationDate {dateTime, timezone:"Europe/Dublin"}`
   - Record the planner URL in the log entry, then commit and push again.

10. **Report** in one short message: the topic, the post time, credits used, and the Metricool planner link.

## New topics (only when the backlog is used up)

- Use WebSearch (mode "extended") to find women's-health and wellness topics that are trending right now on short-form video and in health news, for women 30+.
  - Good areas: perimenopause/menopause, strength and bones, gut health, sleep, stress/cortisol, heart health, iron and thyroid, pelvic health, nutrition myths, hydration, posture and back pain, skin and aging, mental load.
  - Skip anything already in `log.json` or `backlog.json`.
- Write each new topic as a backlog entry with the same shape as the existing ones:
  - `hook_tts` of 1–2 short sentences (the presenter speaks it), plus `hook_caption_split`
  - 5–7 `lines`, the last one a follow/share/save call to action
  - `cards` with `at_line` (-1 = during the hook)
  - 4 `broll` entries covering every line in order
  - `fb_title` and `fb_text` with 3–5 hashtags and the disclaimer line
- Aim for 120–160 spoken words in total. Use US spelling and units.
- **Accuracy is non-negotiable.**
  - Every factual claim must be supported by a reputable source opened during research: NIH/MedlinePlus, CDC, Mayo Clinic, Cleveland Clinic, ACOG, AHA, NHS or peer-reviewed reviews. Record those URLs in the log entry's `sources`.
  - Hedge where the evidence is mixed ("research suggests", "can help").
  - Never give dosing, diagnoses or product recommendations.
  - Always point to a doctor for symptoms.
  - Never present the presenter as a medical professional.
- B-roll prompts must be photorealistic, vertical, "No text, no logos", and wholesome. Use no real people or brands.
- Add 3 new topics at a time so the backlog doesn't run dry every day.
