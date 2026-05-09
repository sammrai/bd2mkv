# bd2mkv

Blu-ray / DVD のリッピングおよび H.265 エンコードを行う、単一 Docker イメージで完結するパイプライン。日本のライブ円盤については、付属の Claude Code skill により Plex 用メタデータ整備までを自動化する。

## 前提

- Linux ホスト + Docker + 光学ドライブ
- Claude Code (skill 利用時)
- Plex ライブラリのマウントパス (Plex 配置を行う場合のみ)

## 使い方

Claude Code 上で以下を実行する。

```
/rip-disc
```

skill が以下を自動で実行する。情報源に真の曖昧性がある場合のみユーザーに確認する。対象外のディスク (劇場映画、アニメ、洋楽ライブ、非音楽コンテンツ) では rip + encode のみで停止する。

- ディスク識別 / 光学ドライブのデバイスパス検出
- rip / encode / チャプター命名
- セットリスト取得 (Amazon 商品ページ → LiveFans)
- ジャケット取得 (Amazon → レーベル EC → HMV / Tower / 楽天)
- NFO 生成 (Personal Media エージェント向け)
- Plex ライブラリへの配置

セットリスト取得・ジャケット取得・チャプター命名 (ASR + ファジーマッチ) は Web スクレイピングおよび推論を伴うため非決定的。それ以外は決定論的に動作する。

## 手動実行 (CLI)

skill を使わず Docker CLI のみで実行する場合の入口。`--device` の値は環境ごとに `lsscsi -g` で確認する (詳細は `.claude/skills/rip-disc/SKILL.md` 参照)。

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
