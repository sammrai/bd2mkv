"""Run faster-whisper over chapter snippets in /w/chapters/*.mp3.

Pass 1: medium (vad_filter=True) over all snippets.
Pass 2: large-v3 (vad_filter=False) over snippets that came back empty
        or look like Whisper hallucinations on quiet audio.

Outputs JSON per chapter to /w/transcripts/<name>.json with the merged best
transcript across passes (pass 2 wins when it has more characters).
"""
import json, os, glob, re

CHAPTERS = os.environ.get("INPUT_DIR", "/w/chapters")
OUT = os.environ.get("OUTPUT_DIR", "/w/transcripts")
CACHE = os.environ.get("WHISPER_CACHE", "/cache")
os.makedirs(OUT, exist_ok=True)

HALLUCINATION_MARKERS = [
    "ご視聴ありがとうございました",
    "JR東日本",
    "おやすみなさい",
    "Subscribe",
    "by H.",
]


def is_useless(text: str) -> bool:
    t = re.sub(r"\s+", "", text or "")
    if len(t) < 10:
        return True
    return any(m in text for m in HALLUCINATION_MARKERS) and len(t) < 80


def transcribe(model, path):
    segments, _ = model.transcribe(
        path, language="ja", beam_size=5,
        vad_filter=False,
        condition_on_previous_text=False,
        temperature=[0.0, 0.2, 0.4],
        no_speech_threshold=0.3,
    )
    segs = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    text = " ".join(s["text"].strip() for s in segs)
    return text, segs


def run_pass(model_name, snippets):
    from faster_whisper import WhisperModel
    print(f"loading {model_name} ...", flush=True)
    m = WhisperModel(model_name, device="cpu", compute_type="int8",
                     download_root=CACHE)
    for path in snippets:
        name = os.path.splitext(os.path.basename(path))[0]
        out_path = f"{OUT}/{name}.json"
        existing = None
        if os.path.exists(out_path):
            existing = json.load(open(out_path))
            if not is_useless(existing.get("text", "")):
                # already have a good transcript
                continue
        print(f"transcribe {name} ({model_name})", flush=True)
        text, segs = transcribe(m, path)
        keep = {"name": name, "model": model_name, "text": text, "segments": segs}
        # if existing has more characters, keep both: prefer longer
        if existing and len(re.sub(r"\s+", "", existing.get("text", ""))) > len(re.sub(r"\s+", "", text)):
            keep = existing
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=2)
        print(f"  -> {keep['text'][:100]}", flush=True)


snippets = sorted(glob.glob(f"{CHAPTERS}/ch*.mp3"))
run_pass("medium", snippets)
# pass 2: only chapters that still look bad
need = []
for s in snippets:
    name = os.path.splitext(os.path.basename(s))[0]
    p = f"{OUT}/{name}.json"
    if not os.path.exists(p) or is_useless(json.load(open(p)).get("text", "")):
        need.append(s)
if need:
    print(f"pass 2: {len(need)} chapters need large-v3", flush=True)
    run_pass("large-v3", need)
print("done", flush=True)
