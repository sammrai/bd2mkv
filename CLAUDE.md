# MKVリッピング・エンコード プロジェクト

## リッピング (CLI)

```bash
docker compose up -d makemkv   # MakeMKVコンテナ起動 (Web UIは http://HOST:5800/ )
./rip.sh                       # ディスク → output/<DISC_NAME>/
```

- `rip.sh` は `docker exec makemkv makemkvcon` 経由で全タイトルをリッピング
- 既にリッピング済みのタイトル (`*_tNN.mkv`) はスキップ
- ディスク名が取得できない場合は `BD_ROM` または `disc_<timestamp>` で出力

### トラブルシューティング

- **"This application version is too old"** → MakeMKVが古い。`docker compose pull makemkv && docker compose up -d makemkv` で更新
- **"The volume key is unknown for this disc"** → AACSキーが古い。最新keydb.cfgを取得:
  ```bash
  curl -L -o /tmp/keydb.zip "http://fvonline-db.bplaced.net/fv_download.php?lang=eng"
  unzip -p /tmp/keydb.zip > aacs/keydb.cfg
  docker compose restart makemkv
  ```
- **"No titles found on disc"** → ディスクが認識されていない、またはMakeMKVがメタデータを返していない。`docker compose exec makemkv /opt/makemkv/bin/makemkvcon -r info disc:0` で生情報を確認

## エンコードスクリプト

```bash
./encode.sh <input_folder> [crf]
```

- ファイルサイズ最大のものをメインとして `FOLDER_NAME.mkv` に出力
- その他は `-scene.mkv` を付けてシーンファイルとして出力
- デフォルト CRF: 20
- コーデック: H.265 (HEVC) + AAC 320kbps
- チャプター・字幕維持

## Plexメタデータ作成手順

### 1. NFOファイル作成

出力フォルダに `FOLDER_NAME.nfo` を作成:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
    <title>タイトル</title>
    <originaltitle>オリジナルタイトル</originaltitle>
    <year>2019</year>
    <premiered>2019-06-26</premiered>  <!-- 公演日 -->
    <plot>
セットリスト:
1. 曲名1
2. 曲名2
...
    </plot>
    <genre>コンサート</genre>
    <genre>音楽</genre>
    <studio>レーベル名</studio>
</movie>
```

**セットリスト取得方法:**
- LiveFans: https://www.livefans.jp/
- セトリ検索: 「アーティスト名 ツアー名 セットリスト」で検索

### 2. ジャケット画像取得 (Amazon)

1. Amazon商品ページから画像IDを取得:
```bash
curl -s "https://www.amazon.co.jp/dp/商品ID" \
  -H "User-Agent: Mozilla/5.0" | \
  grep -oE '"hiRes":"https://m\.media-amazon\.com/images/I/[^"]+"'
```

2. 高解像度版URLを構築:
```
https://m.media-amazon.com/images/I/画像ID._AC_SL1500_.jpg
```
- `_AC_SL1500_`: 1500px版
- `_AC_SL1000_`: 1000px版

3. ダウンロード:
```bash
curl -L -o poster.jpg "https://m.media-amazon.com/images/I/画像ID._AC_SL1500_.jpg"
```

### 3. ファイル配置

```
encoded/FOLDER_NAME/
├── FOLDER_NAME.mkv           # メイン動画
├── FOLDER_NAME.nfo           # メタデータ
├── poster.jpg                # ジャケット画像
├── fanart.jpg                # 背景画像 (任意)
└── *-scene.mkv               # シーン動画
```

### 4. Plex設定

- ライブラリタイプ: 映画 または その他のビデオ
- エージェント: Personal Media (レガシー) または ローカルメディアアセットを優先
- スキャン実行でメタデータ反映
