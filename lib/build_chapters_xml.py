"""Read chapters.csv (idx,start,end,duration) and assignment.tsv (idx<TAB>title),
emit a Matroska chapter XML to stdout."""
import argparse, csv


def hms(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h*3600 - m*60
    return f"{h:02d}:{m:02d}:{s:09.6f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", required=True)
    ap.add_argument("--assignment", required=True)
    ap.add_argument("--lang", default="jpn")
    args = ap.parse_args()

    titles = {}
    for line in open(args.assignment, encoding="utf-8"):
        idx, title = line.rstrip("\n").split("\t", 1)
        titles[int(idx)] = title

    rows = list(csv.DictReader(open(args.chapters)))
    rows.sort(key=lambda r: int(r["idx"]))

    print('<?xml version="1.0" encoding="UTF-8"?>')
    print('<!DOCTYPE Chapters SYSTEM "matroska.dtd">')
    print('<Chapters>')
    print('  <EditionEntry>')
    print('    <EditionFlagDefault>1</EditionFlagDefault>')
    for r in rows:
        idx = int(r["idx"])
        print('    <ChapterAtom>')
        print(f'      <ChapterTimeStart>{hms(float(r["start"]))}</ChapterTimeStart>')
        print(f'      <ChapterTimeEnd>{hms(float(r["end"]))}</ChapterTimeEnd>')
        print('      <ChapterDisplay>')
        print(f'        <ChapterString>{titles.get(idx, f"Chapter {idx:02d}")}</ChapterString>')
        print(f'        <ChapterLanguage>{args.lang}</ChapterLanguage>')
        print('      </ChapterDisplay>')
        print('    </ChapterAtom>')
    print('  </EditionEntry>')
    print('</Chapters>')


if __name__ == "__main__":
    main()
