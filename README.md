# bd2mkv

MakeMKV による Blu-ray / DVD のリッピングと H.265 エンコードを単一の CLI から扱えるよう統合したプロジェクト。日本のライブ円盤については、リッピングから Plex 用メタデータ生成までを一貫して自動化する agent skill (`/rip-disc`) を併せて提供する。

## 前提

- Linux ホスト + Docker
- 光学ドライブ (Blu-ray は [LibreDrive 対応機](https://www.makemkv.com/forum/viewforum.php?f=16))
- skill 対応の agent (Claude Code など。skill 利用時のみ)

## 使い方

skill 対応の agent (Claude Code 等) 上で以下を実行する。

```
/rip-disc
```

skill が以下を自動で実行する。情報源に真の曖昧性がある場合のみユーザーに確認する。対象外のディスク (劇場映画、アニメ、洋楽ライブ、非音楽コンテンツ) では rip + encode のみで停止する。

- ディスク識別 / 光学ドライブのデバイスパス検出
- rip / encode / チャプター命名
- セットリスト取得 (Amazon 商品ページ → LiveFans)
- ジャケット取得 (Amazon → レーベル EC → HMV / Tower / 楽天)
- NFO 生成 (Personal Media エージェント向け)

セットリスト取得・ジャケット取得・チャプター命名 (ASR + ファジーマッチ) は Web スクレイピングおよび推論を伴うため非決定的。それ以外は決定論的に動作する。

## 手動実行 (CLI)

skill を使わず Docker CLI のみで実行する場合の入口。`--device` の値は環境ごとに `lsscsi -g` で確認する (詳細は [`.claude/skills/rip-disc/SKILL.md`](./.claude/skills/rip-disc/SKILL.md) 参照)。

```bash
alias bd2mkv='docker run --rm --device /dev/sr0 --device /dev/sg3 --privileged \
  -v "$(pwd):/work" ghcr.io/sammrai/bd2mkv'

bd2mkv                            # rip + encode (デフォルト)
bd2mkv rip                        # rip のみ
bd2mkv encode <folder> [crf]      # encode のみ
bd2mkv name-chapters <folder>     # チャプター命名のみ (要 setlist.txt + lyrics/)
```

## 関連ドキュメント

- [`CLAUDE.md`](./CLAUDE.md) — パイプライン仕様および Plex メタデータ規約
- [`.claude/skills/rip-disc/SKILL.md`](./.claude/skills/rip-disc/SKILL.md) — skill の自動化仕様
