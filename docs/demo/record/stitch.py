"""Stitch the recorded clips (demo-video/clips/*.webm) into two H.264 MP4s with ffmpeg.

    python3 docs/demo/record/stitch.py

Writes demo-video/harvestnet-demo.mp4 (the full walk-through), demo-video/harvestnet-demo-short.mp4
(a 60 to 90 second highlight cut) and demo-video/README.txt. Needs ffmpeg and ffprobe on the PATH.
The short cut uses the timestamps record_demo.py saved in demo-video/marks.json.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'demo-video'
CLIPS = OUT / 'clips'
WORK = OUT / 'work'
MARKS = json.loads((OUT / 'marks.json').read_text())
FPS = 25
VF = 'scale=1280:720:flags=lanczos,format=yuv420p'
ENC = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-r', str(FPS), '-pix_fmt', 'yuv420p', '-an']

CARD_SECONDS = 3.0

# What each segment of the full video shows (also written to README.txt).
LONG = [
    ('card:intro', 'Title card: this is a local run on one Mac, synthetic data only.'),
    ('00-opening', 'Opening, slides 1 to 3 of docs/demo/slides.html (live in the browser).'),
    ('01-household', 'Moment 1, a household asks in Spanish. LIVE-DRIVEN on the household page. The voice line is shown as the web form '
                     '(text fallback), with the same read-back and consent question. It saves a request code and picks food banks.'),
    ('02-donor-negotiation', 'Moments 2 and 3, the farmers market reports surplus on the donor page and the agents negotiate. LIVE-DRIVEN. '
                             'The rules-based negotiators run on submit; the clip scrolls the version history with each reason.'),
    ('04-approvals', 'Moment 4, a live approval. LIVE-DRIVEN. The local approvals service issues one review link per organization '
                     '(email is not sent locally) and each organization approves the exact version; the lot becomes committed.'),
    ('05-cooler', 'Moment 5, the cooler fails. LIVE-DRIVEN. The local demo switch fails the city cooler; the city host\'s own watcher proposes a '
                  'new version; the city dashboard shows the reason cards; city and eastside approve the new version on fresh review links.'),
    ('06-pickup', 'Moment 6, the household\'s pickup screen. LIVE-DRIVEN. Shows the changed pickup (eastside) and Can\'t make it (No puedo ir) '
                  'in Spanish. No email or text is sent locally, so the pickup screen stands in for it.'),
    ('07-results', 'Moment 7 and close. LIVE-DRIVEN. The results strip reads the free (rules-based) evaluation stored in the local core; then slide 16.'),
    ('card:outro', 'Closing card.'),
]

# The highlight cut: (clip, start mark or seconds, end mark or seconds, speed)
SHORT = [
    ('card:intro', None, None, 2.5),
    ('01-household', 'form_start', 'read_back', 4),
    ('01-household', 'read_back', 'saved', 2),
    ('01-household', 'saved', 'waiting', 2.5),
    ('02-donor-negotiation', 'offer_ready', 'offered', 2),
    ('02-donor-negotiation', 'versions', 'versions_end', 2.5),
    ('05-cooler', 'terminal', 'flipped', 1.5),
    ('05-cooler', 'flipped', 'disruption', 3),
    ('05-cooler', 'disruption', 'reason_cards_end', 1.5),
    ('05-cooler', 'reason_cards_end', 'reapproved', 3),
    ('06-pickup', 'pickup', 'released', 2),
    ('07-results', 'results', 'results_end', 2),
    ('07-results', 'results_end', 'close', 1),
    ('07-results', 'close', None, 1),
]


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.exit(f'ffmpeg failed: {" ".join(map(str, cmd))}\n{r.stderr[-1500:]}')
    return r.stdout


def duration(path):
    return float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)]).strip())


def mark(clip, value, default):
    if value is None:
        return default
    return MARKS[clip][value] if isinstance(value, str) else float(value)


def card(name, seconds, out):
    run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-t', str(seconds), '-i', str(CLIPS / f'{name}.png'),
         '-vf', f'{VF},fade=t=in:d=0.4,fade=t=out:st={seconds - 0.4}:d=0.4', *ENC, str(out)])


def segment(clip, start, end, speed, out, fade=0.2):
    src = CLIPS / f'{clip}.webm'
    total = duration(src)
    start = mark(clip, start, 0.0)
    end = mark(clip, end, total)
    length = (end - start) / speed
    filt = f'trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed},fps={FPS},{VF}'
    if fade:
        filt += f',fade=t=in:d={fade},fade=t=out:st={max(0, length - fade):.3f}:d={fade}'
    run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-vf', filt, *ENC, str(out)])


def concat(parts, out):
    listing = WORK / (out.stem + '.txt')
    listing.write_text(''.join(f"file '{p}'\n" for p in parts))
    run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy', '-movflags', '+faststart', str(out)])


def timestamp(seconds):
    return f'{int(seconds // 60)}:{int(seconds % 60):02d}'


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob('*.mp4'):
        old.unlink()

    # Full video
    parts, rows, at = [], [], 0.0
    for i, (name, text) in enumerate(LONG):
        out = WORK / f'long-{i:02d}.mp4'
        if name.startswith('card:'):
            card(name[5:], CARD_SECONDS, out)
        else:
            segment(name, None, None, 1, out, fade=0.3)
        d = duration(out)
        rows.append((at, d, name, text))
        at += d
        parts.append(out)
    full = OUT / 'harvestnet-demo.mp4'
    concat(parts, full)

    # Highlight cut
    parts_s = []
    for i, (clip, a, b, speed) in enumerate(SHORT):
        out = WORK / f'short-{i:02d}.mp4'
        if clip.startswith('card:'):
            card(clip[5:], speed, out)
        else:
            segment(clip, a, b, speed, out)
        parts_s.append(out)
    short = OUT / 'harvestnet-demo-short.mp4'
    concat(parts_s, short)

    lines = [
        'HarvestNet end-to-end demo video (local run, synthetic data)',
        '',
        'Everything in these videos was recorded on one Mac, on localhost, by docs/demo/record/record_demo.py,',
        'against a local copy of the stack (docs/demo/record/start_local_stack.sh). The data is the repo\'s synthetic',
        'fixtures. It is not the live AWS system and it uses no paid model calls (rules-based negotiators), no email',
        'and no live sponsor service. Each caption bar says "Synthetic data · local run of the same code".',
        'Test tokens were generated locally for this run; none is shown.',
        '',
        f'harvestnet-demo.mp4        {timestamp(duration(full))} total',
    ]
    for start, d, name, text in rows:
        lines.append(f'  {timestamp(start)}  ({d:4.0f} s)  {name if not name.startswith("card:") else "title card"}')
        lines.append(f'       {text}')
    lines += ['', f'harvestnet-demo-short.mp4  {timestamp(duration(short))} total',
              '  Highlights, sped up in places: household request, agents negotiate, cooler failure with reason cards and fresh',
              '  approvals, the changed pickup, and the results strip. The approvals moment is left out of this cut.', '',
              'Every moment was driven live in the browser against the local stack; no step needed the recorded replay',
              '(docs/demo/replay.html). Where the live system sends an email or a text, the local run has no email service,',
              'so the clips show the local approvals service\'s review links and the household pickup screen instead.', '']
    (OUT / 'README.txt').write_text('\n'.join(lines))
    print(f'{full.name}: {duration(full):.1f} s; {short.name}: {duration(short):.1f} s')


if __name__ == '__main__':
    main()
