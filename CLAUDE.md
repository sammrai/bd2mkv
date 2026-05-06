# bd2mkv — Blu-ray rip & encode pipeline

## 使い方 (Docker)

```bash
# rip + encode (デフォルト)
docker run --rm \
  --device /dev/sr0 --device /dev/sg3 --privileged \
  -v "$(pwd):/work" \
  ghcr.io/sammrai/bd2mkv

# rip のみ
docker run --rm <opts> ghcr.io/sammrai/bd2mkv rip

# encode のみ
docker run --rm -v "$(pwd):/work" ghcr.io/sammrai/bd2mkv encode output/<DISC_NAME> [crf]
```

出力先:
- `./output/<DISC_NAME>/` — リッピング済みMKV
- `./encoded/<DISC_NAME>/` — エンコード後MKV (メイン: `<DISC_NAME>.mkv`、その他: `*-scene.mkv`)

エンコード:
- H.265 (libx265) CRF 20 / preset medium / AAC 320kbps / チャプター・字幕維持

## キー類

`bd2mkv` は実行時に自動取得・キャッシュ:
- AACS keydb.cfg → `/var/cache/aacs/keydb.cfg` (週次更新)
- MakeMKV beta key → `/var/cache/makemkv/beta.key` (日次更新)

ホスト側で固定したい場合: `./aacs/keydb.cfg` を置けば優先される。

## チャプター自動命名 (オプション)

```bash
docker run --rm -v "$(pwd):/work" \
  ghcr.io/sammrai/bd2mkv name-chapters encoded/<DISC_NAME>
```

セットリストと歌詞からチャプター名を自動付与。faster-whisper で音声を文字起こしし、4-gram Jaccard で曲を特定、`mkvpropedit` で書き戻す。

事前準備:
```
encoded/<DISC_NAME>/
├── <DISC_NAME>.mkv
├── setlist.txt              # 1行1曲
└── lyrics/<曲名>.txt        # 空白は _ に置換
```

Whisper モデル (medium / large-v3 int8) はイメージにバンドル済 (`/opt/whisper-models`)。実行時のダウンロードは不要。

## Plexメタデータ作成

### NFOファイル

`encoded/<DISC_NAME>/<DISC_NAME>.nfo`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
    <title>タイトル</title>
    <originaltitle>オリジナルタイトル</originaltitle>
    <year>2019</year>
    <premiered>2019-06-26</premiered>
    <plot>
セットリスト:
1. 曲名1
2. 曲名2
    </plot>
    <genre>コンサート</genre>
    <genre>音楽</genre>
    <studio>レーベル名</studio>
</movie>
```

セットリストは LiveFans (https://www.livefans.jp/) で「アーティスト名 ツアー名 セットリスト」検索。

### ジャケット画像 (Amazon)

```bash
curl -s "https://www.amazon.co.jp/dp/<商品ID>" \
  -H "User-Agent: Mozilla/5.0" | \
  grep -oE '"hiRes":"https://m\.media-amazon\.com/images/I/[^"]+"'

curl -L -o poster.jpg \
  "https://m.media-amazon.com/images/I/<画像ID>._AC_SL1500_.jpg"
```

`_AC_SL1500_` = 1500px / `_AC_SL1000_` = 1000px

### ファイル配置

```
encoded/<DISC_NAME>/
├── <DISC_NAME>.mkv
├── <DISC_NAME>.nfo
├── poster.jpg
├── fanart.jpg                # 任意
└── *-scene.mkv
```

### Plex設定

- ライブラリタイプ: 映画 / その他のビデオ
- エージェント: Personal Media (レガシー) または ローカルメディアアセットを優先

## トラブルシューティング

- **"This application version is too old"** → イメージを再pull (`docker pull ghcr.io/sammrai/bd2mkv:latest`)
- **"The volume key is unknown for this disc"** → keydbキャッシュを削除して再実行 (`docker volume rm bd2mkv_aacs` 等)
- **"No titles found on disc"** → ディスク認識失敗。`docker run --rm <opts> ghcr.io/sammrai/bd2mkv bash -c "makemkvcon -r info disc:0"` で生情報確認

## CI

`.github/workflows/build.yml` が `main` push / タグで GHCR (`ghcr.io/sammrai/bd2mkv`) にイメージを push する。
