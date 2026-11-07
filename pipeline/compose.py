#!/usr/bin/env python3
"""Compose a 1080x1920 health short from generated parts.

Usage: python3 compose.py <workdir>

<workdir> must contain:
  spec.json            the video spec (see specs/EXAMPLE.json)
  hook.mp4             presenter talking-head clip (with its own audio)
  line_00.mp3 ...      one voiceover file per spec["lines"] entry, in order
  b1.mp4 .. b4.mp4     silent b-roll clips (any length, 9:16)
Writes <workdir>/final.mp4 (H.264/AAC, 30 fps, faststart) and preview.jpg.
"""
import json, math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
GAP = 0.25          # silence between voiceover lines (s)
TAIL = 2.2          # end hold for disclaimer (s)
ACC = (255, 214, 102)
SERIES = "HEALTH STUFF NOBODY TOLD US"


def font(size):
    for p in ["/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_SUB, F_TAG, F_CAP, F_DISC = font(56), font(40), font(62), font(34)


def run(*a):
    subprocess.run(a, check=True)


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]).decode())


def ease(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def back(t):
    t = max(0.0, min(1.0, t)); c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def wrap(d, text, f, maxw):
    out, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= maxw: cur = trial
        else: out.append(cur); cur = w
    out.append(cur); return out


def chunk_caps(s, e, text, out):
    w = text.split(); n = len(w); t = s
    for i in range(0, n, 4):
        part = w[i:i + 4]; d = (e - s) * len(part) / n
        out.append((t, t + d + (0.3 if i + 4 >= n else 0), " ".join(part))); t += d


def main(wd):
    spec = json.load(open(f"{wd}/spec.json"))
    lines = spec["lines"]
    enc = ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]

    # ---- timeline -------------------------------------------------------
    hook_d = dur(f"{wd}/hook.mp4")
    caps = []
    hook_sil = spec.get("hook_caption_split")  # optional: list of caption strings for the hook
    hook_caps = hook_sil or [spec["hook_caption"]]
    # spread hook captions by word share over the hook clip (minus 0.2 s tail)
    tw = sum(len(c.split()) for c in hook_caps); t = 0.0
    for c in hook_caps:
        d = (hook_d - 0.2) * len(c.split()) / tw
        chunk_caps(t, t + d, c, caps); t += d

    line_t = []  # (start, end) of each voiceover line on the output timeline
    t = hook_d + 0.15
    for i in range(len(lines)):
        d = dur(f"{wd}/line_{i:02d}.mp3")
        line_t.append((t, t + d)); chunk_caps(t, t + d, lines[i]["caption"], caps); t += d + GAP
    body_end = t - GAP
    total = body_end + TAIL

    # ---- audio ------------------------------------------------------------
    parts, filt = ["-i", f"{wd}/hook.mp4"], "[0:a]aresample=48000,asetpts=PTS-STARTPTS,apad=pad_dur=0.15,atrim=0:%.3f[a0];" % (hook_d + 0.15)
    labels = ["[a0]"]
    for i in range(len(lines)):
        parts += ["-i", f"{wd}/line_{i:02d}.mp3"]
        pad = GAP if i < len(lines) - 1 else TAIL
        filt += f"[{i+1}:a]aresample=48000,asetpts=PTS-STARTPTS,apad=pad_dur={pad}[a{i+1}];"
        labels.append(f"[a{i+1}]")
    filt += "".join(labels) + f"concat=n={len(labels)}:v=0:a=1,loudnorm=I=-14:TP=-1.5,apad,atrim=0:{total:.3f}[a]"
    run("ffmpeg", "-loglevel", "error", "-y", *parts, "-filter_complex", filt, "-map", "[a]",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2", f"{wd}/audio.m4a")

    # ---- video pieces -----------------------------------------------------
    run("ffmpeg", "-loglevel", "error", "-y", "-i", f"{wd}/hook.mp4", "-vf",
        f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},tpad=stop_mode=clone:stop_duration=0.15",
        *enc, f"{wd}/v0.mp4")
    broll = spec["broll"]
    cursor = hook_d + 0.15
    for k, b in enumerate(broll):
        last_line = b["lines"][-1]
        end = line_t[last_line][1] + (GAP if last_line < len(lines) - 1 else TAIL)
        seg = end - cursor
        src = f"{wd}/b{k+1}.mp4"; sd = dur(src)
        factor = max(1.0, seg / sd)
        run("ffmpeg", "-loglevel", "error", "-y", "-i", src, "-vf",
            f"setpts={factor:.4f}*PTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"tpad=stop_mode=clone:stop_duration=1,trim=0:{seg:.3f},setpts=PTS-STARTPTS", *enc, f"{wd}/v{k+1}.mp4")
        cursor = end
    with open(f"{wd}/list.txt", "w") as fh:
        for k in range(len(broll) + 1): fh.write(f"file 'v{k}.mp4'\n")
    run("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{wd}/list.txt", "-c", "copy", f"{wd}/base.mp4")

    # ---- headline cards ---------------------------------------------------
    heads = []
    for j, c in enumerate(spec["cards"]):
        start = 0.0 if c["at_line"] < 0 else line_t[c["at_line"]][0] - 0.1
        heads.append([start, None, c["head"], c.get("sub")])
    for j in range(len(heads)):
        heads[j][1] = heads[j + 1][0] if j + 1 < len(heads) else 1e9

    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd_ = ImageDraw.Draw(shade)
    for y in range(820): sd_.line([(0, y), (W, y)], fill=(0, 0, 0, int(150 * (1 - y / 820) ** 1.4)))
    for y in range(1300, H): sd_.line([(0, y), (W, y)], fill=(0, 0, 0, int(110 * ((y - 1300) / (H - 1300)) ** 1.6)))

    cache = {}
    def head_img(i):
        if i in cache: return cache[i]
        _, _, head, sub = heads[i]
        hl = Image.new("RGBA", (W, 560), (0, 0, 0, 0)); hd = ImageDraw.Draw(hl)
        rows = head.split("\n")
        for size in range(108, 60, -4):
            fh = font(size)
            if max(hd.textlength(r, font=fh) for r in rows) <= 960: break
        lh = int(size * 1.15); y = 280 - (len(rows) * lh + (80 if sub else 0)) / 2
        for r in rows:
            for dx, dy in [(4, 5), (0, 3)]:
                hd.text((W / 2 + dx, y + lh / 2 + dy), r, font=fh, fill=(0, 0, 0, 120), anchor="mm")
            hd.text((W / 2, y + lh / 2), r, font=fh, fill=(255, 255, 255, 255), anchor="mm"); y += lh
        if sub:
            sf = fh if sub.startswith("≠") else F_SUB
            if hd.textlength(sub, font=sf) > 980: sf = font(44)
            hd.text((W / 2 + 3, y + 49), sub, font=sf, fill=(0, 0, 0, 140), anchor="mm")
            hd.text((W / 2, y + 45), sub, font=sf, fill=ACC + (255,), anchor="mm")
        cache[i] = hl; return hl

    disc_at = body_end + 0.3
    def overlay(frame, t):
        im = frame.convert("RGBA"); im.alpha_composite(shade); d = ImageDraw.Draw(im)
        tl = d.textlength(SERIES, font=F_TAG)
        d.rounded_rectangle([(W - tl) / 2 - 36, 110, (W + tl) / 2 + 36, 190], radius=40, fill=(0, 0, 0, 255))
        d.text((W / 2, 150), SERIES, font=F_TAG, fill=ACC, anchor="mm")
        for i, (h0, h1, _, _) in enumerate(heads):
            if h0 <= t < h1:
                lt = t - h0; s = back(lt / 0.35); a = ease(lt / 0.2)
                if s > 0.01:
                    sw, sh = int(W * s), int(560 * s)
                    hs = head_img(i).resize((max(sw, 1), max(sh, 1)), Image.BILINEAR)
                    if a < 1: hs.putalpha(hs.getchannel("A").point(lambda q: int(q * a)))
                    im.alpha_composite(hs, ((W - sw) // 2, 220 + (560 - sh) // 2))
        cur = None
        for c0, c1, c in caps:
            if c0 <= t < c1: cur = c
        if cur:
            rws = wrap(d, cur, F_CAP, 900); cy = 1560 - (len(rws) - 1) * 40
            for r in rws:
                rl = d.textlength(r, font=F_CAP)
                d.rounded_rectangle([(W - rl) / 2 - 28, cy - 48, (W + rl) / 2 + 28, cy + 44], radius=22, fill=(0, 0, 0, 255))
                d.text((W / 2, cy), r, font=F_CAP, fill=(255, 255, 255), anchor="mm"); cy += 96
        if t > disc_at:
            al = int(255 * ease((t - disc_at) / 0.3))
            d.text((W / 2, 1780), "General information only, not medical advice.", font=F_DISC, fill=(255, 255, 255, al), anchor="mm")
            d.text((W / 2, 1830), "Talk to your doctor.", font=F_DISC, fill=(255, 255, 255, al), anchor="mm")
        out = im.convert("RGB")
        if total - t < 0.3:
            out = Image.blend(Image.new("RGB", (W, H)), out, ease((total - t) / 0.3))
        return out

    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", f"{wd}/base.mp4", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    tmp = f"{wd}/final.tmp.mp4"
    encp = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "-", "-i", f"{wd}/audio.m4a", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "19",
        "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", "-movflags", "+faststart", tmp],
        stdin=subprocess.PIPE)
    k, sz, prev = 0, W * H * 3, None
    while True:
        raw = dec.stdout.read(sz)
        if len(raw) < sz: break
        fr = overlay(Image.frombytes("RGB", (W, H), raw), k / FPS)
        if abs(k / FPS - 2.0) < 0.5 / FPS: fr.save(f"{wd}/preview.jpg", quality=85)
        encp.stdin.write(fr.tobytes()); k += 1
    encp.stdin.close()
    if encp.wait() != 0: sys.exit("encode failed")
    os.replace(tmp, f"{wd}/final.mp4")
    print(json.dumps({"frames": k, "duration": round(total, 2), "out": f"{wd}/final.mp4"}))


if __name__ == "__main__":
    main(sys.argv[1])
