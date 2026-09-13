# 動画を連結するPython

単純連結は `scripts/video/assemble_scene.py`、ショット別のフレーム編集は `scripts/video/edit_scene.py`。どちらもコマンドとPython関数で使える。新規作品テンプレートにも同じソースと本書を配布する。

## 必要なもの

Python 3.10以上、ffmpeg、ffprobe。Pythonの追加パッケージ、GPU、ComfyUIの起動は不要。以下の `python` は、利用可能なPython実行ファイルのパスに置き換えてよい。ffmpeg/ffprobeにPATHが通っていない場合は `--ffmpeg` と `--ffprobe` で実行ファイルを指定する。

## コマンドから使う

作品ルートで実行する。`--clip` を指定した順番でつなぎ、元動画は保持する。入力ファイル名は任意で、2本でも4本以上でも使える。

```powershell
python .\scripts\video\assemble_scene.py --clip .\output\cut-01.mp4 --clip .\output\cut-02.mp4 --output .\output\scene-v1.mp4
```

各動画の冒頭から最大3秒ずつ使う場合：

```powershell
python .\scripts\video\assemble_scene.py --clip .\output\cut-01.mp4 --clip .\output\cut-02.mp4 --trim-seconds 3 --output .\output\scene-v2.mp4
```

`--trim-seconds` は全入力に同じ上限を適用する。先頭を削る機能や、クリップごとに異なる開始・終了時刻を指定する機能ではない。カット途中の台詞が切れないかは別途確認する。

## 別のPythonから使う

作品ルートをPythonのモジュール検索対象にして呼ぶ。引数は文字列・Pathのどちらでもよい。

```python
from scripts.video.assemble_scene import assemble_clips

report = assemble_clips(
    ["output/cut-01.mp4", "output/cut-02.mp4"],
    "output/scene-v3.mp4",
    # trim_seconds=3,  # 任意
    # ffmpeg="tools/ffmpeg.exe",
    # ffprobe="tools/ffprobe.exe",
)
print(report["probe"]["format"]["duration"])
```

関数は保存する連結記録と同じ辞書を返す。既存出力にはFileExistsError、不適切な入力にはValueError、外部ツールの失敗にはsubprocess/OSError系の例外を返す。コマンド版は理由を表示して異常終了する。

## 出力と適用範囲

- 入力：同じ縦横サイズ、映像と音声を持つ短い動画。各素材1～10秒を想定し、10.05秒までのメタデータの丸めを許容する。切り詰め後も1秒以上が必要。
- 出力：24fps・H.264・AAC・48kHzステレオのMP4。入力音声を連結して再エンコードする。無劣化コピーや音量の自動均一化は行わない。
- 記録：`scene-v1.assembly.json` に入力順、各入力の実尺・使用尺・SHA256、ffprobe結果、ffmpegコマンド、完成動画の情報を保存する。
- 記録内の素材・出力・コマンドの作業パスは、記録ファイルの保存先を基準にした相対パス。`path_base` は `.`。素材と記録は同じドライブに置く。実行時の内部パス解決と保存用のパスを区別する。
- 保護：動画または同名の記録が既にあれば、処理前に拒否する。別の版名を指定する。エンコード失敗時は調査用の途中ファイルが残る場合がある。
- この単純連結で未対応：無音素材への無音追加、サイズ自動調整、クロスフェード、字幕、クリップ別の編集点、1秒未満のインサート。後ろの2項目には以下のフレーム編集を使う。

技術的に連結できることと、カットの意味・動作・音声がつながることは別に確認する。映画の各ショットを何秒使うかは編集設計で決め、モデルが生成する4～7秒をそのまま1ショットの尺として固定しない。

## ショット別の開始・終了をフレームで指定する

24fpsの素材で、開始を含み終了を含まないフレーム範囲を指定する。例えば12～30は18フレーム＝0.75秒。素材は音声付き・同サイズ・各241フレーム以下が必要。1フレームから指定できる。素材パスは編集JSONの保存先を基準に解決する。

```json
{
  "version": 1,
  "shots": [
    {"id": "F01", "file": "wide.mp4", "start_frame": 0, "end_frame": 24,
     "manga_panel": "P1-1", "reason": "人物の左右を先に示す"},
    {"id": "F04", "file": "hand.mp4", "start_frame": 12, "end_frame": 30,
     "manga_panel": "P1-4", "reason": "怒りを命令の前に予告する"}
  ]
}
```

```powershell
python .\scripts\video\edit_scene.py --edit-list .\output\timeline.json --output .\output\scene-edited.mp4
```

```python
from scripts.video.edit_scene import assemble_timeline
report = assemble_timeline("output/timeline.json", "output/scene-edited.mp4")
```

任意の `crop: [x, y, width, height]` は全値を偶数とし、元画像と同じ縦横比を保ってフレーム内に収める。拡大後の出力サイズは元と同じ。`audio_gain` は0～4（既定1）。音声は映像と同じ時間で切り、48kHzステレオへ統一し、端に5ミリ秒のフェードを入れる。台詞の途中では切らず、余韻も含めて編集点を確認する。

完成MP4と `.assembly.json` を保存する。記録には編集JSONのSHA256、素材のSHA256、元のフレーム範囲、完成タイムラインの開始フレーム、コマIDや採用理由を含む全ショット情報、ffmpegコマンド、出力の検査結果を残す。既存動画・既存記録は上書きしない。音声の自動均一化、字幕、クロスフェードは行わない。独立生成した声・環境音やアクションの連続性は完成後の内容確認が必要。
