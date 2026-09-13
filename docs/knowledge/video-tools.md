# ローカル動画制作の補助スクリプト

更新: 2026-09-12。任意の動画試作を実行するときだけ使う。通常の漫画制作やテンプレート作成では動画処理を起動しない。

Python 3.10以上の標準ライブラリと、連結時のffmpeg/ffprobeを使う。ComfyUIは別途用意した稼働環境を参照する。スクリプトはモデルのダウンロードやAPIキーの取得を行わない。Windowsでは利用可能なPython実行ファイルを `$Python` に設定してから例を使う。ComfyUI付属のPythonも利用できる。

## 実行の流れ

元ワークフロー、参照画像、プロンプトは作品側に置く。モデルとノードを確認してから入力画像をローカルComfyUIへアップロードする。

```powershell
& $Python .\scripts\video\comfy_video_job.py --url http://127.0.0.1:8188 upload --image .\assets\characters\cast.png --record .\docs\experiments\reference-upload.json
```

upload結果のnameを次の `--image` に指定する。既存ComfyUI画像を上書きしないよう、入力名は固有名になる。

```powershell
& $Python .\scripts\video\build_minimax_prompt.py --workflow .\workflows\source-r2v.json --image UPLOADED_NAME.png --prompt-file .\workflows\cut-01.txt --seed 12345 --seconds 5 --width 896 --height 512 --steps 4 --output-prefix movie/cut-01-v1 --output .\workflows\cut-01-v1.json --server http://127.0.0.1:8188
& $Python .\scripts\video\comfy_video_job.py --url http://127.0.0.1:8188 submit --prompt .\workflows\cut-01-v1.json --record .\docs\experiments\cut-01-v1-job.json
```

上の4stepsは旧Larryvrh系の対応LoRAと専用サンプラーを含む元グラフでの試験値。**LightX2Vの8-step v1.0へそのまま流用しない。** 通常モデルのstepsを4へ減らす意味でもない。API変換はGUIのSaveVideo出力から必要な依存だけをたどり、参照・プロンプト・seed・尺を置き換える。入れ子I2VとR2Vを初期検証対象とし、任意の全ノードの変換を保証しない。モデル名等は元ワークフローから保持し、参照画像名は今回の値へ差し替える。新しいLoRAはこの変換スクリプトが自動追加するわけではないので、対応ノードを含む正しい元グラフを用意する。

5秒指定はこのH3フレーム制約では124frames/24fps=約5.167秒となる。10秒指定は丸め後10秒超となるため拒否する。生成後にffprobe等で実尺を確認する。元ワークフローと既存APIグラフは上書きせず、新しい版名で作る。

```powershell
& $Python .\scripts\video\comfy_video_job.py status --record .\docs\experiments\cut-01-v1-job.json
& $Python .\scripts\video\comfy_video_job.py collect --record .\docs\experiments\cut-01-v1-job.json --output .\output\cut-01-v1
```

status/collectは記録されたURLとprompt_idを使う。送信応答が不明なら自動再送せず、client_idとサーバーのqueue/historyを確認する。別の作業がキューにあるとsubmitは拒否し、その作業を中断しない。エラー時はjob JSONに詳細を残す。別ポートを使う場合はupload、変換、submitに同じURLを指定する。

補助処理が記録するローカルの素材・ワークフロー・回収先は、各記録ファイルの保存先を基準にした相対パス。素材と記録は同じドライブに置く。サーバーから返された生の履歴やエラー詳細には環境情報を含む場合があるため、共有用の出典・仕様と分けて作品内に保管する。

## モデル別の設定例

### ModelTC / LightX2V FL2V 8-step v1.0

確認日2026-09-12。[作者のComfyUI設定](https://github.com/ModelTC/Minimax-H3-Turbo/blob/main/COMFYUI_SETUP_AND_INFERENCE.md)と[モデル表](https://github.com/ModelTC/Minimax-H3-Turbo)に基づく。`minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` はFL2VA用の標準LoRA形式。FL2VAのUNETLoader→LoraLoaderModelOnly（1.0）→MiniMaxH3SigmaShift（video12/audio3）をBasicGuiderとBasicSchedulerへ接続する。Euler、simple、8steps、CFG1の構成。Ref2VA用、768p専用、Larryvrh旧LoRAを同一設定として扱わない。

数値は上記モデル用の設定例であり、他のモデルや解像度へ無条件に流用しない。速度と品質は使用環境で確認する。

### 末尾フレームから次のカットへ

確認済みAPIグラフを持っている場合は、`continue_minimax_clip.py` でモデル設定を維持し、開始画像・プロンプト・seed・出力名だけを変更できる。入力はGUI workflowではなくAPI JSON。LoadImageが1つのI2V用で、2画像や複数参照のグラフは拒否する。前カット末尾を抽出・目視確認してuploadした記録を渡す。

```powershell
& $Python .\scripts\video\continue_minimax_clip.py --base .\workflows\cut-01-v1.json --upload-record .\docs\experiments\cut-02-reference.json --prompt-file .\workflows\cut-02.txt --seed 12346 --prefix movie/cut-02-v1 --output .\workflows\cut-02-v1.json
```

元グラフのハッシュ・参照・変更内容は `.continuation.json` へ記録する。確認後にsubmitする。末尾に人物消失などの破綻があれば、そのフレームを連鎖させず修正する。

### 音声を含む結合

```powershell
& $Python .\scripts\video\assemble_scene.py --clip .\output\cut-01.mp4 --clip .\output\cut-02.mp4 --clip .\output\cut-03.mp4 --clip .\output\cut-04.mp4 --output .\output\scene-v1.mp4
```

同じ解像度の動画とネイティブ音声を連結し、24fps/H.264/AACのMP4へ保存する。入力の実尺・ハッシュ・ffprobe結果と実行コマンドは同名の `.assembly.json` に残す。必要なら `--trim-seconds 5` で各カット末尾を5秒まで残すが、台詞や動作を切らないか先に確認する。無音を勝手に補って音声完成扱いにはしない。

コマンドの例、他のPythonから呼ぶ `assemble_clips()`、入力条件と対応範囲は [動画連結Pythonの使い方](video-assembly.md) を参照。動画と記録の両方に上書き防止を適用する。
