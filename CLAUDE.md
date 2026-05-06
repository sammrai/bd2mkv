# bd2mkv

Blu-ray ripping + H.265 encoding pipeline. 単一 Docker イメージ `ghcr.io/sammrai/bd2mkv`。

```bash
# rip + encode
docker run --rm --device /dev/sr0 --device /dev/sg3 --privileged \
  -v "$(pwd):/work" ghcr.io/sammrai/bd2mkv

# サブコマンド
ghcr.io/sammrai/bd2mkv rip
ghcr.io/sammrai/bd2mkv encode <folder> [crf]
ghcr.io/sammrai/bd2mkv name-chapters <folder>
```

AACS keydb (週次) と MakeMKV beta key (日次) は実行時自動取得・キャッシュ。`./aacs/keydb.cfg` 配置で上書き可。強制更新: `bd2mkv update-keys`。Whisper モデルはイメージ同梱。

`name-chapters` 事前準備:

```
encoded/<DISC>/
├── <DISC>.mkv
├── setlist.txt          # 1行1曲、# でコメント
└── lyrics/<曲名>.txt    # 空白は _ に置換
```

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
