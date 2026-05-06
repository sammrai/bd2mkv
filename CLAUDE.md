# bd2mkv

Blu-ray ripping + H.265 encoding pipeline. 単一 Docker イメージ `ghcr.io/sammrai/bd2mkv`。

```bash
alias bd2mkv='docker run --rm --device /dev/sr0 --device /dev/sg3 --privileged \
  -v "$(pwd):/work" ghcr.io/sammrai/bd2mkv'

bd2mkv                            # default = [1] + [2]
bd2mkv rip                        # [1] only
bd2mkv encode <folder> [crf]      # [2] only
bd2mkv name-chapters <folder>     # [3] only
```

パイプライン (各ステップは前段の出力を読む):

| | コマンド | 入力 | 出力 |
|---|---|---|---|
| [1] | `rip` | ディスク | `./output/<DISC>/title_t*.mkv` |
| [2] | `encode <f> [crf]` | `./output/<f>/*.mkv` | `./encoded/<f>/<f>.mkv` (+ `*-scene.mkv`) |
| [3] | `name-chapters <f>` | `./encoded/<f>/<f>.mkv` + `setlist.txt` + `lyrics/<曲名>.txt` | 同mkvを **in-place** で書き換え (`mkvpropedit`) |

- `[1]` のみ ディスクと AACS keydb / MakeMKV beta key (実行時取得) を要する
- `[3]` は **日本のライブBlu-ray/DVD専用**(faster-whisper 日本語ASR + 日本語歌詞4-gram Jaccard)。洋楽コンサートや非音楽ディスクには使わない
- `[3]` の事前準備: `setlist.txt` (1行1曲、`#` コメント可)、`lyrics/<曲名>.txt` (空白は `_` に置換)
- ステートレス: コンテナは `--rm` で毎回使い捨て。Whisper モデルはイメージ同梱。`./aacs/keydb.cfg` を置けばホスト固定値を優先

## Plex メタデータ

`encoded/<DISC_NAME>/<DISC_NAME>.nfo`:

```xml
<movie>
    <title>...</title>
    <year>2019</year>
    <premiered>2019-06-26</premiered>
    <plot>セットリスト:
1. 曲名1
2. 曲名2</plot>
    <genre>コンサート</genre>
    <studio>レーベル名</studio>
</movie>
```

- セットリスト: https://www.livefans.jp/ で「アーティスト名 ツアー名 セットリスト」検索
- ジャケット (Amazon): 商品ページの `hiRes` 画像IDを取得し `https://m.media-amazon.com/images/I/<ID>._AC_SL1500_.jpg` を `poster.jpg` として保存
- Plex ライブラリ: 「その他のビデオ」、エージェントは Personal Media (レガシー)
