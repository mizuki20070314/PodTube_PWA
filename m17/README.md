# PodTube for M17

Linux ハンドヘルド **M17**(Rockchip RK3126C / 480×272 / 十字キー+ボタン)で動く、PodTube PWA のクライアントです。
画面・操作・機能は [PodTube PWA](../podtube-pwa/pwa/README.md)(`https://my-dev.sakura.ne.jp/podtube/`)に合わせてあり、
**PWA のサーバー(`api.cgi`)をそのまま使います**。端末側は [LÖVE 11.4](https://love2d.org/)(Lua)のアプリで、動画のデコードだけ端末の ffmpeg に任せます。

> 非公式の YouTube クライアントです。YouTube / Google とは無関係です。

## 使うもの

- M17 本体(MinUI が動いていること。`/mnt/sdcard/Ports/Balatro` の LÖVE を流用します)
- **PC のトンネル**: この端末にはネットワーク機器が無いので、USB ケーブルでつないだ PC で `C:\Users\Mizuki\m17-net\m17-net.exe`(単一の exe)を動かしておきます
  (adb の上の SSH 逆トンネル+プロキシ。端末の 127.0.0.1:8899 が PC 経由で外に出ます。時計もそのとき合わせ、切れたら自分でやり直します。`m17-net\README.md`)
- PodTube PWA のサーバーのアドレスとアクセスキー(`~/.podtube/config.json` の `access_key`)

## インストール

```
python tools/install.py            # app/・フォント・ランチャーを送る。secrets/pt_key があればサーバー設定も書く
python tools/install.py --debug    # 開発用: PC から画面を操作する制御ソケットも有効にする
```

`secrets/pt_key` にアクセスキーを置いておくと(Git には入りません)、サーバー設定まで自動です。無ければ、初回に **設定 → サーバー設定** で画面キーボードから入力します。
MinUI の **Ports → PodTube** から起動します。**初回だけ**ボタン設定の画面が出て、この端末の各ボタンを順に押して登録します(何も押さないと既定の割り当てを使います。あとで 設定 → ボタン設定 で変更できます)。

## 操作

| 場所 | 操作 |
|---|---|
| どこでも | 十字キー=移動 / A=決定 / B=戻る / X=メニュー / Y=検索 / L・R=前後のタブ / L2・R2=ページ送り |
| タブ(ホーム・ショート・登録チャンネル・マイページ) | 左端で ← → 左のレール(🔍🏠ショート登録マイページ)/ L・R でタブ切替 / B を 2 回で終了 / START で更新 |
| ホーム | ↑ でチップ(ジャンル)/ A で動画を開く / X で「後で見る」「再生リスト」「チャンネル」「ダウンロード」…のメニュー |
| 再生(全画面) | A=再生/停止 / ←→=±10 秒(押し続けると 30・60 秒刻み。シークバー上にフィルムストリップ)/ ↑=操作パネル / L・R=前後の動画 / X=字幕 / Y=設定(画質・速度・字幕・チャプター・ループ・スリープタイマー・統計)/ L2・R2=チャプター移動 / START・↓・B=詳細表示 / SELECT=統計 |
| 再生(詳細) | 左に映像と情報、右に 高評価・保存・共有・ダウンロード / チャンネル / 概要 / コメント / 自動再生 / 関連動画。START=全画面 / B=戻る(再生は続き、下にミニプレーヤー)/ SELECT=ミニプレーヤーから動画ページへ |
| 検索 | 十字キーで文字を選び A で入力(かな=五十音表、゛゜小 キーあり / カナ / ABC / 記号)/ B=削除 / X=空白 / Y・L・R=文字種 / SELECT=大文字 / START=検索。キーボードの上端で ↑ → 検索候補(「ねこ」→「猫」のように変換代わり)。YouTube の URL を入れるとそのまま開きます |
| ショート | ↑↓=前後 / A=一時停止 / X=高評価 / Y=メニュー / → =動画ページ / START=チャンネル登録 |
| 終了 | START+SELECT を 1 秒、または タブで B 2 回、または 設定 → PodTube を終了 |

音量・明るさは本体のボタン(keymon)のままです。音量を変えると、右チャンネルが 0 のままになる MinUI の癖を直して左右をそろえます。

## 音ズレの自動補正

映像と音声は別々の HLS(映像=MPEG-TS、音声=ADTS の AAC、約 5.3 秒のセグメント)を ffmpeg に 2 本入力として読ませ、音声を基準の時計にして映像を合わせています。実測で分かった原因と、直し方:

| 原因(旧版の症状) | 直し方 |
|---|---|
| **シーク・レジューム後に映像が音より 0.3〜5 秒先に出る**。ffmpeg 4.0 の HLS は、シーク後に「目標以降の最初のキーフレーム」から映像を渡すので、最初の絵が目標より遅れて始まるのに、それを 0 番目のフレームとして扱っていた | 映像入力だけ **6.5 秒手前から読み**(`-ss`)、`-itsoffset` で時間軸を目標位置に戻し、手前の絵は `trim` で捨てる。先頭は `fps=…:start_time=0` で最初の絵を複製して 0 秒から埋める |
| 開始時にも映像が音より約 50 ms 先(映像の先頭が 0.033 秒から始まるのに、入力ごとに 0 へ正規化されていた) | 両方の入力に `-seek_timestamp 1`(ストリーム自身の時刻をそのまま使う)。音声は `aresample=async=1:first_pts=0` で 0 秒から無音で埋める |
| ダウンロードした mp4 に、トラックの開始時刻の差が焼き込まれる | ダウンロードも同じ時間軸でコピーし、全体を共通の量だけずらす(`-avoid_negative_ts make_zero`) |
| 音が途切れている間にも時計が進み、音が戻ると映像が先走って見える | 時計(`player/clock.lua`)は **デバイスに渡した音声の終わりを越えない**。音が止まれば映像も止まる |

それでも実行中に映像が遅れ続ける(CPU が足りない・セグメントが遅い)場合は `player/syncmon.lua` が見張ります:
次の絵が 0.25 秒以上遅れた状態が 3 秒続くと**現在位置から再同期**(トースト表示)、45 秒以内にまた起きたら**画質を一段下げて**再同期(最下段ならフレームレートを 24→15)、
ALSA の under-run が 10 秒に 4 回なら**デバイスのバッファを 120→250→500 ms に増やして**再同期、15 秒何も進まなければ再同期。1 本の動画で 6 回までで、設定 → 音ズレの自動補正 で切れます。
統計(SELECT)に `A/V +xxms late xxms repairs n` が出ます。設定の「映像と音声の微調整」は、画面や音声経路そのものの遅れ(物理的な遅延)を手で足すための残りです。

試験: `tools/avsync/`(合成の閃光+ビープを HLS にして端末の ffmpeg で測る `avsync_test.py`、本物のサーバーの音ズレ試験動画を測る `real_test.py`・`real_first_pts.py`、アプリ全体を制御ソケットで測る `app_test.py`、重すぎる画質で自動修復を起こさせる `hq_test.py`)、
`tools/test_sync.py`(時計・監視・ffmpeg 引数)、`tools/test_engine.py`(エンジンを偽の LÖVE と模擬の音声デバイスで動かす)。

**実機での結果(2026-11-13、本物のサーバーの音ズレ試験動画・PC の `m17-net.exe` 経由)**: 開始・シーク後(13.0 秒・5.5 秒)とも映像は音より **−10〜−13 ms**(1 フレーム未満)で、遅れ 0 ms・xrun 0・終端は `ended`。
CPU を奪う 8 本(nice −10)を走らせると音の途切れ(xrun)が出て、**再同期(ALSA バッファ 120→250 ms)→ 2 回目で画質上限 720p・バッファ 500 ms** と自動で直り、
負荷が終わると −10 ms で揃って再生が続きました。1080p を求める `hq_test.py` でも同じ連鎖が働き、720p 上限で映像と音が ±10 ms のまま(フレームは数 % 落とす)でした。
実機では遅れたフレームを落として追いつくため、「絵が 0.25 秒遅れる」経路より xrun・停止の経路が先に働きます(遅れの最大は 14 ms)。

## PWA との対応

ホーム(チップ・続きの読み込み・更新で見たものを後ろへ)/ 検索(候補・履歴・フィルタ・リンク貼り付け)/ 再生(画質・速度・字幕・チャプター・ループ・スリープタイマー・統計・音声トラック・フィルムストリップ・ミニプレーヤー)/
動画情報(高評価・概要・コメント・関連・自動再生・再生リスト連続再生)/ ショート / チャンネル(タブ)/ 再生リスト / 登録チャンネル(未ログイン=端末内、インポート)/
マイページ(履歴・再生リスト・後で見る・高評価・ダウンロード)/ 設定 / Google ログイン(機器コード)と、アカウントの おすすめ・登録・履歴(端末の再生を時刻に合わせて混ぜる)・後で見る・高評価・再生リスト、視聴履歴への記録 /
ダウンロードとオフライン再生 / 接続診断。

**この端末では出来ないこと**: 全画面表示の切り替え・PiP・AirPlay・ロック画面(ブラウザの機能)/ 「制限されたら公式の埋め込みプレーヤーで再生」(ブラウザが無い。サーバーの IP が bot 判定されると再生できません。時間を置いて再試行)/ ライブ配信 / QR コード。
データ(履歴・登録・設定・トークン)は端末の中(`/mnt/sdcard/Ports/PodTube/love/podtube/`)だけにあり、PWA とは共有されません。

## 仕組み

```
LÖVE アプリ(Lua) ──curl──▶ PodTube サーバー api.cgi ──▶ YouTube
   │  ├ 画面・入力: GLES2(Mali-400)で描画。ボタンは /dev/input/event* を FFI で直接読む(SDL のキー入力は使わない)
   │  └ 再生: posix_spawn で ffmpeg を起動(HLS の映像と音声を別の入力として読む)
   │        ├ fd3: 生の YUV420 フレーム ─▶ 映像スレッド ─▶ シェーダ(YUV→RGB・拡大)
   │        └ fd4: PCM 44.1kHz ─▶ 音声スレッド ─▶ ALSA 直書き。再生位置(書いた数 − 機器の遅延)が A/V のクロック
   └ 画像: curl ─▶ ディスクキャッシュ ─▶ スレッドでデコード ─▶ LRU
```

- 端末の ffmpeg は 2018 年版(ソフトウェアの h264 / aac)。MinUI が全部を CPU3 だけに固定しているので、ランチャーが `taskset` で 4 コアに広げます。360p のデコードは 4 コアで約 6 倍速、CPU の使用は全体の約 2 割。
- 画質は既定 360p(最大 480p)。変換と拡大を ffmpeg(CPU)でやると実時間に届かないため、YUV のまま GPU に渡します。
- 音声は LÖVE の audio(OpenAL)を切り、ALSA を直接使います(音声の遅延を取れるため)。クロックはソフトウェアの PLL でなめらかにしています。
- `app/data/strings.lua`(日本語・英語の文言)と `app/data/icons_*.png`(Material アイコン)は、PWA のソースから `tools/gen_strings.py` / `tools/gen_icons.py` で生成します。

```
app/
  main.lua, conf.lua      起動・独自のメインループ(変化したときだけ描画)・例外からの回復
  core/                   app(画面スタックとレール)・input・net(curl のワーカー)・img・store・account・downloads・feed・nav ・proc(posix_spawn)ほか
  player/                 engine(ffmpeg+スレッド)・player(状態・キュー・履歴・字幕)・storyboard・chapters・hls
  ui/                     draw・text・feedlist・menulist・keyboard・hud・sheet・mini・chips …
  screens/                home・watch・search・results・channel・playlist・shorts・subs・you・library・downloads・settings・signin・comments・buttons・gate・diag
  data/ fonts/            文言・アイコン・Noto Sans JP(400/500/700)
device/PodTube.sh         MinUI のランチャー(プロキシの有無・ミキサー補正・CPU の開放)
tools/                    開発用の道具(下)
```

## 開発用の道具

```
python tools/fbshot.py [out.png]        画面を撮る。MinUI も LÖVE も DRM(KMS)で描くので /dev/fb0 は黒いまま。
                                        端末の kmsshot(静的リンクの小さな C、ioctl で走査中のバッファを読む)で撮り、PNG にする。--fb で /dev/fb0
python tools/dev.py push|launch|stop|log|shot|run|provision|debug    端末への配備・起動(MinUI を SIGKILL して /tmp/next で起動)・ログ
python tools/ctl.py key down a / seq "down down a" --shot name / eval "..." / state / reload / text 猫    制御ソケット(debug.flag が要る)
python tools/luacheck.py                全 Lua を LuaJIT 2.1(lupa)で構文検査   python tools/check_strings.py   文言キーの過不足
python tools/soak.py 180                長時間再生の状態記録(落ちフレーム・xrun・メモリ)
python tools/test_sync.py               時計・同期監視・ffmpeg 引数の単体試験(模擬時間)   python tools/test_engine.py   エンジンの試験(偽の LÖVE)
python tools/avsync/avsync_test.py [--legacy] [--kind ts|single-ts]    合成ストリームでの音ズレ測定(端末の ffmpeg)
python tools/avsync/real_test.py [--both]    本物のサーバーの音ズレ試験動画での測定   real_first_pts.py   位置ごとの最初の絵・音の時刻
python tools/avsync/app_test.py [--stress [--hogs 8 --nice -10 --stress-seconds 50]]   アプリ全体の音ズレ(開始・シーク・終端)と、CPU を奪ったときの自動修復
python tools/avsync/hq_test.py [--height 1080]   端末が実時間でデコードできない画質を求めて、自動で画質が下がって揃うまで
tools/uinput_pad.c                      /dev/uinput で仮想ゲームパッドを作り、ボタン入力(キー・十字キーの軸)を本物のカーネル入力で試験する
tools/api.py                            サーバーの API を手元から叩いて応答の形を見る
```

`debug.flag` が無いと制御ソケット(127.0.0.1:7777、端末の中だけ)は開きません。`install.py` は既定でフラグを消します。

## 確認した範囲

実機(M17)で、ホーム・検索(五十音キーボード・候補)・結果・チャンネル・再生リスト・動画再生(映像+音声のパイプ、シーク、一時停止、字幕、フィルムストリップ、ダウンロードとオフライン再生)・
ショート・登録チャンネル・マイページ・設定・ログインのコード表示・コメント・インポートを、画面を撮って確認しました。再生中のメモリは、love.armhf が RSS 約 46〜49 MB・ffmpeg が約 23〜26 MB、端末全体の MemAvailable が約 150 MB(全体 245 MB)で、既定の 360p を 2〜3 分(シーク・一時停止を含む)再生した間は増え続けず、xrun もありませんでした(2026-11-12 の測定。数時間の連続再生と、音ズレ対策後の版の RSS は測っていません)。
ボタン入力は仮想ゲームパッドで、キーと軸のタップ・長押しリピートを確認しました。

**未確認**: 実機のボタンの割り当て(初回のボタン設定で決めます)/ 実際の音(ALSA は RUNNING・書き込みは実時間で進むのを確認、耳では未確認。映像と音のずれは 設定 → 映像と音声のずれ補正。画面・スピーカーの物理的な遅れは測っていません)/
Google アカウントのログインの通し(コードの承認 → 反映)/ 視聴履歴への記録 / 長時間のバッテリー。
